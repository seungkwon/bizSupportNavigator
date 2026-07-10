"""Attachment loader factory (detailed_plan.md 2.2 / 4.1)."""

from langchain_community.document_loaders import PyPDFLoader
from langchain_core.document_loaders import BaseLoader
from langchain_core.documents import Document

from app.loaders.hwp import HWPLoader
from app.loaders.hwpx import HWPXLoader

SUPPORTED_FORMATS = ("pdf", "hwp", "hwpx")

# bizinfo attachment filenames aren't always trustworthy about their own format:
# confirmed in Milestone 9 integration testing, a real `*.hwpx`-named download
# turned out to be OLE-format HWP 5.0 content (magic bytes below), which
# HWPXLoader can't open (it's not a ZIP). Since hwp/hwpx share no container
# structure, sniffing these two signatures is enough to tell them apart
# regardless of what the filename claims.
_OLE_SIGNATURE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
_ZIP_SIGNATURE = b"PK\x03\x04"


def _sniff_hwp_variant(file_path: str, declared_format: str) -> str:
    if declared_format not in ("hwp", "hwpx"):
        return declared_format
    with open(file_path, "rb") as f:
        head = f.read(8)
    if head.startswith(_OLE_SIGNATURE):
        return "hwp"
    if head.startswith(_ZIP_SIGNATURE):
        return "hwpx"
    return declared_format


class AttachmentLoaderFactory:
    """Returns the langchain Loader instance matching a file format."""

    _LOADERS: dict[str, type[BaseLoader]] = {
        "pdf": PyPDFLoader,
        "hwp": HWPLoader,
        "hwpx": HWPXLoader,
    }

    def get_loader(self, file_path: str, file_format: str) -> BaseLoader:
        loader_cls = self._LOADERS.get(file_format)
        if loader_cls is None:
            raise ValueError(f"unsupported file format: {file_format}")
        return loader_cls(file_path)

    def load(self, file_path: str, file_format: str) -> list[Document]:
        actual_format = _sniff_hwp_variant(file_path, file_format)
        return self.get_loader(file_path, actual_format).load()
