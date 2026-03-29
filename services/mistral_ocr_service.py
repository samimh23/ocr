"""
Mistral OCR Service — extract structured financial data from Tunisian
invoices (factures) and bank statements (relevés bancaires) using the
Mistral vision / OCR API.

Environment variable required:
    MISTRAL_API_KEY   — your Mistral API key

Optionally place the key in a .env file at the project root.
"""

import base64
import json
import os
import re
from pathlib import Path
from typing import Union

from dotenv import load_dotenv
from mistralai import Mistral, ImageURLChunk, DocumentURLChunk

from utils.rib_parser import parse_rib

load_dotenv()

_MISTRAL_MODEL = "mistral-ocr-latest"   # OCR / document-understanding model
_LLM_MODEL = "mistral-small-latest"     # Chat model used for structured extraction


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = (
    "You are an expert at reading Tunisian financial documents "
    "(bank statements and invoices). "
    "Extract ALL fields accurately and return ONLY valid JSON with no markdown."
)

_EXTRACTION_PROMPT = """
Analyze the OCR text extracted from a Tunisian financial document and return structured JSON.

IMPORTANT — Tunisian number format:
  - Dot (.) = thousands separator  →  2.361  means 2361
  - Comma (,) = decimal separator  →  2.361,625  means 2361.625
  Always convert to plain float (e.g. 2361.625).

For a BANK STATEMENT (relevé bancaire), return:
{
  "type": "releve_bancaire",
  "banque": "<bank name>",
  "agence": "<agency name or code>",
  "numero_compte": "<account number>",
  "rib": "<full RIB as found in the document>",
  "titulaire": "<account holder name>",
  "periode": {"debut": "<DD/MM/YYYY>", "fin": "<DD/MM/YYYY>"},
  "solde_initial": <float>,
  "solde_final": <float>,
  "transactions": [
    {"date": "<DD/MM/YYYY>", "libelle": "<description>", "debit": <float or null>, "credit": <float or null>, "solde": <float or null>}
  ],
  "total_debits": <float>,
  "total_credits": <float>
}

For an INVOICE (facture), return:
{
  "type": "facture",
  "numero_facture": "<invoice number>",
  "date_facture": "<DD/MM/YYYY>",
  "emetteur": {
    "raison_sociale": "<company name>",
    "matricule_fiscal": "<fiscal ID>",
    "adresse": "<address>",
    "telephone": "<phone>"
  },
  "client": {
    "raison_sociale": "<company name>",
    "matricule_fiscal": "<fiscal ID>",
    "adresse": "<address>"
  },
  "lignes": [
    {"description": "<item>", "quantite": <float>, "prix_unitaire": <float>, "montant": <float>}
  ],
  "montant_ht": <float>,
  "taux_tva": <float>,
  "montant_tva": <float>,
  "timbre_fiscal": <float>,
  "montant_ttc": <float>,
  "mode_paiement": "<payment method>",
  "rib": "<RIB if present>"
}

Rules:
- Use null for missing values, never empty string for numeric fields.
- All amounts in TND with up to 3 decimal places.
- Return ONLY the JSON object, no explanation, no markdown fences.

OCR TEXT:
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_tunisian_number(value: Union[str, float, int, None]) -> Union[float, None]:
    """Convert Tunisian-formatted number string to float.

    Tunisian/European convention:
      dot   → thousands separator  (2.361 → 2361)
      comma → decimal separator    (2.361,625 → 2361.625)
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    raw = str(value).strip()
    # Remove currency labels
    raw = re.sub(r"[^\d,.\-]", "", raw)
    if not raw:
        return None
    # If both dot and comma present:  1.234,56 → 1234.56
    if "." in raw and "," in raw:
        raw = raw.replace(".", "").replace(",", ".")
    elif "," in raw:
        # Only comma: could be decimal (1234,56) or thousands (1,234)
        comma_pos = raw.rfind(",")
        after_comma = raw[comma_pos + 1:]
        if len(after_comma) <= 3:
            raw = raw.replace(",", ".")
        else:
            raw = raw.replace(",", "")
    # Only dots remaining — if last dot separates ≤3 digits treat as decimal
    elif raw.count(".") == 1:
        dot_pos = raw.rfind(".")
        after_dot = raw[dot_pos + 1:]
        if len(after_dot) > 3:
            raw = raw.replace(".", "")
    elif raw.count(".") > 1:
        raw = raw.replace(".", "")
    try:
        return round(float(raw), 3)
    except ValueError:
        return None


def _normalize_amounts(data: dict) -> dict:
    """Recursively ensure all numeric-looking strings are converted to floats."""
    numeric_keys = {
        "solde_initial", "solde_final", "total_debits", "total_credits",
        "debit", "credit", "solde", "montant_ht", "montant_tva",
        "montant_ttc", "timbre_fiscal", "taux_tva", "quantite",
        "prix_unitaire", "montant",
    }
    if isinstance(data, dict):
        return {k: (_parse_tunisian_number(v) if k in numeric_keys else _normalize_amounts(v))
                for k, v in data.items()}
    if isinstance(data, list):
        return [_normalize_amounts(item) for item in data]
    return data


