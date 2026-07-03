"""Golden expectations over the synthetic corpus (docs/03 §7).

Baselines are enforced in CI: a change that drops retrieval hit-rate or
classification accuracy below these bars fails the build. Bars are set for
the *local* deterministic providers (lexical-dominant retrieval, heuristic
classification); runs with real providers should clear them with room and
can ratchet them up.
"""

from dataclasses import dataclass, field


@dataclass
class RetrievalCase:
    query: str
    expected_filename: str
    within_top: int = 3
    # Any of these substrings appearing in the hit text also counts — some
    # answers legitimately live in more than one document.
    accept_text: list[str] = field(default_factory=list)


RETRIEVAL_CASES = [
    RetrievalCase(
        "how are new claims assigned to adjusters",
        "adjuster-assignment-procedure.docx",
    ),
    RetrievalCase(
        "severity tiers for triage",
        "claims-triage-policy.md",
        accept_text=["Severity 1", "severity tiers"],
    ),
    RetrievalCase(
        "duplicate data entry between CallTrak and ClaimCore",
        "claims-intake-sop.md",
        accept_text=["re-enter", "rekeying", "Duplicate entry"],
    ),
    RetrievalCase(
        "what happens when fraud is suspected",
        "fraud-referral-procedure.docx",
    ),
    RetrievalCase(
        "subrogation referral steps",
        "subrogation-process.md",
    ),
    RetrievalCase(
        "escalation of complex claims",
        "adjuster-assignment-procedure.docx",
        accept_text=["Complex Claims", "escalat"],
    ),
    RetrievalCase(
        "vendor invoice approval thresholds",
        "vendor-invoice-approval.pdf",
    ),
    RetrievalCase(
        "action items from the ops weekly meeting",
        "ops-weekly-2026-05-12.md",
    ),
    RetrievalCase(
        "what does FNOL mean",
        "claims-glossary.txt",
    ),
    RetrievalCase(
        "monthly claims volume and registration time",
        "claims-volume-report.xlsx",
    ),
]

RETRIEVAL_HIT_RATE_BAR = 0.8

# Filenames the classifier must label correctly with local heuristics; the
# accuracy bar applies across this set.
CLASSIFICATION_EXPECTED = {
    "claims-intake-sop.md": "sop",
    "adjuster-assignment-procedure.docx": "sop",
    "claims-triage-policy.md": "policy",
    "ops-weekly-2026-05-12.md": "meeting_notes",
    "fraud-referral-procedure.docx": "sop",
}
CLASSIFICATION_ACCURACY_BAR = 0.8

# Planted PII in customer-complaints-log.xlsx: minimum counts by type.
PII_EXPECTED_MIN = {"email": 4, "phone": 4, "policy_number": 4, "claim_number": 4}
