"""Parser units, run against the generated corpus fixtures — the nastiest
specimens we have until real-world breakage donates better ones."""

import pytest
from evals import corpus

from app.modules.documents.elements import ElementKind
from app.parsing.base import UnsupportedDocumentError
from app.parsing.registry import parse_document


def _doc(filename: str) -> corpus.CorpusDoc:
    return next(d for d in corpus.build_corpus() if d.filename == filename)


def test_markdown_structure():
    doc = _doc("claims-intake-sop.md")
    elements = parse_document(doc.filename, doc.mime, doc.data)
    headings = [e for e in elements if e.kind == ElementKind.heading]
    assert any("First Notice of Loss" in h.text for h in headings)
    # Section breadcrumbs nest under the H1
    leaf = next(e for e in elements if "Duplicate entry" in e.text)
    assert len(leaf.section_path) == 2
    assert "Known issues" in leaf.section_path[-1]
    lists = [e for e in elements if e.kind == ElementKind.list_item]
    assert len(lists) >= 5


def test_docx_headings_lists_and_tables():
    doc = _doc("adjuster-assignment-procedure.docx")
    elements = parse_document(doc.filename, doc.mime, doc.data)
    assert any(e.kind == ElementKind.heading and "Escalation" in e.text for e in elements)
    table = next(e for e in elements if e.kind == ElementKind.table)
    assert table.table_json is not None
    assert table.table_json["rows"][0][0] == "Severity"
    assert "Complex Claims unit" in table.text


def test_xlsx_sheets_are_structured_tables():
    doc = _doc("claims-volume-report.xlsx")
    elements = parse_document(doc.filename, doc.mime, doc.data)
    assert len(elements) == 1
    assert elements[0].kind == ElementKind.table
    assert elements[0].section_path == ["Volumes"]
    assert elements[0].table_json["rows"][1][0] == "2026-01"


def test_pptx_titles_bodies_notes():
    doc = _doc("transformation-kickoff.pptx")
    elements = parse_document(doc.filename, doc.mime, doc.data)
    assert any(e.kind == ElementKind.heading and "Why now" in e.text for e in elements)
    notes = [e for e in elements if e.kind == ElementKind.note]
    assert any("ops weekly" in n.text for n in notes)
    assert all(e.page is not None for e in elements)


def test_pdf_headings_and_text():
    doc = _doc("vendor-invoice-approval.pdf")
    elements = parse_document(doc.filename, doc.mime, doc.data)
    headings = [e for e in elements if e.kind == ElementKind.heading]
    assert any("Approval thresholds" in h.text for h in headings)
    body = next(e for e in elements if "2,500" in e.text)
    assert body.page == 1


def test_unsupported_format_is_explicit():
    with pytest.raises(UnsupportedDocumentError, match="Unsupported format"):
        parse_document("diagram.vsdx", "application/octet-stream", b"xx")


def test_empty_document_is_rejected():
    with pytest.raises(UnsupportedDocumentError):
        parse_document("empty.txt", "text/plain", b"   \n  \n")
