"""DOCX via python-docx: heading styles drive the section breadcrumb;
tables are preserved as structured rows."""

import io
import re

import docx
from docx.document import Document as DocxDocument
from docx.table import Table
from docx.text.paragraph import Paragraph

from app.modules.documents.elements import ElementKind
from app.parsing.base import ParsedElement, SectionTracker, UnsupportedDocumentError

_HEADING_STYLE = re.compile(r"heading\s*(\d)", re.IGNORECASE)


def parse_docx(data: bytes) -> list[ParsedElement]:
    try:
        doc = docx.Document(io.BytesIO(data))
    except Exception as exc:
        raise UnsupportedDocumentError(f"Cannot open DOCX: {exc}") from exc

    elements: list[ParsedElement] = []
    sections = SectionTracker()

    for item in _iter_body(doc):
        if isinstance(item, Paragraph):
            text = " ".join(item.text.split())
            if not text:
                continue
            style = item.style.name if item.style else ""
            match = _HEADING_STYLE.match(style)
            if match:
                level = int(match.group(1))
                sections.push(level, text)
                elements.append(
                    ParsedElement(
                        kind=ElementKind.heading,
                        text=text,
                        section_path=sections.path,
                        meta={"level": level},
                    )
                )
            elif style.startswith("List") or item._p.xpath("./w:pPr/w:numPr"):
                elements.append(
                    ParsedElement(
                        kind=ElementKind.list_item, text=text, section_path=sections.path
                    )
                )
            else:
                elements.append(
                    ParsedElement(
                        kind=ElementKind.paragraph, text=text, section_path=sections.path
                    )
                )
        elif isinstance(item, Table):
            rows = [[cell.text.strip() for cell in row.cells] for row in item.rows]
            if not any(any(row) for row in rows):
                continue
            elements.append(
                ParsedElement(
                    kind=ElementKind.table,
                    text="\n".join(" | ".join(row) for row in rows),
                    section_path=sections.path,
                    table_json={"rows": rows},
                )
            )
    return elements


def _iter_body(doc: DocxDocument):
    """Paragraphs and tables in true document order."""
    parent = doc.element.body
    for child in parent.iterchildren():
        if child.tag.endswith("}p"):
            yield Paragraph(child, doc)
        elif child.tag.endswith("}tbl"):
            yield Table(child, doc)
