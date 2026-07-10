"""Attachment loader factory (detailed_plan.md 2.2 / 4.1).

HWP/HWPX support is deferred: the source project referenced by the plan
(`korean_pdf_rag_langgraph/hwp.py`, `hwpx.py`) is not available on this machine.
`pdf` is wired up now; `hwp`/`hwpx` raise NotImplementedError until those loaders
are vendored or reimplemented.
"""

from langchain_community.document_loaders import PyPDFLoader
from langchain_core.document_loaders import BaseLoader
from langchain_core.documents import Document

SUPPORTED_FORMATS = ("pdf", "hwp", "hwpx")


class AttachmentLoaderFactory:
    """Returns the langchain Loader instance matching a file format."""

    _LOADERS: dict[str, type[BaseLoader]] = {
        "pdf": PyPDFLoader,
    }

    def get_loader(self, file_path: str, file_format: str) -> BaseLoader:
        if file_format in ("hwp", "hwpx"):
            raise NotImplementedError(
                f"{file_format} loader not yet implemented (see detailed_plan.md 2.2 / 11)"
            )
        loader_cls = self._LOADERS.get(file_format)
        if loader_cls is None:
            raise ValueError(f"unsupported file format: {file_format}")
        return loader_cls(file_path)

    def load(self, file_path: str, file_format: str) -> list[Document]:
        return self.get_loader(file_path, file_format).load()
