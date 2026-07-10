"""Orchestrates the collection pipeline (detailed_plan.md 3.1):
fetch -> select announcement -> download -> persist to PostgreSQL."""

from dataclasses import dataclass, field
from datetime import date, datetime, timezone

from sqlalchemy.orm import Session

from app.models.policy import Policy, PolicyAttachment
from app.services.announcement_selector import AttachmentCandidate, select_announcement_file
from app.services.attachment_downloader import download_attachment, infer_format
from app.services.bizinfo_client import BizinfoClient, parse_bizinfo_datetime

META_FIELDS = (
    "jrsdInsttNm",
    "excInsttNm",
    "trgetNm",
    "pldirSportRealmLclasCodeNm",
    "pldirSportRealmMlsfcCodeNm",
    "hashtags",
    "reqstMthPapersCn",
    "bsnsSumryCn",
    "pblancUrl",
)


@dataclass
class SyncSummary:
    fetched: int = 0
    created: int = 0
    updated: int = 0
    attachments_downloaded: int = 0
    manual_review_count: int = 0
    errors: list[str] = field(default_factory=list)


def extract_attachment_candidates(item: dict) -> list[AttachmentCandidate]:
    """bizinfo exposes at most two attachment slots per policy (`fileNm`/`flpthNm`
    and `printFileNm`/`printFlpthNm`), not an arbitrary list — confirmed by sampling
    the live API. Both are treated as selection candidates."""
    pairs = [
        (item.get("fileNm"), item.get("flpthNm")),
        (item.get("printFileNm"), item.get("printFlpthNm")),
    ]
    seen_urls: set[str] = set()
    candidates: list[AttachmentCandidate] = []
    for file_name, download_url in pairs:
        if not file_name or not download_url or download_url in seen_urls:
            continue
        seen_urls.add(download_url)
        candidates.append(AttachmentCandidate(file_name=file_name, download_url=download_url))
    return candidates


def parse_apply_period(value: str | None) -> tuple[date | None, date | None]:
    if not value or "~" not in value:
        return None, None
    start_raw, _, end_raw = value.partition("~")
    return _parse_date(start_raw.strip()), _parse_date(end_raw.strip())


def _parse_date(value: str) -> date | None:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def persist_policy_meta(db: Session, item: dict) -> tuple[Policy, bool]:
    policy_id = item["pblancId"]
    policy = db.get(Policy, policy_id)
    is_new = policy is None
    start_date, end_date = parse_apply_period(item.get("reqstBeginEndDe"))
    meta = {field_name: item.get(field_name) for field_name in META_FIELDS}

    if policy is None:
        policy = Policy(policy_id=policy_id, source="bizinfo")
        db.add(policy)

    policy.title = item.get("pblancNm", policy_id)
    policy.meta = meta
    policy.apply_start_date = start_date
    policy.apply_end_date = end_date
    policy.collected_at = datetime.now(timezone.utc)
    policy.source_updated_at = parse_bizinfo_datetime(item.get("updtPnttm"))

    return policy, is_new


def sync_attachments(db: Session, policy: Policy, item: dict, summary: SyncSummary) -> None:
    candidates = extract_attachment_candidates(item)

    # Re-derive attachment rows each sync so stale candidates don't linger.
    for existing in list(policy.attachments):
        db.delete(existing)
    db.flush()

    if not candidates:
        return

    result = select_announcement_file(candidates)

    for candidate in candidates:
        is_selected = (
            result.selected is not None and candidate.download_url == result.selected.download_url
        )
        attachment = PolicyAttachment(
            policy_id=policy.policy_id,
            file_name=candidate.file_name,
            download_url=candidate.download_url,
            is_announcement=is_selected,
            selection_reason=result.reason if is_selected else None,
            needs_manual_review=result.needs_manual_review and result.selected is None,
            format=infer_format(candidate.file_name),
            parse_status="pending",
        )
        if is_selected:
            try:
                attachment.downloaded_path = download_attachment(
                    candidate.download_url, candidate.file_name, policy.policy_id
                )
                summary.attachments_downloaded += 1
            except Exception as exc:  # noqa: BLE001 - external download, degrade gracefully
                attachment.parse_status = "download_failed"
                summary.errors.append(f"{policy.policy_id}: 다운로드 실패 ({exc})")
        db.add(attachment)

    if result.needs_manual_review:
        summary.manual_review_count += 1


def sync_policies(
    db: Session,
    max_pages: int = 50,
    page_unit: int = 100,
    updated_since: datetime | None = None,
) -> SyncSummary:
    client = BizinfoClient()
    summary = SyncSummary()

    for item in client.fetch_all(page_unit=page_unit, max_pages=max_pages, updated_since=updated_since):
        summary.fetched += 1
        policy, is_new = persist_policy_meta(db, item)
        db.flush()
        sync_attachments(db, policy, item, summary)
        if is_new:
            summary.created += 1
        else:
            summary.updated += 1

    db.commit()
    return summary
