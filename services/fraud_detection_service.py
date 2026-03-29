"""
Fraud Detection Service for Tunisian Financial Documents

Analyses extracted data from invoices (factures) and bank statements
(relevés bancaires) and returns a list of fraud alerts together with
an overall fraud score (0–100) and a risk level.

Risk levels:
  0–20  → LOW
  21–50 → MEDIUM
  51–80 → HIGH
  81–100→ CRITICAL
"""

import math
import re
from collections import Counter
from datetime import datetime
from typing import List, Optional

from utils.rib_parser import TUNISIAN_BANK_CODES, parse_rib

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VALID_TVA_RATES = {0.07, 0.13, 0.19}   # Standard Tunisian VAT rates
STANDARD_TIMBRE = 1.000                  # Standard Tunisian timbre fiscal (TND)
HIGH_VALUE_THRESHOLD = 50_000.0          # Flag transactions above this amount (TND)

# Benford's Law expected first-digit frequencies
BENFORD = {
    1: 0.301,
    2: 0.176,
    3: 0.125,
    4: 0.097,
    5: 0.079,
    6: 0.067,
    7: 0.058,
    8: 0.051,
    9: 0.046,
}

# Severity weights used to compute the fraud score
SEVERITY_WEIGHTS = {
    "CRITICAL": 30,
    "HIGH": 15,
    "MEDIUM": 8,
    "LOW": 3,
}

WEEKDAY_NAMES = [
    "Monday", "Tuesday", "Wednesday", "Thursday",
    "Friday", "Saturday", "Sunday",
]


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _safe_float(value) -> float:
    """Return float or 0.0 if value is None / non-numeric."""
    try:
        return float(value) if value is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


# ---------------------------------------------------------------------------
# Main service class
# ---------------------------------------------------------------------------

