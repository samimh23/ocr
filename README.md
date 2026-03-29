# 🇹🇳 Tunisian Invoice & Bank Statement OCR

An intelligent OCR extraction and fraud detection tool for Tunisian financial
documents (invoices / *factures* and bank statements / *relevés bancaires*).

## Features

- **Mistral OCR + LLM** – two-stage pipeline: OCR text extraction → structured JSON
- **Tunisian number format** – handles European notation (`2.361,625` → `2361.625`)
- **RIB parsing** – extracts bank code, *agence*, and account number automatically
- **Running balance** – calculates per-transaction solde when missing
- **Solde final** – computed as `solde_initial + total_credits − total_debits`
- **Fraud detection** – rule-based checks with a 0–100 fraud score
- **REST API** – FastAPI with `/analyze` (Mistral) and `/extract` (Tesseract) endpoints

---

## Setup

### Prerequisites

- Python 3.10+
- Mistral API key (https://console.mistral.ai/)

### Installation

```bash
git clone https://github.com/samimh23/ocr.git
cd ocr
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### Environment Variables

Create a `.env` file in the project root (never commit this file):

```
MISTRAL_API_KEY=your_key_here
```

Or export directly:

```bash
export MISTRAL_API_KEY=your_key_here
```

---

## Usage

### CLI Test Script

Process `biat.png` (or any image/PDF):

```bash
python tests/test_biat.py                        # uses biat.png
python tests/test_biat.py path/to/invoice.png
python tests/test_biat.py path/to/statement.pdf
```

Output is printed to the console and saved as `results_<filename>.json`.

### Start the API Server

```bash
uvicorn main:app --reload --port 8000
```

Visit the interactive docs at http://localhost:8000/docs

---

## API Reference

### `POST /analyze`

Upload an image or PDF and receive extracted data + fraud analysis.

**Request:** `multipart/form-data` with a `file` field.

**Response:**

```json
{
  "extracted_data": {
    "type": "releve_bancaire",
    "banque": "BIAT",
    "agence": "303",
    "numero_compte": "0002810013616",
    "rib": "08 303 0002810013616 47",
    "titulaire": "MAHJOUB SAMI",
    "periode": { "debut": "01/01/2024", "fin": "31/01/2024" },
    "solde_initial": 1500.000,
    "solde_final": 2361.625,
    "transactions": [
      { "date": "05/01/2024", "libelle": "Virement", "debit": null, "credit": 1000.000, "solde": 2500.000 }
    ],
    "total_debits": 138.375,
    "total_credits": 1000.000
  },
  "fraud_report": {
    "alerts": [],
    "fraud_score": 0,
    "risk_level": "LOW"
  }
}
```

### `POST /extract`

Legacy Tesseract-based extraction (no Mistral API key required).

### `GET /health`

Returns service health status.

### `GET /banks`

Lists all supported Tunisian banks and their RIB prefixes.

---

## Fraud Detection

The fraud engine runs the following checks:

| Check | Document Type | Severity |
|---|---|---|
| Balance consistency (`initial + credits − debits = final`) | Statement | CRITICAL |
| Arithmetic check (`HT + TVA + Timbre = TTC`) | Invoice | CRITICAL |
| Invalid matricule fiscal format | Invoice | HIGH |
| Invalid/unknown TVA rate | Invoice | HIGH |
| RIB length (must be 20 digits) | Both | HIGH |
| Future-dated document | Both | HIGH |
| Unknown Tunisian bank code in RIB | Both | MEDIUM |
| Duplicate transactions | Statement | MEDIUM |
| High-value transaction (> 50,000 TND) | Statement | MEDIUM |
| Unusual timbre fiscal (≠ 1.000 TND) | Invoice | MEDIUM |
| Benford's Law anomaly (≥ 20 transactions) | Statement | MEDIUM |
| Weekend-dated transaction | Both | LOW |

**Risk levels:** `LOW` (0–20) · `MEDIUM` (21–50) · `HIGH` (51–80) · `CRITICAL` (81–100)

---

## Tunisian Bank Codes

| Code | Bank |
|---|---|
| 01 | STB – Société Tunisienne de Banque |
| 02 | BNA – Banque Nationale Agricole |
| 03 | BH – Banque de l'Habitat |
| 07 | Amen Bank |
| 08 | BIAT – Banque Internationale Arabe de Tunisie |
| 09 | Attijari Bank |
| 10 | ATB – Arab Tunisian Bank |
| 11 | UIB – Union Internationale de Banques |
| 12 | UBCI – Union Bancaire pour le Commerce et l'Industrie |
| 25 | Zitouna Bank |

---

## Development Workflow

### Keeping your branch up to date with `main`

When new commits are pushed to `main` (e.g. after a pull request is merged), update your local branch with:

```bash
# 1. Fetch the latest changes from the remote
git fetch origin

# 2. Merge main into your current branch
git merge origin/main

# 3. Push the updated branch
git push origin <your-branch-name>
```

Or, if you prefer a linear history, rebase instead of merge:

```bash
git fetch origin
git rebase origin/main
git push --force-with-lease
```

> **Note:** `git push --force-with-lease` (without specifying a branch) pushes the current branch to its configured upstream — the same as `git push --force-with-lease origin <your-branch-name>`. Both forms work identically on Windows PowerShell and macOS/Linux.

> **Tip:** Run `git status` and `git log --oneline origin/main..HEAD` at any time to see how far ahead or behind your branch is relative to `main`.

---

## Project Structure

```
ocr/
├── main.py                          # FastAPI application
├── requirements.txt
├── .env                             # API keys (not committed)
├── biat.png                         # Sample BIAT bank statement
├── models/
│   ├── banks.py                     # Tunisian bank definitions
│   └── document.py                  # Pydantic response models
├── services/
│   ├── mistral_ocr_service.py       # Mistral OCR + LLM extraction
│   ├── fraud_detection_service.py   # Rule-based fraud detection
│   ├── ocr_service.py               # Tesseract OCR (legacy)
│   ├── bank_detector.py
│   ├── document_classifier.py
│   └── field_extractor.py
├── tests/
│   ├── test_biat.py                 # CLI test script
│   └── test_extractor.py
└── utils/
    ├── rib_parser.py                # Tunisian RIB parser
    └── preprocessing.py
```
