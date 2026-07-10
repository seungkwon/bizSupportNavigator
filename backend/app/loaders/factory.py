"""Attachment loader factory (detailed_plan.md 2.2 / 4.1)."""

from langchain_community.document_loaders import PyPDFLoader
from langchain_core.document_loaders import BaseLoader
from langchain_core.documents import Document

from app.loaders.hwp import HWPLoader
from app.loaders.hwpx import HWPXLoader

SUPPORTED_FORMATS = ("pdf", "hwp", "hwpx")


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
        return self.get_loader(file_path, file_format).load()
