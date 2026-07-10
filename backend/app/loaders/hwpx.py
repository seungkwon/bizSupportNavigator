"""Loader for `.hwpx` files (ZIP + OOXML-style XML format).

Freshly implemented for this project (detailed_plan.md 2.2) — see hwp.py for why
this isn't vendored from an external source. `.hwpx` uses an entirely different
container/format than `.hwp`, so it needs its own parsing logic rather than
reusing HWPLoader.
"""

import re
import zipfile
import xml.etree.ElementTree as ET

from langchain_core.document_loaders import BaseLoader
from langchain_core.documents import Document

_SECTION_PATH_RE = re.compile(r"^Contents/section(\d+)\.xml$", re.IGNORECASE)


class HWPXLoader(BaseLoader):
    def __init__(self, file_path: str):
        self.file_path = file_path

    def load(self) -> list[Document]:
        try:
            with zipfile.ZipFile(self.file_path) as archive:
                sections = self._ordered_sections(archive)
                if not sections:
                    raise RuntimeError(f"{self.file_path}: no Contents/section*.xml found")
                text = "\n".join(self._extract_section_text(archive, name) for name in sections)
        except (zipfile.BadZipFile, ET.ParseError) as exc:
            raise RuntimeError(f"{self.file_path}: failed to parse hwpx") from exc

        return [Document(page_content=text, metadata={"source": self.file_path})]

    @staticmethod
    def _ordered_sections(archive: zipfile.ZipFile) -> list[str]:
        matches = ((name, _SECTION_PATH_RE.match(name)) for name in archive.namelist())
        numbered = [(int(m.group(1)), name) for name, m in matches if m]
        return [name for _, name in sorted(numbered)]

    @staticmethod
    def _extract_section_text(archive: zipfile.ZipFile, section_name: str) -> str:
        root = ET.fromstring(archive.read(section_name))
        # hwpx text nodes are namespaced (e.g. {…}t); match by local name only.
        texts = [elem.text for elem in root.iter() if elem.tag.rsplit("}", 1)[-1] == "t" and elem.text]
        return "\n".join(texts)
