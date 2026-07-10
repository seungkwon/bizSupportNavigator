"""Selects the announcement (공고문) attachment among a policy's candidate files
(detailed_plan.md 3.2): rule-based keyword filter first, LLM structured-output
judge for anything still ambiguous, manual-review queue for low-confidence cases.
"""

from dataclasses import dataclass

from openai import OpenAI
from pydantic import BaseModel

from app.core.config import get_settings

INCLUDE_KEYWORDS = ("공고문", "시행공고", "모집공고", "공고")
EXCLUDE_KEYWORDS = ("신청서", "서식", "동의서", "리플릿", "포스터", "가이드북")


@dataclass(frozen=True)
class AttachmentCandidate:
    file_name: str
    download_url: str


@dataclass(frozen=True)
class SelectionResult:
    selected: AttachmentCandidate | None
    reason: str
    needs_manual_review: bool


class _LlmSelection(BaseModel):
    selected_filename: str
    reason: str


def rule_based_filter(candidates: list[AttachmentCandidate]) -> list[AttachmentCandidate]:
    """Narrows candidates by filename keywords. Returns the full list unchanged if
    the keywords don't produce a confident narrowing (caller should escalate to the LLM)."""
    included = [c for c in candidates if any(k in c.file_name for k in INCLUDE_KEYWORDS)]
    if not included:
        return candidates
    narrowed = [c for c in included if not any(k in c.file_name for k in EXCLUDE_KEYWORDS)]
    return narrowed if narrowed else candidates


def select_announcement_file(candidates: list[AttachmentCandidate]) -> SelectionResult:
    if not candidates:
        return SelectionResult(selected=None, reason="첨부파일 없음", needs_manual_review=False)

    narrowed = rule_based_filter(candidates)
    if len(narrowed) == 1:
        return SelectionResult(
            selected=narrowed[0],
            reason="규칙 기반: 공고문 키워드 매칭",
            needs_manual_review=False,
        )

    return _llm_select(narrowed if narrowed else candidates)


def _llm_select(candidates: list[AttachmentCandidate]) -> SelectionResult:
    if len(candidates) == 1:
        return SelectionResult(
            selected=candidates[0], reason="후보 1건 (규칙 기반 매칭 없음)", needs_manual_review=False
        )

    settings = get_settings()
    if not settings.openai_api_key:
        return SelectionResult(
            selected=None,
            reason="OpenAI API 키 미설정으로 자동 판별 불가",
            needs_manual_review=True,
        )

    client = OpenAI(api_key=settings.openai_api_key)
    filenames = [c.file_name for c in candidates]
    try:
        completion = client.beta.chat.completions.parse(
            model=settings.openai_model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "너는 정부지원사업 공고 첨부파일 목록에서 실제 공고문(신청자격/제외요건이 "
                        "담긴 시행 공고문) 1개를 고르는 어시스턴트다. 신청서 양식, 별첨 서식, "
                        "개인정보 동의서 등은 공고문이 아니다."
                    ),
                },
                {
                    "role": "user",
                    "content": "첨부파일 목록:\n" + "\n".join(f"- {name}" for name in filenames),
                },
            ],
            response_format=_LlmSelection,
        )
    except Exception as exc:  # noqa: BLE001 - external API call, degrade to manual review
        return SelectionResult(
            selected=None, reason=f"LLM 호출 실패: {exc}", needs_manual_review=True
        )

    parsed = completion.choices[0].message.parsed
    if parsed is None:
        return SelectionResult(selected=None, reason="LLM 응답 파싱 실패", needs_manual_review=True)

    match = next((c for c in candidates if c.file_name == parsed.selected_filename), None)
    if match is None:
        return SelectionResult(
            selected=None,
            reason=f"LLM이 후보 목록에 없는 파일명을 반환함: {parsed.selected_filename}",
            needs_manual_review=True,
        )

    return SelectionResult(selected=match, reason=parsed.reason, needs_manual_review=False)
