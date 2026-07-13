"""Milestone 7 chat WebSocket (detailed_plan.md 5/8): `/ws/chat/{session_id}`.

Protocol (detailed_plan.md 5):
  client -> server: {"type": "start", "company_id": "...", "query": "..."?, "limit": 10?, "only_open": true?, "policy_id": "..."?}
  # "policy_id" (dashboard "이 정책 재확인" flow): when set, clarification questions
  # focus on that specific policy instead of the RAG top rank (see
  # app/services/chat_service.py::_resolve_focus_candidate), so a policy the user
  # clicked into from the recommendation list always gets asked about even if it
  # wasn't the #1 match for the generic query text.
  client -> server: {"type": "answer", "question_id": "q1", "value": "yes"|"no"}
  server -> client: {"type": "question", "question_id": "q1", "text": "...", "options": [...]}
  server -> client: {"type": "result", "matches": [...]}
  server -> client: {"type": "error", "message": "..."}

A plain `SessionLocal()` is used instead of the `Depends(get_db)` REST pattern:
a WebSocket connection is long-lived and spans many independent commits (one
per turn), which doesn't fit a per-request generator dependency.

`create_session`/`advance_session` do synchronous, blocking work (bge-m3
embedding inference, Neo4j driver calls, OpenAI HTTP calls -- easily 10s of
seconds) and must run via `asyncio.to_thread`, not awaited directly: calling
them inline blocks the event loop, which starves the websocket keepalive
ping/pong and kills the connection with a "keepalive ping timeout" (observed
while testing this).

Auth (Milestone 8, detailed_plan.md 6): browsers can't set a custom
`Authorization` header on a WebSocket handshake, so the JWT travels as a
`?token=` query param instead. `data["company_id"]` on `start` and the
resumed `chat_sessions.company_id` on reconnect must both match the token's
company -- otherwise a valid token for one company could resume or drive
another company's chat session just by guessing its session_id.
"""

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session as DbSession

from app.core.security import decode_company_id
from app.db.postgres import SessionLocal
from app.services.chat_service import advance_session, create_session, get_session, record_answer, resume_payload

router = APIRouter(tags=["chat"])

_WRONG_COMPANY = {"type": "error", "message": "다른 기업의 세션에 접근할 수 없습니다"}


async def _handle_start(db: DbSession, session_id: str, data: dict, authenticated_company_id: str) -> dict:
    if data.get("company_id") != authenticated_company_id:
        return {"type": "error", "message": "토큰의 기업과 일치하지 않습니다"}
    session = await asyncio.to_thread(
        create_session,
        db,
        session_id,
        company_id=authenticated_company_id,
        query_text=data.get("query"),
        limit=data.get("limit", 10),
        only_open=data.get("only_open", True),
        target_policy_id=data.get("policy_id"),
    )
    return await asyncio.to_thread(advance_session, db, session)


async def _handle_answer(db: DbSession, session_id: str, data: dict, authenticated_company_id: str) -> dict:
    session = get_session(db, session_id)
    if session is None:
        return {"type": "error", "message": "세션이 시작되지 않았습니다 (type=start 먼저 전송)"}
    if session.company_id != authenticated_company_id:
        return _WRONG_COMPANY
    await asyncio.to_thread(record_answer, db, session, data["question_id"], data["value"])
    return await asyncio.to_thread(advance_session, db, session)


async def _send_resume_if_any(websocket: WebSocket, db: DbSession, session_id: str, authenticated_company_id: str) -> bool:
    """Returns False (and closes the socket) if the session belongs to a different company."""
    session = get_session(db, session_id)
    if session is None:
        return True
    if session.company_id != authenticated_company_id:
        await websocket.send_json(_WRONG_COMPANY)
        await websocket.close(code=1008)
        return False
    payload = await asyncio.to_thread(resume_payload, db, session)
    if payload is not None:
        await websocket.send_json(payload)
    return True


@router.websocket("/ws/chat/{session_id}")
async def chat_ws(websocket: WebSocket, session_id: str) -> None:
    token = websocket.query_params.get("token")
    authenticated_company_id = decode_company_id(token) if token else None
    if authenticated_company_id is None:
        await websocket.close(code=1008)  # policy violation
        return

    await websocket.accept()
    db = SessionLocal()
    try:
        if not await _send_resume_if_any(websocket, db, session_id, authenticated_company_id):
            return

        while True:
            data = await websocket.receive_json()
            message_type = data.get("type")

            if message_type == "start":
                payload = await _handle_start(db, session_id, data, authenticated_company_id)
            elif message_type == "answer":
                payload = await _handle_answer(db, session_id, data, authenticated_company_id)
            else:
                payload = {"type": "error", "message": f"알 수 없는 메시지 타입: {message_type}"}

            await websocket.send_json(payload)
    except WebSocketDisconnect:
        pass
    finally:
        db.close()
