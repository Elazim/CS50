"""Document classification (docs/03 §1 step 5).

The class conditions later extraction prompts (an SOP is mined differently
from a meeting transcript). LLM-backed when configured; otherwise a
transparent keyword heuristic — wrong-but-inspectable beats silently absent,
and the analyst can override doc_class in the UI later.
"""

import enum
import re

from app.ai.providers import NoLLMConfigured, get_llm_provider
from app.logging import get_logger

log = get_logger("classify")


class DocClass(enum.StrEnum):
    sop = "sop"
    policy = "policy"
    process_map = "process_map"
    meeting_notes = "meeting_notes"
    org_chart = "org_chart"
    ticket_export = "ticket_export"
    report = "report"
    email = "email"
    other = "other"


_HEURISTICS: list[tuple[DocClass, re.Pattern]] = [
    (DocClass.sop,
     re.compile(r"standard operating procedure|\bSOP\b|\bprocedure\b|work instruction", re.I)),
    (DocClass.meeting_notes, re.compile(r"meeting (notes|minutes)|attendees|action items", re.I)),
    (DocClass.process_map, re.compile(r"process (map|flow)|swimlane|flowchart|bpmn", re.I)),
    (DocClass.org_chart, re.compile(r"org(anization)? chart|reporting structure", re.I)),
    (DocClass.ticket_export, re.compile(r"ticket|jira|incident (id|number)|service ?now", re.I)),
    (DocClass.email, re.compile(r"^\s*(from|to|subject)\s*:", re.I | re.M)),
    (DocClass.policy, re.compile(r"\bpolicy\b|guideline|compliance requirement", re.I)),
    (DocClass.report, re.compile(r"\breport\b|quarterly|analysis|findings", re.I)),
]

_LLM_SYSTEM = (
    "You classify business documents. Answer with exactly one label from: "
    + ", ".join(c.value for c in DocClass)
)


def classify_document(filename: str, sample_text: str) -> DocClass:
    sample = f"{filename}\n{sample_text[:3000]}"
    try:
        provider = get_llm_provider()
        answer = provider.complete(
            system=_LLM_SYSTEM,
            user=f"Classify this document:\n\n{sample}",
            max_tokens=10,
        )
        label = answer.strip().lower().split()[0]
        if label in DocClass.__members__:
            return DocClass(label)
        log.warning("classify.llm_bad_label", label=label)
    except NoLLMConfigured:
        pass

    for doc_class, pattern in _HEURISTICS:
        if pattern.search(sample):
            return doc_class
    return DocClass.other
