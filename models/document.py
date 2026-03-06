"""
Pydantic models for structured JSON responses
"""
from pydantic import BaseModel
from typing import Optional, List
from datetime import date
from enum import Enum


class DocumentType(str, Enum):
    RELEVE_BANCAIRE = "releve_bancaire"
    AVIS_DEBIT = "avis_debit"
    AVIS_CREDIT = "avis_credit"
    ATTESTATION_BANCAIRE = "attestation_bancaire"
    UNKNOWN = "unknown"


class Transaction(BaseModel):
    date: Optional[str] = None
    description: Optional[str] = None
    debit: Optional[float] = None
    credit: Optional[float] = None
    balance: Optional[float] = None
    reference: Optional[str] = None


class BankInfo(BaseModel):
    bank_code: str
    bank_name: str
    bank_full_name: str
    agency: Optional[str] = None


class AccountInfo(BaseModel):
    account_holder: Optional[str] = None
    account_number: Optional[str] = None
    rib: Optional[str] = None  # Relevé d'Identité Bancaire (20 digits in Tunisia)
    iban: Optional[str] = None
    currency: Optional[str] = "TND"  # Default Tunisian Dinar


class StatementPeriod(BaseModel):
    start_date: Optional[str] = None
    end_date: Optional[str] = None


class DocumentExtractionResult(BaseModel):
    document_type: DocumentType
    confidence: float
    bank: BankInfo
    account: AccountInfo
    period: Optional[StatementPeriod] = None
    opening_balance: Optional[float] = None
    closing_balance: Optional[float] = None
    total_debit: Optional[float] = None
    total_credit: Optional[float] = None
    transactions: List[Transaction] = []
    raw_text_preview: Optional[str] = None