"""액션 기록(관심=saved, 참여=participated, 관심없음=hidden 등). 정본: dashboard-api.md §5."""
from __future__ import annotations

import uuid

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import delete, select

from app.api.deps import CurrentCompany, DbSession
from app.db.models.opportunity import UserOpportunityAction
from app.schemas.opportunity import ActionIn

router = APIRouter()


class HideIn(BaseModel):
    reason: str | None = None


@router.post("/{opportunity_id}/actions", status_code=201)
def record_action(
    opportunity_id: uuid.UUID, body: ActionIn, company_id: CurrentCompany, db: DbSession
) -> dict:
    exists = db.scalar(
        select(UserOpportunityAction).where(
            UserOpportunityAction.company_id == company_id,
            UserOpportunityAction.opportunity_id == opportunity_id,
            UserOpportunityAction.action_type == body.type,
        )
    )
    if not exists:  # 멱등
        db.add(UserOpportunityAction(
            company_id=company_id, opportunity_id=opportunity_id, action_type=body.type
        ))
        db.commit()
    return {"ok": True, "action_type": body.type}


@router.delete("/{opportunity_id}/actions/saved", status_code=204)
def unsave(opportunity_id: uuid.UUID, company_id: CurrentCompany, db: DbSession) -> None:
    db.execute(
        delete(UserOpportunityAction).where(
            UserOpportunityAction.company_id == company_id,
            UserOpportunityAction.opportunity_id == opportunity_id,
            UserOpportunityAction.action_type == "saved",
        )
    )
    db.commit()


@router.post("/{opportunity_id}/hide", status_code=201)
def hide(
    opportunity_id: uuid.UUID, body: HideIn, company_id: CurrentCompany, db: DbSession
) -> dict:
    """'관심없음' — 추천에서 제외(+사유 저장). 멱등(재호출 시 사유만 갱신)."""
    meta = {"reason": body.reason} if body.reason else None
    existing = db.scalar(
        select(UserOpportunityAction).where(
            UserOpportunityAction.company_id == company_id,
            UserOpportunityAction.opportunity_id == opportunity_id,
            UserOpportunityAction.action_type == "hidden",
        )
    )
    if existing is not None:
        existing.meta = meta
    else:
        db.add(UserOpportunityAction(
            company_id=company_id, opportunity_id=opportunity_id,
            action_type="hidden", meta=meta,
        ))
    db.commit()
    return {"ok": True, "reason": body.reason}


@router.delete("/{opportunity_id}/hide", status_code=204)
def unhide(opportunity_id: uuid.UUID, company_id: CurrentCompany, db: DbSession) -> None:
    """'관심없음' 취소(실행취소)."""
    db.execute(
        delete(UserOpportunityAction).where(
            UserOpportunityAction.company_id == company_id,
            UserOpportunityAction.opportunity_id == opportunity_id,
            UserOpportunityAction.action_type == "hidden",
        )
    )
    db.commit()
