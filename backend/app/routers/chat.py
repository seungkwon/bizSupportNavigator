"""Milestone 7 chat WebSocket (detailed_plan.md 5/8): `/ws/chat/{session_id}`.

Protocol (detailed_plan.md 5):
  client -> server: {"type": "start", "company_id": "...", "query": "..."?, "limit": 10?, "only_open": true?}
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
"""

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.db.postgres import SessionLocal
from app.services.chat_service import advance_session, create_session, get_session, record_answer, resume_payload

router = APIRouter(tags=["chat"])


@router.websocket("/ws/chat/{session_id}")
async def chat_ws(websocket: WebSocket, session_id: str) -> None:
    await websocket.accept()
    db = SessionLocal()
    try:
        session = get_session(db, session_id)
        if session is not None:
            payload = await asyncio.to_thread(resume_payload, db, session)
            if payload is not None:
                await websocket.send_json(payload)

        while True:
            data = await websocket.receive_json()
            message_type = data.get("type")

            if message_type == "start":
                session = await asyncio.to_thread(
                    create_session,
                    db,
                    session_id,
                    company_id=data["company_id"],
                    query_text=data.get("query"),
                    limit=data.get("limit", 10),
                    only_open=data.get("only_open", True),
                )
                payload = await asyncio.to_thread(advance_session, db, session)
            elif message_type == "answer":
                session = get_session(db, session_id)
                if session is None:
                    await websocket.send_json(
                        {"type": "error", "message": "세션이 시작되지 않았습니다 (type=start 먼저 전송)"}
                    )
                    continue
                await asyncio.to_thread(record_answer, db, session, data["question_id"], data["value"])
                payload = await asyncio.to_thread(advance_session, db, session)
            else:
                await websocket.send_json({"type": "error", "message": f"알 수 없는 메시지 타입: {message_type}"})
                continue

            await websocket.send_json(payload)
    except WebSocketDisconnect:
        pass
    finally:
        db.close()
