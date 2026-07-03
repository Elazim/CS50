"""PII detection pass (docs/03 §1 step 6, docs/05 §4).

Deterministic pattern detectors for the identifier types that matter in
insurance corpora. Spans are tagged (type + offsets + masked preview) so
downstream policy can redact before external AI calls or in exports.
Raw values are never copied into tags. Name detection is deliberately
absent — regex name-guessing produces confident noise; an NER pass is an
M2+ upgrade behind this same interface.
"""

import re
from dataclasses import dataclass

_DETECTORS: dict[str, re.Pattern] = {
    "email": re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"),
    "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "phone": re.compile(r"\b(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}\b"),
    "policy_number": re.compile(r"\b(?:POL|PLCY)[-# ]?\d{6,12}\b", re.I),
    "claim_number": re.compile(r"\b(?:CLM|CLAIM)[-# ]?\d{6,12}\b", re.I),
    "dob": re.compile(r"\b(?:DOB|date of birth)[:\s]+\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b", re.I),
}


@dataclass
class PiiSpan:
    type: str
    start: int
    end: int
    preview: str  # masked: first char + asterisks


def detect_pii(text: str) -> list[PiiSpan]:
    spans: list[PiiSpan] = []
    for pii_type, pattern in _DETECTORS.items():
        for match in pattern.finditer(text):
            value = match.group()
            spans.append(
                PiiSpan(
                    type=pii_type,
                    start=match.start(),
                    end=match.end(),
                    preview=value[0] + "*" * (min(len(value), 12) - 1),
                )
            )
    spans.sort(key=lambda s: s.start)
    return spans


def summarize(span_counts: dict[str, int]) -> dict:
    return {"counts": span_counts, "total": sum(span_counts.values())}
