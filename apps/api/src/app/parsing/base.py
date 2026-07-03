"""Parser contract: bytes in, ordered ParsedElements out.

Every parser preserves document structure (headings, tables, slides) and
positional provenance (page, section path) — the citation chain starts
here (docs/03 §1).
"""

from dataclasses import dataclass, field

from app.modules.documents.elements import ElementKind


class UnsupportedDocumentError(Exception):
    pass


@dataclass
class ParsedElement:
    kind: ElementKind
    text: str
    page: int | None = None
    section_path: list[str] = field(default_factory=list)
    table_json: dict | None = None
    meta: dict = field(default_factory=dict)


class SectionTracker:
    """Maintains the heading breadcrumb while a parser walks a document."""

    def __init__(self) -> None:
        self._stack: list[tuple[int, str]] = []

    def push(self, level: int, title: str) -> None:
        while self._stack and self._stack[-1][0] >= level:
            self._stack.pop()
        self._stack.append((level, title.strip()))

    @property
    def path(self) -> list[str]:
        return [title for _, title in self._stack]
