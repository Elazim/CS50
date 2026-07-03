"""PDF via PyMuPDF: text blocks with a font-size heading heuristic, tables
via the built-in detector. Scanned/image-only pages are detected and
reported — the OCR lane handles them (docs/03 §1)."""

import statistics

import fitz  # PyMuPDF

from app.modules.documents.elements import ElementKind
from app.parsing.base import ParsedElement, SectionTracker, UnsupportedDocumentError


def parse_pdf(data: bytes) -> list[ParsedElement]:
    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception as exc:
        raise UnsupportedDocumentError(f"Cannot open PDF: {exc}") from exc

    elements: list[ParsedElement] = []
    sections = SectionTracker()
    body_size = _dominant_font_size(doc)
    text_seen = False

    for page_index, page in enumerate(doc):
        page_no = page_index + 1

        for table in page.find_tables().tables:
            rows = table.extract()
            if not rows:
                continue
            elements.append(
                ParsedElement(
                    kind=ElementKind.table,
                    text=_table_text(rows),
                    page=page_no,
                    section_path=sections.path,
                    table_json={"rows": rows},
                )
            )

        for block in page.get_text("dict")["blocks"]:
            if block.get("type") != 0:  # non-text (images) — OCR lane's job
                continue
            block_text, max_size, bold = _flatten_block(block)
            if not block_text:
                continue
            text_seen = True
            is_heading = body_size and (
                max_size >= body_size * 1.25 or (bold and max_size >= body_size * 1.1)
            )
            if is_heading and len(block_text) < 200:
                level = 1 if max_size >= body_size * 1.6 else 2
                sections.push(level, block_text)
                elements.append(
                    ParsedElement(
                        kind=ElementKind.heading,
                        text=block_text,
                        page=page_no,
                        section_path=sections.path,
                        meta={"level": level},
                    )
                )
            else:
                elements.append(
                    ParsedElement(
                        kind=ElementKind.paragraph,
                        text=block_text,
                        page=page_no,
                        section_path=sections.path,
                    )
                )

    if not text_seen:
        raise UnsupportedDocumentError(
            "PDF contains no extractable text (likely scanned); OCR lane not yet enabled"
        )
    return elements


def _dominant_font_size(doc: "fitz.Document") -> float:
    sizes: list[float] = []
    for page in doc:
        for block in page.get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                sizes.extend(span["size"] for span in line.get("spans", []))
        if len(sizes) > 2000:
            break
    return statistics.median(sizes) if sizes else 0.0


def _flatten_block(block: dict) -> tuple[str, float, bool]:
    parts: list[str] = []
    max_size = 0.0
    bold = False
    for line in block.get("lines", []):
        for span in line.get("spans", []):
            parts.append(span["text"])
            max_size = max(max_size, span["size"])
            bold = bold or bool(span["flags"] & 2**4)
    return " ".join(" ".join(parts).split()), max_size, bold


def _table_text(rows: list[list]) -> str:
    return "\n".join(
        " | ".join("" if cell is None else str(cell).strip() for cell in row) for row in rows
    )
