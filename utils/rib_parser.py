"""
Tunisian RIB (Relevé d'Identité Bancaire) Parser

Tunisian RIB format: 20 digits
  XX  XXX  XXXXXXXXXXXXXXXX  X  XX
  |   |    |                 |  |
  |   |    |                 |  check key (2 digits)
  |   |    account number (13 digits in practice, but varies)
  |   agence code (3 digits)
  bank code (2 digits)

Example: 08 303 0002810013616 47
  bank_code = "08"  → BIAT
  agence    = "303"
  account   = remaining digits before check key
"""

import re
from typing import Optional

# Tunisian bank codes per the Banque Centrale de Tunisie
TUNISIAN_BANK_CODES = {
    "01": "STB",
    "02": "BNA",
    "03": "BH",
    "04": "BFPME",
    "05": "BT",
    "06": "CITI_BANK",
    "07": "AMEN_BANK",
    "08": "BIAT",
    "09": "ATTIJARI",
    "10": "ATB",
    "11": "UIB",
    "12": "UBCI",
    "14": "BTE",
    "16": "QNB",
    "17": "BTK",
    "20": "BTL",
    "21": "TSB",
    "24": "ABC",
    "25": "ZITOUNA",
    "26": "AL_BARAKA",
    "28": "WIFAK",
}


def clean_rib(raw_rib: str) -> str:
    """Remove all non-digit characters from a RIB string."""
    return re.sub(r"\D", "", raw_rib)


def parse_rib(raw_rib: str) -> dict:
    """
    Parse a Tunisian RIB string into its components.

    Args:
        raw_rib: RIB string, possibly with spaces/dashes
                 e.g. "08 303 00028 10 01361 6 47"

    Returns:
        dict with keys: bank_code, bank_name, agence, account_number,
                        check_key, rib_clean, is_valid
    """
    rib_clean = clean_rib(raw_rib)

    result = {
        "bank_code": None,
        "bank_name": None,
        "agence": None,
        "account_number": None,
        "check_key": None,
        "rib_clean": rib_clean,
        "is_valid": False,
    }

    if len(rib_clean) != 20:
        return result

    result["bank_code"] = rib_clean[0:2]
    result["agence"] = rib_clean[2:5]
    result["account_number"] = rib_clean[5:18]
    result["check_key"] = rib_clean[18:20]
    result["bank_name"] = TUNISIAN_BANK_CODES.get(result["bank_code"])
    result["is_valid"] = result["bank_code"] in TUNISIAN_BANK_CODES

    return result


def format_rib(raw_rib: str) -> Optional[str]:
    """
    Return a cleanly formatted RIB string (groups separated by spaces)
    in the canonical Tunisian form: XX XXX XXXXXXXXXXXXX XX

    Returns None if the RIB does not have exactly 20 digits.
    """
    rib_clean = clean_rib(raw_rib)
    if len(rib_clean) != 20:
        return None
    return f"{rib_clean[0:2]} {rib_clean[2:5]} {rib_clean[5:18]} {rib_clean[18:20]}"


def validate_rib(raw_rib: str) -> bool:
    """
    Validate that a RIB string represents a known Tunisian bank and
    has exactly 20 digits.
    """
    parsed = parse_rib(raw_rib)
    return parsed["is_valid"]
