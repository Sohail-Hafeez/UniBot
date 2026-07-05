"""
backend/routes/chat.py

Chat + conversation-session endpoints for the NUST/MCS student assistant.
The response contract (SSE token stream, conversations CRUD) matches what
the frontend expects — only the underlying model/retrieval stack differs
from a generic assistant: every reply is grounded in the Qdrant knowledge
base built by the ingestion pipeline.

Every route requires a verified Firebase ID token (see services/firebase_auth.py)
and every conversation is scoped to its owning user_id — one user can never
list, read, or delete another user's sessions.
"""

import asyncio
import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from memory.episodic import EpisodicMemory
from memory.short_term import ShortTermMemory
from services.firebase_auth import CurrentUser, get_current_user
from services.rag import build_system_prompt, generate_title, retrieve_context, stream_chat, summarize

router = APIRouter()

episodic = EpisodicMemory()
short_term = ShortTermMemory()


class ChatRequest(BaseModel):
    session_id: str
    message: str


async def _require_owned_session(session_id: str, user_id: str) -> None:
    """
    Raise 404 unless `session_id` exists AND belongs to `user_id`.

    Uses 404 (not 403) for both "doesn't exist" and "belongs to someone
    else" so a caller can't distinguish the two and enumerate valid
    session ids belonging to other users.
    """

    owner = await episodic.get_session_owner(session_id)
    if owner is None or owner != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")


@router.post("/api/chat")
async def chat(req: ChatRequest, current_user: CurrentUser = Depends(get_current_user)):
    """Stream a RAG-grounded chat response as Server-Sent Events."""

    await _require_owned_session(req.session_id, current_user.uid)

    summary, recent = await short_term.get_context(req.session_id, episodic)
    context_chunks = await retrieve_context(req.message)

    messages: list[dict] = [
        {"role": "system", "content": build_system_prompt(context_chunks)}
    ]
    if summary:
        messages.append(
            {"role": "system", "content": f"[Summary of earlier conversation: {summary}]"}
        )
    messages.extend(recent)
    messages.append({"role": "user", "content": req.message})

    collected: list[str] = []

    async def generate():
        async for token in stream_chat(messages):
            collected.append(token)
            yield f"data: {json.dumps({'token': token})}\n\n"
        yield "data: [DONE]\n\n"
        asyncio.create_task(
            _post_process(req.session_id, req.message, "".join(collected))
        )

    return StreamingResponse(generate(), media_type="text/event-stream")


async def _post_process(session_id: str, user_msg: str, assistant_msg: str) -> None:
    """Persist the exchange, title the session on its first turn, summarise if it's grown long."""

    await short_term.add_exchange(session_id, user_msg, assistant_msg, episodic, summarize)
    count = await episodic.get_message_count(session_id)
    if count == 2:
        title = await generate_title(
            [{"role": "user", "content": user_msg}, {"role": "assistant", "content": assistant_msg}]
        )
        await episodic.update_title(session_id, title)


@router.get("/api/conversations")
async def list_conversations(current_user: CurrentUser = Depends(get_current_user)):
    return await episodic.get_sessions(current_user.uid, only_with_messages=True)


@router.post("/api/conversations")
async def create_conversation(current_user: CurrentUser = Depends(get_current_user)):
    session_id = str(uuid.uuid4())
    await episodic.create_session(session_id, current_user.uid)
    short_term.clear_session(session_id)
    return {"session_id": session_id}


@router.get("/api/conversations/{session_id}")
async def get_conversation(session_id: str, current_user: CurrentUser = Depends(get_current_user)):
    await _require_owned_session(session_id, current_user.uid)
    messages = await episodic.get_messages(session_id)
    return {"messages": messages}


@router.delete("/api/conversations/{session_id}")
async def delete_conversation(session_id: str, current_user: CurrentUser = Depends(get_current_user)):
    await _require_owned_session(session_id, current_user.uid)
    await episodic.delete_session(session_id)
    short_term.clear_session(session_id)
    return {"ok": True}
