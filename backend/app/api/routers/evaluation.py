"""AI-evaluation endpoint (Phase 5): quality/cost metrics for the AI stack."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthContext, get_auth
from app.db.base import get_session
from app.services import evaluation

router = APIRouter(prefix="/evaluation", tags=["evaluation"])


@router.get("/summary")
async def evaluation_summary(
    auth: Annotated[AuthContext, Depends(get_auth)],
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Forecast accuracy, agent stats, recommendation success, usage & cost.

    Ownership-scoped: regular users are evaluated on their own runs/forecasts;
    service/admin see everything.
    """
    return await evaluation.summary(
        session, owner_id=auth.user_id, privileged=auth.privileged
    )
