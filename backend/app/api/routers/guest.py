"""Guest workspace reset endpoint (Phase 7).

A signed-in caller wipes their OWN workspace so each guest session starts clean.
Self-scoped: it can only ever delete rows owned by the authenticated user_id, so
it is safe for any account (it never touches other users' data).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthContext, get_auth
from app.db.base import get_session
from app.services import guest_service

router = APIRouter(prefix="/guest", tags=["guest"])

Auth = Annotated[AuthContext, Depends(get_auth)]


@router.post("/reset")
async def reset_workspace(auth: Auth, session: AsyncSession = Depends(get_session)) -> dict:
    """Clear all workspace data owned by the authenticated caller."""
    if auth.user_id is None:
        raise HTTPException(status_code=400, detail="reset requires a signed-in user")
    deleted = await guest_service.reset_workspace(session, auth.user_id)
    return {"ok": True, "deleted": deleted}
