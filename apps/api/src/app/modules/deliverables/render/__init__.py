"""Format renderers: pure functions of a deliverable spec.

Formats per deliverable type are explicit — a current-state assessment is
a document, a roadmap is a deck; rendering everything to everything would
produce artifacts nobody presents.
"""

from app.modules.deliverables.models import DeliverableType
from app.modules.deliverables.render.docx import render_docx
from app.modules.deliverables.render.md import render_md
from app.modules.deliverables.render.pdf import render_pdf
from app.modules.deliverables.render.pptx import render_pptx
from app.modules.deliverables.render.xlsx import render_xlsx

FORMATS_BY_TYPE: dict[DeliverableType, list[str]] = {
    DeliverableType.executive_summary: ["pptx", "docx", "pdf", "md"],
    DeliverableType.current_state_assessment: ["docx", "pdf", "md"],
    DeliverableType.opportunity_register: ["xlsx", "docx", "pdf", "md"],
    DeliverableType.roadmap_deck: ["pptx", "pdf", "md"],
}

_RENDERERS = {
    "pptx": render_pptx,
    "docx": render_docx,
    "xlsx": render_xlsx,
    "pdf": render_pdf,
    "md": render_md,
}

MIME_BY_FORMAT = {
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pdf": "application/pdf",
    "md": "text/markdown",
}


def render_all(deliverable_type: DeliverableType, spec: dict) -> dict[str, bytes]:
    return {
        fmt: _RENDERERS[fmt](spec) for fmt in FORMATS_BY_TYPE[deliverable_type]
    }
