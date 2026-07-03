"""Structure-aware chunking (docs/03 §1 step 4).

Rules: never split a table; prefer breaking at headings; target ~800
estimated tokens with a hard cap. Each chunk records the element ids it
covers — provenance survives chunking.
"""

from dataclasses import dataclass

from app.ai.providers import estimate_tokens
from app.modules.documents.elements import DocumentElement, ElementKind

TARGET_TOKENS = 800
HARD_CAP_TOKENS = 1100


@dataclass
class ChunkDraft:
    element_ids: list
    text: str
    token_count: int
    section_path: list
    pages: list[int]


def chunk_elements(elements: list[DocumentElement]) -> list[ChunkDraft]:
    chunks: list[ChunkDraft] = []
    current: list[DocumentElement] = []
    current_tokens = 0

    def flush() -> None:
        nonlocal current, current_tokens
        if current:
            chunks.append(_draft(current))
            current = []
            current_tokens = 0

    for element in elements:
        tokens = estimate_tokens(element.text)

        if element.kind == ElementKind.table:
            flush()
            chunks.append(_draft([element]))
            continue

        starts_section = element.kind == ElementKind.heading and (
            element.meta or {}
        ).get("level", 9) <= 2
        if current and (
            current_tokens + tokens > HARD_CAP_TOKENS
            or (starts_section and current_tokens >= TARGET_TOKENS // 2)
        ):
            flush()

        current.append(element)
        current_tokens += tokens
        if current_tokens >= TARGET_TOKENS:
            flush()

    flush()
    return chunks


def _draft(elements: list[DocumentElement]) -> ChunkDraft:
    # Prefix the section breadcrumb: it disambiguates retrieval hits pulled
    # out of context ("Escalation > Supervisor review: ...").
    breadcrumb = " > ".join(elements[0].section_path or [])
    body = "\n".join(e.text for e in elements)
    text = f"{breadcrumb}\n{body}" if breadcrumb else body
    return ChunkDraft(
        element_ids=[e.id for e in elements],
        text=text,
        token_count=estimate_tokens(text),
        section_path=elements[0].section_path or [],
        pages=sorted({e.page for e in elements if e.page is not None}),
    )