class FraudDetectionService:
    """
    Run rule-based fraud checks on extracted Tunisian document data.

    Usage:
        detector = FraudDetectionService()
        report = detector.analyze(extracted_data)
        # report = {"alerts": [...], "fraud_score": 42, "risk_level": "MEDIUM"}
    """

    def analyze(self, data: dict) -> dict:
        """
        Run all applicable fraud checks and return a report.

        Returns:
            {
              "alerts": List[dict],
              "fraud_score": int (0–100),
              "risk_level": str
            }
        """
        alerts: List[dict] = []
        doc_type = data.get("type", "")

        # ----- Checks for both document types -----
        alerts += self._check_rib(data)

        if doc_type == "facture":
            alerts += self._check_matricule_fiscal(data)
            alerts += self._check_tva_consistency(data)
            alerts += self._check_arithmetic_facture(data)
            alerts += self._check_date_anomalies_facture(data)
            alerts += self._check_timbre_fiscal(data)
            alerts += self._check_high_value_invoice(data)

        elif doc_type == "releve_bancaire":
            alerts += self._check_balance_consistency(data)
            alerts += self._check_duplicate_transactions(data)
            alerts += self._check_date_anomalies_transactions(data)
            alerts += self._check_high_value_transactions(data)
            alerts += self._check_benford_law(data)

        fraud_score = self._compute_score(alerts)
        risk_level = self._risk_level(fraud_score)

        return {
            "alerts": alerts,
            "fraud_score": fraud_score,
            "risk_level": risk_level,
        }

    # ------------------------------------------------------------------
    # Shared checks
    # ------------------------------------------------------------------

    def _check_rib(self, data: dict) -> List[dict]:
        alerts = []
        rib_raw = data.get("rib")
        if not rib_raw:
            return alerts

        parsed = parse_rib(rib_raw)
        rib_clean = parsed["rib_clean"]

        if len(rib_clean) != 20:
            alerts.append({
                "level": "HIGH",
                "type": "INVALID_RIB_LENGTH",
                "message": (
                    f"RIB '{rib_raw}' should contain 20 digits, "
                    f"found {len(rib_clean)}."
                ),
            })
        elif not parsed["is_valid"]:
            alerts.append({
                "level": "MEDIUM",
                "type": "UNKNOWN_BANK_CODE",
                "message": (
                    f"Bank code '{parsed['bank_code']}' in RIB '{rib_raw}' "
                    "is not a recognised Tunisian bank code."
                ),
            })
        return alerts

    # ------------------------------------------------------------------
    # Invoice-specific checks
    # ------------------------------------------------------------------

    def _check_matricule_fiscal(self, data: dict) -> List[dict]:
        """Validate Tunisian matricule fiscal: 7-digit number / Letter / Letter / Letter / 3-digit number."""
        alerts = []
        mf = (data.get("emetteur") or {}).get("matricule_fiscal") or ""
        if not mf:
            return alerts
        # Accept formats like "1234567/A/B/C/000" or with spaces
        cleaned = mf.replace(" ", "")
        pattern = r"^\d{7}/[A-Z]/[A-Z]/[A-Z]/\d{3}$"
        if not re.match(pattern, cleaned):
            alerts.append({
                "level": "HIGH",
                "type": "INVALID_MATRICULE_FISCAL",
                "message": (
                    f"Matricule fiscal '{mf}' does not match the expected "
                    "Tunisian format (1234567/A/B/C/000)."
                ),
            })
        return alerts

    def _check_tva_consistency(self, data: dict) -> List[dict]:
        """Verify the applied TVA rate is a standard Tunisian rate."""
        alerts = []
        ht = _safe_float(data.get("montant_ht"))
        tva = _safe_float(data.get("montant_tva"))
        if ht <= 0 or tva <= 0:
            return alerts
        rate = round(tva / ht, 2)
        if rate not in VALID_TVA_RATES:
            alerts.append({
                "level": "HIGH",
                "type": "INVALID_TVA_RATE",
                "message": (
                    f"Computed TVA rate {rate * 100:.1f}% is not a standard "
                    "Tunisian rate (7%, 13%, 19%)."
                ),
            })
        return alerts

    def _check_arithmetic_facture(self, data: dict) -> List[dict]:
        """Verify: montant_ht + montant_tva + timbre_fiscal ≈ montant_ttc."""
        alerts = []
        ht = _safe_float(data.get("montant_ht"))
        tva = _safe_float(data.get("montant_tva"))
        timbre = _safe_float(data.get("timbre_fiscal"))
        ttc = _safe_float(data.get("montant_ttc"))
        if ttc == 0 or ht == 0:
            return alerts
        expected = round(ht + tva + timbre, 3)
        if abs(expected - ttc) > 0.01:
            alerts.append({
                "level": "CRITICAL",
                "type": "ARITHMETIC_MISMATCH",
                "message": (
                    f"HT({ht}) + TVA({tva}) + Timbre({timbre}) = {expected} "
                    f"≠ TTC({ttc}). Difference: {abs(expected - ttc):.3f} TND."
                ),
            })
        return alerts

    def _check_date_anomalies_facture(self, data: dict) -> List[dict]:
        """Flag future dates or dates on weekends."""
        alerts = []
        date_str = data.get("date_facture") or ""
        if not date_str:
            return alerts
        for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"):
            try:
                doc_date = datetime.strptime(date_str, fmt)
                break
            except ValueError:
                doc_date = None
        else:
            return alerts  # unparseable date

        now = datetime.now()
        if doc_date > now:
            alerts.append({
                "level": "HIGH",
                "type": "FUTURE_DATE",
                "message": f"Invoice date '{date_str}' is in the future.",
            })
        if doc_date.weekday() >= 5:
            day_name = WEEKDAY_NAMES[doc_date.weekday()]
            alerts.append({
                "level": "LOW",
                "type": "WEEKEND_DATE",
                "message": f"Invoice is dated on a {day_name} ({date_str}).",
            })
        return alerts

    def _check_timbre_fiscal(self, data: dict) -> List[dict]:
        """Tunisian timbre fiscal is normally 1.000 TND."""
        alerts = []
        timbre = data.get("timbre_fiscal")
        if timbre is None:
            return alerts
        timbre = _safe_float(timbre)
        if timbre != 0.0 and abs(timbre - STANDARD_TIMBRE) > 0.001:
            alerts.append({
                "level": "MEDIUM",
                "type": "UNUSUAL_TIMBRE_FISCAL",
                "message": (
                    f"Timbre fiscal is {timbre:.3f} TND; "
                    f"standard value is {STANDARD_TIMBRE:.3f} TND."
                ),
            })
        return alerts

    def _check_high_value_invoice(self, data: dict) -> List[dict]:
        """Flag unusually high invoice total."""
        alerts = []
        ttc = _safe_float(data.get("montant_ttc"))
        if ttc > HIGH_VALUE_THRESHOLD:
            alerts.append({
                "level": "MEDIUM",
                "type": "HIGH_VALUE_INVOICE",
                "message": (
                    f"Invoice total {ttc:,.3f} TND exceeds the high-value "
                    f"threshold of {HIGH_VALUE_THRESHOLD:,.0f} TND."
                ),
            })
        return alerts

    # ------------------------------------------------------------------
    # Bank statement-specific checks
    # ------------------------------------------------------------------

    def _check_balance_consistency(self, data: dict) -> List[dict]:
        """Verify: solde_initial + total_credits - total_debits ≈ solde_final."""
        alerts = []
        initial = _safe_float(data.get("solde_initial"))
        final = _safe_float(data.get("solde_final"))
        credits = _safe_float(data.get("total_credits"))
        debits = _safe_float(data.get("total_debits"))

        if initial == 0 and final == 0:
            return alerts

        expected = round(initial + credits - debits, 3)
        if abs(expected - final) > 0.01:
            alerts.append({
                "level": "CRITICAL",
                "type": "BALANCE_MISMATCH",
                "message": (
                    f"Balance check failed: "
                    f"initial({initial}) + credits({credits}) - debits({debits}) "
                    f"= {expected} ≠ solde_final({final}). "
                    f"Difference: {abs(expected - final):.3f} TND."
                ),
            })
        return alerts

    def _check_duplicate_transactions(self, data: dict) -> List[dict]:
        """Detect transactions that share date, libelle, debit AND credit."""
        alerts = []
        transactions = data.get("transactions") or []
        seen: Counter = Counter()
        for tx in transactions:
            key = (
                tx.get("date"),
                (tx.get("libelle") or "").strip().lower(),
                tx.get("debit"),
                tx.get("credit"),
            )
            seen[key] += 1

        for key, count in seen.items():
            if count > 1:
                date, libelle, debit, credit = key
                amount = debit or credit
                alerts.append({
                    "level": "MEDIUM",
                    "type": "DUPLICATE_TRANSACTION",
                    "message": (
                        f"Transaction appears {count} times: "
                        f"date={date}, libelle='{libelle}', amount={amount} TND."
                    ),
                })
        return alerts

    def _check_date_anomalies_transactions(self, data: dict) -> List[dict]:
        """Flag transactions with future dates or on weekends."""
        alerts = []
        transactions = data.get("transactions") or []
        now = datetime.now()

        for tx in transactions:
            date_str = tx.get("date") or ""
            if not date_str:
                continue
            doc_date = None
            for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"):
                try:
                    doc_date = datetime.strptime(date_str, fmt)
                    break
                except ValueError:
                    continue
            if doc_date is None:
                continue

            if doc_date > now:
                alerts.append({
                    "level": "HIGH",
                    "type": "FUTURE_TRANSACTION_DATE",
                    "message": (
                        f"Transaction date '{date_str}' is in the future "
                        f"(libelle: '{tx.get('libelle', '')}')."
                    ),
                })
            if doc_date.weekday() >= 5:
                day_name = WEEKDAY_NAMES[doc_date.weekday()]
                alerts.append({
                    "level": "LOW",
                    "type": "WEEKEND_TRANSACTION",
                    "message": (
                        f"Transaction on {day_name} ({date_str}): "
                        f"'{tx.get('libelle', '')}' "
                        f"amount={tx.get('debit') or tx.get('credit')} TND."
                    ),
                })
        return alerts

    def _check_high_value_transactions(self, data: dict) -> List[dict]:
        """Flag individual transactions above the high-value threshold."""
        alerts = []
        transactions = data.get("transactions") or []
        for tx in transactions:
            for field in ("debit", "credit"):
                amount = _safe_float(tx.get(field))
                if amount > HIGH_VALUE_THRESHOLD:
                    alerts.append({
                        "level": "MEDIUM",
                        "type": "HIGH_VALUE_TRANSACTION",
                        "message": (
                            f"High-value {field} of {amount:,.3f} TND on "
                            f"{tx.get('date', 'unknown date')}: "
                            f"'{tx.get('libelle', '')}'."
                        ),
                    })
        return alerts

    def _check_benford_law(self, data: dict) -> List[dict]:
        """
        Apply Benford's Law to transaction amounts.

        If the leading-digit distribution deviates significantly from
        Benford's expected distribution (chi-squared > critical value),
        a MEDIUM alert is raised.  Requires at least 20 transactions to
        produce a meaningful result.
        """
        alerts = []
        transactions = data.get("transactions") or []
        amounts = []
        for tx in transactions:
            for field in ("debit", "credit"):
                v = _safe_float(tx.get(field))
                if v > 0:
                    amounts.append(v)

        if len(amounts) < 20:
            return alerts  # Not enough data for Benford analysis

        # Count leading digits
        observed: Counter = Counter()
        for amount in amounts:
            first_digit = int(str(amount).replace(".", "").lstrip("0")[0])
            observed[first_digit] += 1

        n = len(amounts)
        chi_sq = 0.0
        for digit in range(1, 10):
            expected_count = BENFORD[digit] * n
            actual_count = observed.get(digit, 0)
            chi_sq += (actual_count - expected_count) ** 2 / expected_count

        # Chi-squared critical value for 8 dof at p=0.05 is 15.507
        if chi_sq > 15.507:
            alerts.append({
                "level": "MEDIUM",
                "type": "BENFORD_LAW_ANOMALY",
                "message": (
                    f"Transaction amounts deviate from Benford's Law "
                    f"(chi²={chi_sq:.2f}, critical=15.51). "
                    "This may indicate fabricated amounts."
                ),
            })
        return alerts

    # ------------------------------------------------------------------
    # Scoring
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_score(alerts: List[dict]) -> int:
        """
        Compute a fraud score 0–100 based on alert severity weights.
        Score is capped at 100.
        """
        total = sum(SEVERITY_WEIGHTS.get(a.get("level", "LOW"), 0) for a in alerts)
        return min(total, 100)

    @staticmethod
    def _risk_level(score: int) -> str:
        if score >= 81:
            return "CRITICAL"
        if score >= 51:
            return "HIGH"
        if score >= 21:
            return "MEDIUM"
        return "LOW"
