from __future__ import annotations

import hashlib
import re
from pathlib import Path

from specimpact.models import Chunk, Document, Section


def load_document(
    path: Path, *, source_key: str | None = None
) -> tuple[Document, list[Section], list[Chunk]]:
    if path.suffix.lower() not in {".md", ".txt"}:
        raise ValueError(f"Unsupported document type: {path.suffix}")
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    title = next((line.lstrip("# ").strip() for line in lines if line.strip()), path.stem)
    path_key = source_key or path.name
    slug = re.sub(r"[^a-z0-9]+", "_", path.stem.lower()).strip("_") or "document"
    path_hash = hashlib.sha1(path_key.encode()).hexdigest()[:8]
    document_id = f"doc.{slug}.{path_hash}"
    sections = parse_sections(document_id, lines)
    chunks = chunk_sections(document_id, sections, lines)
    document = Document(
        document_id=document_id,
        path=path.as_posix(),
        title=title,
        hash=hashlib.sha256(text.encode()).hexdigest(),
    )
    return document, sections, chunks


def parse_sections(document_id: str, lines: list[str]) -> list[Section]:
    headings: list[tuple[int, int, str]] = []
    for number, line in enumerate(lines, start=1):
        match = re.match(r"^(#{1,6})\s+(.+)$", line)
        if match:
            headings.append((number, len(match.group(1)), match.group(2).strip()))
    if not headings:
        headings.append((1, 1, "Document"))
    result = []
    for index, (start, level, heading) in enumerate(headings):
        end = headings[index + 1][0] - 1 if index + 1 < len(headings) else max(len(lines), start)
        result.append(
            Section(
                section_id=f"sec.{document_id.removeprefix('doc.')}.{index + 1:03d}",
                document_id=document_id,
                heading=heading,
                level=level,
                line_start=start,
                line_end=end,
            )
        )
    return result


def chunk_sections(document_id: str, sections: list[Section], lines: list[str]) -> list[Chunk]:
    return [
        Chunk(
            chunk_id=f"chunk.{document_id.removeprefix('doc.')}.{index:03d}",
            document_id=document_id,
            section_id=section.section_id,
            text="\n".join(lines[section.line_start - 1 : section.line_end]).strip(),
            line_start=section.line_start,
            line_end=section.line_end,
        )
        for index, section in enumerate(sections, start=1)
    ]
