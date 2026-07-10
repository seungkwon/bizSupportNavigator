"""Downloads the selected announcement attachment to local storage
(detailed_plan.md 3.1 `download_attachment`)."""

import re
from pathlib import Path

import httpx

from app.core.config import get_settings

_UNSAFE_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def sanitize_filename(file_name: str) -> str:
    name = Path(file_name).name  # strips any directory components
    name = _UNSAFE_CHARS.sub("_", name).strip(" .")
    return name or "attachment"


def infer_format(file_name: str) -> str | None:
    suffix = Path(file_name).suffix.lstrip(".").lower()
    return suffix or None


def download_attachment(download_url: str, file_name: str, policy_id: str) -> str:
    settings = get_settings()
    dest_dir = Path(settings.attachment_storage_dir) / sanitize_filename(policy_id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / sanitize_filename(file_name)

    with httpx.stream("GET", download_url, timeout=60, follow_redirects=True) as response:
        response.raise_for_status()
        with open(dest_path, "wb") as f:
            for chunk in response.iter_bytes():
                f.write(chunk)

    return str(dest_path)
