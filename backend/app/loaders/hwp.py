"""Loader for legacy `.hwp` files (HWP 5.0 binary/OLE compound-file format).

Freshly implemented for this project (detailed_plan.md 2.2) — the source project
originally slated for vendoring isn't present on this machine. Follows the same
approach: read BodyText/Section* streams from the OLE container, inflate them if
compressed, and pull text out of HWPTAG_PARA_TEXT (tag 67) records.
"""

import re
import zlib

import olefile
from langchain_core.document_loaders import BaseLoader
from langchain_core.documents import Document

_HWPTAG_PARA_TEXT = 67
_CJK_UNIFIED_RE = re.compile(r"[一-鿿]")
_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


class HWPLoader(BaseLoader):
    def __init__(self, file_path: str):
        self.file_path = file_path

    def load(self) -> list[Document]:
        if not olefile.isOleFile(self.file_path):
            raise ValueError(f"{self.file_path}: not a valid HWP (OLE) file")

        with olefile.OleFileIO(self.file_path) as ole:
            dirs = ole.listdir()
            if ["FileHeader"] not in dirs or ["\x05HwpSummaryInformation"] not in dirs:
                raise ValueError(f"{self.file_path}: missing FileHeader/HwpSummaryInformation stream")

            header = ole.openstream("FileHeader").read()
            is_compressed = bool(header[36] & 0b1)

            text_parts = [
                self._extract_section_text(ole, section, is_compressed)
                for section in self._body_sections(dirs)
            ]

        text = "\n".join(text_parts)
        text = _CJK_UNIFIED_RE.sub("", text)
        text = _CONTROL_CHAR_RE.sub("", text)
        return [Document(page_content=text, metadata={"source": self.file_path})]

    @staticmethod
    def _body_sections(dirs: list[list[str]]) -> list[str]:
        section_indices = sorted(
            int(entry[1][len("Section") :])
            for entry in dirs
            if len(entry) == 2 and entry[0] == "BodyText" and entry[1].startswith("Section")
        )
        return [f"BodyText/Section{i}" for i in section_indices]

    @staticmethod
    def _extract_section_text(ole: olefile.OleFileIO, section: str, is_compressed: bool) -> str:
        data = ole.openstream(section).read()
        if is_compressed:
            data = zlib.decompressobj(-15).decompress(data)

        pos, size = 0, len(data)
        chunks: list[str] = []
        while pos + 4 <= size:
            record_header = int.from_bytes(data[pos : pos + 4], "little")
            tag = record_header & 0x3FF
            rec_size = (record_header >> 20) & 0xFFF
            pos += 4
            if rec_size == 0xFFF:
                rec_size = int.from_bytes(data[pos : pos + 4], "little")
                pos += 4
            if pos + rec_size > size:
                break
            if tag == _HWPTAG_PARA_TEXT:
                chunks.append(data[pos : pos + rec_size].decode("utf-16-le", errors="ignore"))
            pos += rec_size
        return "\n".join(chunks)
