"""Route a document to its parser by MIME type / extension."""

from collections.abc import Callable

from app.parsing.base import ParsedElement, UnsupportedDocumentError
from app.parsing.docx import parse_docx
from app.parsing.pdf import parse_pdf
from app.parsing.pptx import parse_pptx
from app.parsing.text import parse_text
from app.parsing.xlsx import parse_xlsx

_BY_EXTENSION: dict[str, Callable[[bytes], list[ParsedElement]]] = {
    "pdf": parse_pdf,
    "docx": parse_docx,
    "xlsx": parse_xlsx,
    "pptx": parse_pptx,
    "txt": lambda d: parse_text(d, markdown=False),
    "md": lambda d: parse_text(d, markdown=True),
    "markdown": lambda d: parse_text(d, markdown=True),
    "csv": lambda d: parse_text(d, markdown=False),
}

_BY_MIME: dict[str, str] = {
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": "pptx",
    "text/plain": "txt",
    "text/markdown": "md",
    "text/csv": "csv",
}

SUPPORTED_EXTENSIONS = sorted(_BY_EXTENSION)


def parse_document(filename: str, mime: str, data: bytes) -> list[ParsedElement]:
    ext = _BY_MIME.get(mime) or (filename.rsplit(".", 1)[-1].lower() if "." in filename else "")
    parser = _BY_EXTENSION.get(ext)
    if parser is None:
        raise UnsupportedDocumentError(
            f"Unsupported format '{ext or mime}'. Supported: {', '.join(SUPPORTED_EXTENSIONS)}"
        )
    elements = parser(data)
    if not elements:
        raise UnsupportedDocumentError("Document parsed to zero elements")
    return elements
