"""Chat endpoints: persisted sessions + grounded answers (Phase 3)."""

from __future__ import annotations

import uuid
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthContext, get_auth
from app.db.base import get_session
from app.llm.base import LLMError
from app.models.chat import ChatMessage, ChatSession
from app.schemas.chat import ChatMessageOut, ChatSessionOut, ChatTurnOut, SendMessageRequest
from app.services import chat_service

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])

Auth = Annotated[AuthContext, Depends(get_auth)]


@router.post("/sessions", response_model=ChatSessionOut, status_code=201)
async def create_session(
    auth: Auth, session: AsyncSession = Depends(get_session)
) -> ChatSessionOut:
    chat = ChatSession(id=uuid.uuid4(), user_id=auth.user_id)
    session.add(chat)
    await session.commit()
    return ChatSessionOut.model_validate(chat)


@router.get("/sessions", response_model=list[ChatSessionOut])
async def list_sessions(
    auth: Auth,
    limit: int = 50,
    session: AsyncSession = Depends(get_session),
) -> list[ChatSessionOut]:
    stmt = select(ChatSession)
    if not auth.privileged:
        stmt = stmt.where(ChatSession.user_id == auth.user_id)
    stmt = stmt.order_by(ChatSession.updated_at.desc()).limit(min(limit, 200))
    result = await session.execute(stmt)
    return [ChatSessionOut.model_validate(s) for s in result.scalars()]


async def _get_chat_or_404(
    session: AsyncSession, chat_id: uuid.UUID, auth: AuthContext
) -> ChatSession:
    """Load a chat session the caller is allowed to see (cross-user -> 404)."""
    stmt = select(ChatSession).where(ChatSession.id == chat_id)
    if not auth.privileged:
        stmt = stmt.where(ChatSession.user_id == auth.user_id)
    chat = (await session.execute(stmt)).scalar_one_or_none()
    if chat is None:
        raise HTTPException(status_code=404, detail=f"chat session '{chat_id}' not found")
    return chat


@router.get("/sessions/{chat_id}/messages", response_model=list[ChatMessageOut])
async def get_messages(
    chat_id: uuid.UUID,
    auth: Auth,
    session: AsyncSession = Depends(get_session),
) -> list[ChatMessageOut]:
    await _get_chat_or_404(session, chat_id, auth)
    result = await session.execute(
        select(ChatMessage).where(ChatMessage.session_id == chat_id).order_by(ChatMessage.seq)
    )
    return [ChatMessageOut.model_validate(m) for m in result.scalars()]


@router.post("/sessions/{chat_id}/messages", response_model=ChatTurnOut)
async def send_message(
    chat_id: uuid.UUID,
    body: SendMessageRequest,
    auth: Auth,
    session: AsyncSession = Depends(get_session),
) -> ChatTurnOut:
    """Send a user message and receive the grounded assistant reply."""
    await _get_chat_or_404(session, chat_id, auth)
    try:
        turn = await chat_service.send_message(session, chat_id, body.content)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except LLMError as exc:
        raise HTTPException(
            status_code=503, detail="the assistant is temporarily unavailable; try again shortly"
        ) from exc
    return ChatTurnOut(
        user_message=ChatMessageOut.model_validate(turn.user_message),
        assistant_message=ChatMessageOut.model_validate(turn.assistant_message),
    )


@router.delete("/sessions/{chat_id}", status_code=204)
async def delete_session(
    chat_id: uuid.UUID,
    auth: Auth,
    session: AsyncSession = Depends(get_session),
) -> None:
    await _get_chat_or_404(session, chat_id, auth)
    await session.execute(delete(ChatSession).where(ChatSession.id == chat_id))
    await session.commit()