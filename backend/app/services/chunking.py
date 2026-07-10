"""Section-based chunking for parsed attachment text (detailed_plan.md 4.2).

Splits on numbered ("1. 지원대상") and Roman-numeral (Ⅰ, Ⅱ …) section headers
common in Korean government notice documents — the pattern the plan calls out
explicitly — falling back to a single untitled section plus length-based
grouping when no headers are found or a section runs long. This is a heuristic,
not a structural parse (the loaders don't preserve document structure — see
detailed_plan.md 11 for the known accuracy tradeoff, including a confirmed gap:
some PDFs extract with no internal line breaks at all, so header lines can't be
isolated and the whole page falls back to length-based grouping).
"""

import re
from dataclasses import dataclass

from langchain_core.documents import Document

_NUMBERED_HEADER_RE = re.compile(r"^(\d{1,2}[.)]\s*\S.{0,28})$")
_ROMAN_HEADER_RE = re.compile(r"^([ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]{1,4})$")
_MAX_CHUNK_CHARS = 1500

_Line = tuple[str, "int | None"]  # (text, page_no)


@dataclass
class ChunkCandidate:
    section_title: str | None
    content: str
    page_no: int | None


class _SectionAccumulator:
    def __init__(self) -> None:
        self.sections: list[tuple[str | None, list[_Line]]] = []
        self.title: str | None = None
        self.lines: list[_Line] = []

    def add_line(self, line: str, page_no: int | None) -> None:
        header = _match_header(line)
        if header is not None:
            self.flush()
            self.title = header
            return
        self.lines.append((line, page_no))

    def flush(self) -> None:
        if self.lines:
            self.sections.append((self.title, self.lines))
        self.lines = []


def split_into_sections(documents: list[Document]) -> list[ChunkCandidate]:
    raw_sections = _split_into_raw_sections(documents)
    candidates: list[ChunkCandidate] = []
    for title, lines in raw_sections:
        for group in _group_by_length(lines, _MAX_CHUNK_CHARS):
            content = "\n".join(text for text, _ in group).strip()
            if content:
                candidates.append(ChunkCandidate(section_title=title, content=content, page_no=group[0][1]))
    return candidates


def _split_into_raw_sections(documents: list[Document]) -> list[tuple[str | None, list[_Line]]]:
    accumulator = _SectionAccumulator()
    for doc in documents:
        doc_page = doc.metadata.get("page")
        for raw_line in doc.page_content.splitlines():
            line = raw_line.strip()
            if line:
                accumulator.add_line(line, doc_page)
    accumulator.flush()
    return accumulator.sections


def _match_header(line: str) -> str | None:
    match = _NUMBERED_HEADER_RE.match(line) or _ROMAN_HEADER_RE.match(line)
    return match.group(1).strip() if match else None


def _group_by_length(lines: list[_Line], max_chars: int) -> list[list[_Line]]:
    groups: list[list[_Line]] = []
    current: list[_Line] = []
    current_len = 0
    for item in lines:
        text = item[0]
        if current and current_len + len(text) > max_chars:
            groups.append(current)
            current, current_len = [], 0
        current.append(item)
        current_len += len(text)
    if current:
        groups.append(current)
    return groups
