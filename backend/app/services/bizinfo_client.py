"""Client for the bizinfo.go.kr Open API (detailed_plan.md 3.1 `fetch_policy_list`).

Endpoint and field names below were confirmed against the live API
(https://www.bizinfo.go.kr/uss/rss/bizinfoApi.do) rather than taken solely from the
API doc page, since that page's prose didn't spell out the exact JSON schema.
"""

from collections.abc import Iterator
from datetime import datetime

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core.config import get_settings

BIZINFO_BASE_URL = "https://www.bizinfo.go.kr/uss/rss/bizinfoApi.do"


class BizinfoApiError(RuntimeError):
    """Raised when the bizinfo API returns an application-level error (`reqErr`)."""


class BizinfoClient:
    def __init__(self, api_key: str | None = None, base_url: str = BIZINFO_BASE_URL):
        self.api_key = api_key if api_key is not None else get_settings().bizinfo_api_key
        self.base_url = base_url

    @retry(
        retry=retry_if_exception_type(httpx.TransportError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    def fetch_page(self, page_index: int, page_unit: int = 100) -> dict:
        params = {
            "crtfcKey": self.api_key,
            "dataType": "json",
            "pageUnit": page_unit,
            "pageIndex": page_index,
        }
        response = httpx.get(self.base_url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        if "reqErr" in data:
            raise BizinfoApiError(data["reqErr"])
        return data

    def fetch_all(
        self,
        page_unit: int = 100,
        max_pages: int = 50,
        updated_since: datetime | None = None,
    ) -> Iterator[dict]:
        """Yields raw policy items, newest first, stopping early once `updated_since` is reached.

        The API returns items ordered by recency (confirmed by sampling `creatPnttm`), so
        incremental sync can stop paginating as soon as it sees an item at or before the
        last sync's cutoff instead of always walking the full result set.
        """
        page_index = 1
        seen = 0
        while page_index <= max_pages:
            data = self.fetch_page(page_index, page_unit)
            items = data.get("jsonArray", [])
            if not items:
                return
            for item in items:
                if updated_since is not None:
                    item_updated = parse_bizinfo_datetime(item.get("updtPnttm"))
                    if item_updated is not None and item_updated <= updated_since:
                        return
                yield item
            seen += len(items)
            total = _safe_int(items[0].get("totCnt"))
            if total is not None and seen >= total:
                return
            page_index += 1


def parse_bizinfo_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def _safe_int(value: object) -> int | None:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
