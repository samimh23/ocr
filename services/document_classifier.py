"""
Document Classifier - Detect type of banking document
"""
import re
from models.document import DocumentType


class DocumentClassifier:
    # Keywords for each document type (French - used in Tunisian banking)
    DOCUMENT_PATTERNS = {
        DocumentType.RELEVE_BANCAIRE: [
            r"relev[ée]\s*(de\s*)?bancaire",
            r"relev[ée]\s*(de\s*)?compte",
            r"extrait\s*(de\s*)?compte",
            r"relevé",
            r"solde\s*(précédent|ancien|initial)",
            r"solde\s*(nouveau|final|actuel)",
            r"débit.*crédit.*solde",
            r"date\s*valeur",
            r"mouvement",
        ],
        DocumentType.AVIS_DEBIT: [
            r"avis\s*(de\s*)?d[ée]bit",
            r"note\s*(de\s*)?d[ée]bit",
        ],
        DocumentType.AVIS_CREDIT: [
            r"avis\s*(de\s*)?cr[ée]dit",
            r"note\s*(de\s*)?cr[ée]dit",
        ],
        DocumentType.ATTESTATION_BANCAIRE: [
            r"attestation\s*bancaire",
            r"attestation\s*(de\s*)?compte",
            r"certifie\s*que",
        ],
    }

    def classify(self, text: str) -> tuple[DocumentType, float]:
        """Classify the document type based on text content"""
        text_lower = text.lower()
        scores = {}

        for doc_type, patterns in self.DOCUMENT_PATTERNS.items():
            score = 0
            for pattern in patterns:
                matches = re.findall(pattern, text_lower)
                score += len(matches)
            scores[doc_type] = score

        if not scores or max(scores.values()) == 0:
            return DocumentType.UNKNOWN, 0.0

        best_type = max(scores, key=scores.get)
        total = sum(scores.values())
        confidence = scores[best_type] / total if total > 0 else 0.0

        return best_type, round(min(confidence, 1.0), 2)