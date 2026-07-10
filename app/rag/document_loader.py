from pathlib import Path

from docx import Document
from pypdf import PdfReader


def read_txt_or_md(path: Path):
    for encoding in ("utf-8", "utf-8-sig", "cp949"):
        try:
            text = path.read_text(encoding=encoding)
            return [{"text": text, "page": None}]
        except UnicodeDecodeError:
            continue

    text = path.read_text(encoding="utf-8", errors="replace")
    return [{"text": text, "page": None}]


def read_pdf(path: Path):
    reader = PdfReader(str(path))
    pages = []

    for page_idx, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""

        if text.strip():
            pages.append(
                {
                    "text": text,
                    "page": page_idx,
                }
            )

    return pages


def read_docx(path: Path):
    doc = Document(str(path))
    parts = [p.text for p in doc.paragraphs if p.text.strip()]

    for table in doc.tables:
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]

            if cells:
                parts.append(" | ".join(cells))

    text = "\n".join(parts)

    return [{"text": text, "page": None}]


def load_document(path: Path):
    suffix = path.suffix.lower()

    if suffix in [".txt", ".md"]:
        return read_txt_or_md(path)

    if suffix == ".pdf":
        return read_pdf(path)

    if suffix == ".docx":
        return read_docx(path)

    return []
