"""Plain text and Markdown."""

import re

from app.modules.documents.elements import ElementKind
from app.parsing.base import ParsedElement, SectionTracker

_MD_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_MD_LIST = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(.*)$")


def parse_text(data: bytes, *, markdown: bool) -> list[ParsedElement]:
    text = data.decode("utf-8", errors="replace")
    elements: list[ParsedElement] = []
    sections = SectionTracker()
    buffer: list[str] = []

    def flush() -> None:
        if buffer:
            elements.append(
                ParsedElement(
                    kind=ElementKind.paragraph,
                    text=" ".join(buffer).strip(),
                    section_path=sections.path,
                )
            )
            buffer.clear()

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            flush()
            continue
        heading = _MD_HEADING.match(line) if markdown else None
        if heading:
            flush()
            level, title = len(heading.group(1)), heading.group(2)
            sections.push(level, title)
            elements.append(
                ParsedElement(
                    kind=ElementKind.heading,
                    text=title,
                    section_path=sections.path,
                    meta={"level": level},
                )
            )
            continue
        list_item = _MD_LIST.match(line) if markdown else None
        if list_item:
            flush()
            elements.append(
                ParsedElement(
                    kind=ElementKind.list_item,
                    text=list_item.group(1).strip(),
                    section_path=sections.path,
                )
            )
            continue
        buffer.append(line.strip())
    flush()
    return [e for e in elements if e.text]
