import uuid

from app.ai.chunker import HARD_CAP_TOKENS, chunk_elements
from app.modules.documents.elements import DocumentElement, ElementKind


def _element(kind: ElementKind, text: str, section=None, meta=None) -> DocumentElement:
    e = DocumentElement(
        id=uuid.uuid4(),
        kind=kind,
        text=text,
        section_path=section or [],
        meta=meta or {},
        order_key=0,
    )
    return e


def test_tables_are_atomic_chunks():
    elements = [
        _element(ElementKind.paragraph, "before " * 50),
        _element(ElementKind.table, "a | b\n1 | 2"),
        _element(ElementKind.paragraph, "after " * 50),
    ]
    chunks = chunk_elements(elements)
    table_chunks = [c for c in chunks if "a | b" in c.text]
    assert len(table_chunks) == 1
    assert len(table_chunks[0].element_ids) == 1


def test_long_runs_respect_hard_cap():
    elements = [
        _element(ElementKind.paragraph, f"paragraph {i} " + "word " * 120) for i in range(30)
    ]
    chunks = chunk_elements(elements)
    assert len(chunks) > 1
    assert all(c.token_count <= HARD_CAP_TOKENS * 1.2 for c in chunks)
    # Every element lands in exactly one chunk
    seen = [eid for c in chunks for eid in c.element_ids]
    assert len(seen) == len(set(seen)) == 30


def test_breadcrumb_prefixes_chunk_text():
    elements = [
        _element(
            ElementKind.paragraph,
            "Supervisor reviews the queue.",
            section=["Assignment", "Escalation"],
        )
    ]
    chunks = chunk_elements(elements)
    assert chunks[0].text.startswith("Assignment > Escalation")
