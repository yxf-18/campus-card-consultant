from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ParsedDocument:
    text: str
    pages: list[tuple[int | None, str]]


def parse_document(path: Path, suffix: str) -> ParsedDocument:
    suffix = suffix.lower().lstrip(".")
    if suffix == "pdf":
        import fitz
        pages: list[tuple[int | None, str]] = []
        with fitz.open(path) as pdf:
            for index, page in enumerate(pdf, start=1):
                pages.append((index, page.get_text("text").strip()))
        return ParsedDocument("\n\n".join(text for _, text in pages if text), pages)
    if suffix == "docx":
        from docx import Document
        document = Document(path)
        parts = [paragraph.text.strip() for paragraph in document.paragraphs if paragraph.text.strip()]
        for table in document.tables:
            for row in table.rows:
                values = [cell.text.strip() for cell in row.cells if cell.text.strip()]
                if values:
                    parts.append(" | ".join(values))
        text = "\n\n".join(parts)
        return ParsedDocument(text, [(None, text)])
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("gb18030", errors="ignore")
    return ParsedDocument(text.strip(), [(None, text.strip())])


def _split_long(text: str, max_chars: int, overlap: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    pieces, start = [], 0
    while start < len(text):
        end = min(len(text), start + max_chars)
        if end < len(text):
            boundary = max(text.rfind("。", start, end), text.rfind("\n", start, end), text.rfind("；", start, end))
            if boundary > start + max_chars // 2:
                end = boundary + 1
        pieces.append(text[start:end].strip())
        if end >= len(text):
            break
        start = max(start + 1, end - overlap)
    return [piece for piece in pieces if piece]


def chunk_document(pages: list[tuple[int | None, str]], max_chars: int = 700,
                   overlap: int = 100) -> list[dict]:
    chunks: list[dict] = []
    current_heading = ""
    for page_no, page_text in pages:
        for paragraph in re.split(r"\n\s*\n", page_text):
            paragraph = paragraph.strip()
            if not paragraph:
                continue
            if paragraph.startswith("#"):
                current_heading = paragraph.lstrip("# ").strip()[:500]
            for piece in _split_long(paragraph, max_chars, overlap):
                chunks.append({"chunk_index": len(chunks), "heading_path": current_heading or None,
                               "page_no": page_no, "content": piece, "char_count": len(piece)})
    return chunks
