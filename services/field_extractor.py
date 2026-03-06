"""
Field Extractor - Extract financial data from Tunisian bank statements
Handles various formats from different Tunisian banks
"""
import re
from typing import List, Optional
from models.document import Transaction, AccountInfo, StatementPeriod


class FieldExtractor:

    def extract_account_info(self, text: str) -> AccountInfo:
        """Extract account holder name, account number, RIB, IBAN"""
        account = AccountInfo()

        # Extract account holder name
        # Common patterns: "Nom: ...", "Titulaire: ...", "Client: ..."
        name_patterns = [
            r"(?:titulaire|nom|client|raison\s*sociale)\s*[:\-]\s*(.+)",
            r"(?:Mr|Mme|M\.)\s+([A-ZÀ-Ü][a-zà-ü]+(?:\s+[A-ZÀ-Ü][a-zà-ü]+)*)",
        ]
        for pattern in name_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                account.account_holder = match.group(1).strip()
                break

        # Extract RIB (20 digits for Tunisia)
        rib_patterns = [
            r"(?:RIB|R\.I\.B)\s*[:\-]?\s*(\d[\d\s]{18,25}\d)",
            r"\b(\d{2}\s?\d{3}\s?\d{8}\s?\d{2})\b",
        ]
        for pattern in rib_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                account.rib = re.sub(r'\s', '', match.group(1))
                break

        # Extract IBAN (Tunisia: TN59 + 20 digits)
        iban_match = re.search(r"(?:IBAN)\s*[:\-]?\s*(TN\d{2}\s?\d{4}\s?\d{4}\s?\d{4}\s?\d{4}\s?\d{4})", text, re.IGNORECASE)
        if iban_match:
            account.iban = re.sub(r'\s', '', iban_match.group(1))

        # Extract account number
        acct_patterns = [
            r"(?:compte|n[°o]\s*compte|account)\s*[:\-]?\s*(\d[\d\s\-]{5,20}\d)",
            r"(?:numéro)\s*[:\-]?\s*(\d[\d\s\-]{5,20}\d)",
        ]
        for pattern in acct_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                account.account_number = re.sub(r'[\s\-]', '', match.group(1))
                break

        # Detect currency
        if re.search(r'\bEUR\b', text):
            account.currency = "EUR"
        elif re.search(r'\bUSD\b', text):
            account.currency = "USD"
        else:
            account.currency = "TND"

        return account

    def extract_period(self, text: str) -> Optional[StatementPeriod]:
        """Extract statement period (start and end dates)"""
        # Common date formats in Tunisia: DD/MM/YYYY or DD-MM-YYYY
        period_patterns = [
            r"(?:période|du)\s*[:\-]?\s*(\d{2}[\/\-]\d{2}[\/\-]\d{4})\s*(?:au|à|-)\s*(\d{2}[\/\-]\d{2}[\/\-]\d{4})",
            r"(\d{2}[\/\-]\d{2}[\/\-]\d{4})\s*(?:au|à|[-–])\s*(\d{2}[\/\-]\d{2}[\/\-]\d{4})",
        ]
        for pattern in period_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return StatementPeriod(
                    start_date=match.group(1),
                    end_date=match.group(2),
                )
        return None

    def extract_balances(self, text: str) -> dict:
        """Extract opening and closing balances"""
        result = {}

        opening_patterns = [
            r"(?:solde\s*(?:précédent|ancien|initial|début|d[ée]biteur))\s*[:\-]?\s*([\d\s,.]+)",
            r"(?:ancien\s*solde)\s*[:\-]?\s*([\d\s,.]+)",
        ]
        for pattern in opening_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                result["opening_balance"] = self._parse_amount(match.group(1))
                break

        closing_patterns = [
            r"(?:solde\s*(?:nouveau|final|actuel|fin|cr[ée]diteur))\s*[:\-]?\s*([\d\s,.]+)",
            r"(?:nouveau\s*solde)\s*[:\-]?\s*([\d\s,.]+)",
        ]
        for pattern in closing_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                result["closing_balance"] = self._parse_amount(match.group(1))
                break

        return result

    def extract_transactions(self, text: str) -> List[Transaction]:
        """Extract individual transactions from the statement"""
        transactions = []

        # Pattern: DATE DESCRIPTION DEBIT CREDIT BALANCE
        # Tunisian format typically: DD/MM/YYYY or DD/MM
        line_pattern = (
            r"(\d{2}[\/\-]\d{2}(?:[\/\-]\d{2,4})?)"  # Date
            r"\s+(.+?)"                                   # Description
            r"\s+([\d\s,.]+(?:D)?)"                       # Debit or Credit
            r"(?:\s+([\d\s,.]+))?"                         # Balance (optional)
        )

        for match in re.finditer(line_pattern, text):
            tx = Transaction(
                date=match.group(1).strip(),
                description=match.group(2).strip(),
            )
            amount_1 = self._parse_amount(match.group(3))
            amount_2 = self._parse_amount(match.group(4)) if match.group(4) else None

            # Determine if debit or credit based on column position or markers
            if match.group(3) and "D" in match.group(3).upper():
                tx.debit = amount_1
            elif amount_2 is not None:
                tx.debit = amount_1 if amount_1 else None
                tx.balance = amount_2
            else:
                tx.credit = amount_1

            transactions.append(tx)

        return transactions

    def extract_totals(self, text: str) -> dict:
        """Extract total debit and credit sums"""
        result = {}

        total_debit = re.search(
            r"(?:total\s*d[ée]bit|total\s*mouvements?\s*d[ée]bit)\s*[:\-]?\s*([\d\s,.]+)",
            text, re.IGNORECASE
        )
        if total_debit:
            result["total_debit"] = self._parse_amount(total_debit.group(1))

        total_credit = re.search(
            r"(?:total\s*cr[ée]dit|total\s*mouvements?\s*cr[ée]dit)\s*[:\-]?\s*([\d\s,.]+)",
            text, re.IGNORECASE
        )
        if total_credit:
            result["total_credit"] = self._parse_amount(total_credit.group(1))

        return result

    @staticmethod
    def _parse_amount(raw: str) -> Optional[float]:
        """Parse Tunisian number format: 1 234,567 or 1.234,567"""
        if not raw:
            return None
        cleaned = raw.replace("D", "").strip()
        cleaned = re.sub(r'[^\d,.]', '', cleaned)
        # Tunisian/French format: comma = decimal, dot/space = thousands
        cleaned = cleaned.replace('.', '').replace(',', '.')
        try:
            return round(float(cleaned), 3)
        except ValueError:
            return None