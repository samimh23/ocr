"""
OCR Service - Extract text from scanned bank documents
Supports PDF and image formats
"""
import pytesseract
from PIL import Image
from pdf2image import convert_from_path, convert_from_bytes
import io
from typing import Union


class OCRService:
    def __init__(self, lang: str = "fra+ara"):
        """
        Initialize OCR with French + Arabic support
        (Tunisian bank statements are typically in French)
        """
        self.lang = lang

    def extract_text_from_image(self, image: Image.Image) -> str:
        """Extract text from a PIL Image"""
        text = pytesseract.image_to_string(image, lang=self.lang)
        return text.strip()

    def extract_text_from_pdf_bytes(self, pdf_bytes: bytes) -> str:
        """Extract text from PDF bytes (uploaded file)"""
        images = convert_from_bytes(pdf_bytes, dpi=300)
        full_text = ""
        for page_image in images:
            full_text += self.extract_text_from_image(page_image) + "\n"
        return full_text.strip()

    def extract_text_from_file(self, file_bytes: bytes, filename: str) -> str:
        """Auto-detect file type and extract text"""
        lower = filename.lower()
        if lower.endswith(".pdf"):
            return self.extract_text_from_pdf_bytes(file_bytes)
        elif lower.endswith((".png", ".jpg", ".jpeg", ".tiff", ".bmp")):
            image = Image.open(io.BytesIO(file_bytes))
            return self.extract_text_from_image(image)
        else:
            raise ValueError(f"Unsupported file format: {filename}")