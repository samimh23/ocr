"""
Tunisian Bank Document Extractor API
FastAPI application for accountants to extract data from bank statements
"""
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from models.document import DocumentExtractionResult, BankInfo
from services.ocr_service import OCRService
from services.bank_detector import BankDetector
from services.document_classifier import DocumentClassifier
from services.field_extractor import FieldExtractor

app = FastAPI(
    title="🇹🇳 Tunisian Bank Document Extractor",
    description="Extract structured data from Tunisian bank statements (Relevé Bancaire) for accountants",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize services
ocr_service = OCRService(lang="fra+ara")
bank_detector = BankDetector()
document_classifier = DocumentClassifier()
field_extractor = FieldExtractor()


@app.post("/extract", response_model=DocumentExtractionResult)
async def extract_document(file: UploadFile = File(...)):
    """
    Upload a Tunisian bank document (PDF or image) and get structured JSON data.

    Supports:
    - Relevé Bancaire (Bank Statement)
    - Avis de Débit / Crédit
    - Attestation Bancaire

    Banks supported: STB, BIAT, BNA, Attijari, BH, UIB, Amen Bank,
                     BT, UBCI, QNB, Zitouna, Al Baraka, Wifak, and more.
    """
    try:
        file_bytes = await file.read()
        filename = file.filename or "document.pdf"

        # Step 1: OCR - Extract text from document
        raw_text = ocr_service.extract_text_from_file(file_bytes, filename)

        if not raw_text or len(raw_text.strip()) < 10:
            raise HTTPException(
                status_code=422,
                detail="Could not extract text from document. Please upload a clearer scan.",
            )

        # Step 2: Classify document type
        doc_type, doc_confidence = document_classifier.classify(raw_text)

        # Step 3: Detect the bank
        bank_code, bank_confidence = bank_detector.detect_bank(raw_text)
        bank_info_dict = bank_detector.get_bank_info(bank_code)
        bank_info = BankInfo(**bank_info_dict)

        # Step 4: Extract fields
        account_info = field_extractor.extract_account_info(raw_text)
        period = field_extractor.extract_period(raw_text)
        balances = field_extractor.extract_balances(raw_text)
        transactions = field_extractor.extract_transactions(raw_text)
        totals = field_extractor.extract_totals(raw_text)

        # Step 5: Build response
        result = DocumentExtractionResult(
            document_type=doc_type,
            confidence=round((doc_confidence + bank_confidence) / 2, 2),
            bank=bank_info,
            account=account_info,
            period=period,
            opening_balance=balances.get("opening_balance"),
            closing_balance=balances.get("closing_balance"),
            total_debit=totals.get("total_debit"),
            total_credit=totals.get("total_credit"),
            transactions=transactions,
            raw_text_preview=raw_text[:500],
        )

        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Processing error: {str(e)}")


@app.get("/banks")
async def list_supported_banks():
    """List all supported Tunisian banks"""
    from models.banks import TUNISIAN_BANKS
    return {
        code: {"name": info["full_name"], "rib_prefix": info["rib_prefix"]}
        for code, info in TUNISIAN_BANKS.items()
    }


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "Tunisian Bank Document Extractor"}