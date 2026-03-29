"""
Test script — process biat.png (or any image/PDF) with Mistral OCR
and run fraud detection on the extracted data.

Usage:
    python tests/test_biat.py                    # uses biat.png in repo root
    python tests/test_biat.py path/to/file.png   # custom file
    python tests/test_biat.py path/to/file.pdf   # PDF support

Results are printed to stdout and saved to results_<filename>.json
"""

import json
import os
import sys
from pathlib import Path

# Ensure the project root is on the Python path regardless of where the
# script is invoked from.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv

load_dotenv(_PROJECT_ROOT / ".env")

from services.mistral_ocr_service import MistralOCRService
from services.fraud_detection_service import FraudDetectionService


def run(file_path: Path) -> None:
    print(f"\n{'='*60}")
    print(f"  Tunisian Document OCR + Fraud Detection")
    print(f"  File: {file_path.name}")
    print(f"{'='*60}\n")

    # ── Step 1: OCR extraction ────────────────────────────────────────
    print("[1/2] Extracting structured data via Mistral OCR …")
    ocr_service = MistralOCRService()
    extracted = ocr_service.extract_from_image_path(file_path)

    print("\n── Extracted Data ───────────────────────────────────────────")
    print(json.dumps(extracted, indent=2, ensure_ascii=False))

    # ── Step 2: Fraud detection ───────────────────────────────────────
    print("\n[2/2] Running fraud detection …")
    detector = FraudDetectionService()
    fraud_report = detector.analyze(extracted)

    print("\n── Fraud Analysis ───────────────────────────────────────────")
    print(f"  Fraud Score : {fraud_report['fraud_score']} / 100")
    print(f"  Risk Level  : {fraud_report['risk_level']}")
    print(f"  Alerts      : {len(fraud_report['alerts'])}")

    if fraud_report["alerts"]:
        print()
        for i, alert in enumerate(fraud_report["alerts"], 1):
            level = alert.get("level", "INFO")
            alert_type = alert.get("type", "UNKNOWN")
            message = alert.get("message", "")
            print(f"  [{i}] [{level}] {alert_type}")
            print(f"       {message}")
    else:
        print("\n  ✅  No fraud indicators detected.")

    # ── Save results ──────────────────────────────────────────────────
    output = {
        "file": str(file_path),
        "extracted_data": extracted,
        "fraud_report": fraud_report,
    }
    output_path = _PROJECT_ROOT / f"results_{file_path.stem}.json"
    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(output, fh, indent=2, ensure_ascii=False)

    print(f"\n✔  Results saved to: {output_path}")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        target = Path(sys.argv[1]).resolve()
    else:
        # Default: biat.png in the project root
        target = _PROJECT_ROOT / "biat.png"

    if not target.exists():
        print(f"Error: file not found — {target}", file=sys.stderr)
        sys.exit(1)

    run(target)