def _calculate_running_balance(data: dict) -> dict:
    """Fill in missing per-transaction running balances."""
    if data.get("type") != "releve_bancaire":
        return data
    transactions = data.get("transactions") or []
    balance = data.get("solde_initial") or 0.0
    for tx in transactions:
        debit = tx.get("debit") or 0.0
        credit = tx.get("credit") or 0.0
        if tx.get("solde") is None or tx.get("solde") == 0.0:
            balance = round(balance + credit - debit, 3)
            tx["solde"] = balance
        else:
            balance = tx["solde"]
    return data


def _calculate_solde_final(data: dict) -> dict:
    """Calculate solde_final if missing or zero."""
    if data.get("type") != "releve_bancaire":
        return data
    initial = data.get("solde_initial") or 0.0
    total_credits = data.get("total_credits") or 0.0
    total_debits = data.get("total_debits") or 0.0
    current_final = data.get("solde_final")
    if not current_final or current_final == 0.0:
        data["solde_final"] = round(initial + total_credits - total_debits, 3)
    return data


def _enrich_rib(data: dict) -> dict:
    """Parse RIB and fill agence / numero_compte if empty."""
    rib_raw = data.get("rib")
    if not rib_raw:
        return data
    parsed = parse_rib(rib_raw)
    if not parsed["is_valid"]:
        return data
    if not data.get("agence"):
        data["agence"] = parsed["agence"]
    if not data.get("numero_compte"):
        data["numero_compte"] = parsed["account_number"]
    return data


def _extract_json(text: str) -> dict:
    """Extract a JSON object from the LLM response (handles stray markdown)."""
    text = text.strip()
    # Strip markdown code fences if present
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:])
        if text.strip().endswith("```"):
            text = text.strip()[:-3].strip()
    # Attempt direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Try to find the first {...} block
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    raise ValueError(f"Could not parse JSON from LLM response:\n{text[:500]}")


# ---------------------------------------------------------------------------
# Main service class
# ---------------------------------------------------------------------------

class MistralOCRService:
    """
    Two-stage pipeline:
      1. Mistral OCR — convert image/PDF page to raw text
      2. Mistral LLM — extract structured JSON from OCR text

    Then post-processes:
      - Tunisian number normalisation
      - RIB parsing (agence + numero_compte)
      - Running balance calculation
      - Solde final calculation
    """

    def __init__(self, api_key: str = None):
        key = api_key or os.getenv("MISTRAL_API_KEY")
        if not key:
            raise ValueError(
                "MISTRAL_API_KEY not found. "
                "Set the environment variable or pass api_key= explicitly."
            )
        self._client = Mistral(api_key=key)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def extract_from_file(self, file_bytes: bytes, filename: str) -> dict:
        """
        High-level entry point.  Accept raw bytes + filename and return
        a fully post-processed structured dict.
        """
        filename_lower = filename.lower()
        if filename_lower.endswith(".pdf"):
            ocr_text = self._ocr_pdf(file_bytes)
        elif filename_lower.endswith((".png", ".jpg", ".jpeg", ".tiff", ".bmp", ".webp")):
            ocr_text = self._ocr_image(file_bytes, filename)
        else:
            raise ValueError(f"Unsupported file type: {filename}")

        return self._extract_structured(ocr_text)

    def extract_from_image_path(self, image_path: Union[str, Path]) -> dict:
        """Convenience wrapper for a local image file path."""
        image_path = Path(image_path)
        with open(image_path, "rb") as fh:
            file_bytes = fh.read()
        return self.extract_from_file(file_bytes, image_path.name)

    # ------------------------------------------------------------------
    # Stage 1 — OCR
    # ------------------------------------------------------------------

    def _ocr_image(self, image_bytes: bytes, filename: str) -> str:
        """Run Mistral OCR on a single image and return the markdown text."""
        ext = Path(filename).suffix.lstrip(".").lower()
        mime_map = {
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "png": "image/png",
            "tiff": "image/tiff",
            "bmp": "image/bmp",
            "webp": "image/webp",
        }
        mime = mime_map.get(ext, "image/png")
        encoded = base64.b64encode(image_bytes).decode("utf-8")
        data_url = f"data:{mime};base64,{encoded}"

        response = self._client.ocr.process(
            model=_MISTRAL_MODEL,
            document=ImageURLChunk(image_url=data_url),
        )
        pages = response.pages or []
        return "\n\n".join(p.markdown for p in pages if p.markdown)

    def _ocr_pdf(self, pdf_bytes: bytes) -> str:
        """Run Mistral OCR on a PDF (base64-encoded) and return text."""
        encoded = base64.b64encode(pdf_bytes).decode("utf-8")

        response = self._client.ocr.process(
            model=_MISTRAL_MODEL,
            document=DocumentURLChunk(
                document_url=f"data:application/pdf;base64,{encoded}"
            ),
        )
        pages = response.pages or []
        return "\n\n".join(p.markdown for p in pages if p.markdown)

    # ------------------------------------------------------------------
    # Stage 2 — LLM structured extraction
    # ------------------------------------------------------------------

    def _extract_structured(self, ocr_text: str) -> dict:
        """Send OCR text to an LLM and return post-processed structured dict."""
        response = self._client.chat.complete(
            model=_LLM_MODEL,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": _EXTRACTION_PROMPT + ocr_text},
            ],
            temperature=0.0,
        )
        raw_json_text = response.choices[0].message.content
        data = _extract_json(raw_json_text)

        # Post-processing pipeline
        data = _normalize_amounts(data)
        data = _enrich_rib(data)
        data = _calculate_running_balance(data)
        data = _calculate_solde_final(data)

        return data
