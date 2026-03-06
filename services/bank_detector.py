"""
Bank Detection Service - Identify which Tunisian bank issued the document
Uses keyword matching + RIB prefix detection
"""
import re
from typing import Optional, Tuple
from models.banks import TUNISIAN_BANKS


class BankDetector:
    def __init__(self):
        self.banks = TUNISIAN_BANKS

    def detect_bank(self, text: str) -> Tuple[Optional[str], float]:
        """
        Detect the bank from extracted text.
        Returns (bank_code, confidence)
        """
        text_lower = text.lower()

        # Method 1: Keyword matching (highest confidence)
        best_match = None
        best_score = 0

        for code, info in self.banks.items():
            for keyword in info["keywords"]:
                if keyword in text_lower:
                    # Longer keyword matches get higher confidence
                    score = len(keyword) / 10.0
                    if score > best_score:
                        best_score = score
                        best_match = code

        if best_match and best_score > 0.3:
            return best_match, min(best_score + 0.5, 1.0)

        # Method 2: RIB prefix detection
        # Tunisian RIB format: XX XXX XXXXXXXX XX (20 digits)
        rib_pattern = r'\b(\d{2})\s*\d{3}\s*\d{8}\s*\d{2}\b'
        rib_matches = re.findall(rib_pattern, text.replace(" ", "  "))

        # Also try contiguous 20-digit numbers
        rib_pattern_2 = r'\b(\d{20})\b'
        for match in re.findall(rib_pattern_2, text.replace(" ", "")):
            prefix = match[:2]
            for code, info in self.banks.items():
                if info["rib_prefix"] == prefix:
                    return code, 0.7

        return best_match, max(best_score, 0.3) if best_match else ("UNKNOWN", 0.0)

    def get_bank_info(self, bank_code: str) -> dict:
        """Get full bank information"""
        if bank_code in self.banks:
            info = self.banks[bank_code]
            return {
                "bank_code": bank_code,
                "bank_name": bank_code,
                "bank_full_name": info["full_name"],
            }
        return {
            "bank_code": "UNKNOWN",
            "bank_name": "Unknown",
            "bank_full_name": "Unknown Bank",
        }