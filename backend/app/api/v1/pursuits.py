"""진행 관리 파이프라인 (pursuits). 단계: reviewing→preparing→submitted→done.

- GET    /pursuits                  : 진행 중인 공고 전부(단계별 그룹은 프론트가).
- POST   /pursuits                  : 공고를 파이프라인에 추가(기본 reviewing). 멱등.
- PATCH  /pursuits/{opportunity_id} : 단계/메모 변경. submitted·done 도달 시 'participated' 기록.
- DELETE /pursuits/{opportunity_id} : 파이프라인에서 제거.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import and_, delete, select

from app.api.deps import CurrentCompany, DbSession
from app.db.models.accounts import Company
from app.db.models.opportunity import (
    PURSUIT_STAGES,
    Match,
    Opportunity,
    Pursuit,
    UserOpportunityAction,
)
from app.schemas.opportunity import RecommendationItem
from app.services.feasibility.engine import assess_feasibility

router = APIRouter()


class PursuitItem(BaseModel):
    stage: str
    note: str | None = None
    opportunity: RecommendationItem


class PursuitIn(BaseModel):
    opportunity_id: uuid.UUID
    stage: str | None = None


class PursuitPatch(BaseModel):
    stage: str | None = None
    note: str | None = None


def _d_day(deadline: datetime | None) -> int | None:
    if not deadline:
        return None
    return (deadline.date() - datetime.now(timezone.utc).date()).days


def _item(o: Opportunity, score: int | None, company: Company | None) -> RecommendationItem:
    fr = assess_feasibility(
        tech_level=company.tech_level if company else None,
        max_project_budget=company.max_project_budget if company else None,
        capable_categories=company.capable_categories if company else None,
        budget_amount=o.budget_amount,
        category=o.category,
    )
    feasibility = (
        {"verdict": fr.verdict, "label": fr.label, "reasons": fr.reasons} if fr else None
    )
    return RecommendationItem(
        opportunity_id=o.id, title=o.title, agency=o.agency, category=o.category,
        budget_amount=o.budget_amount, posted_at=o.posted_at, deadline=o.deadline,
        d_day=_d_day(o.deadline), score=score, reasons=[], saved=False,
        source=o.source, detail_url=o.detail_url, feasibility=feasibility,
    )


def _record_participated(db: DbSession, company_id: uuid.UUID, opportunity_id: uuid.UUID) -> None:
    """제출/완료 도달 → 퍼널 'participated' 기록(멱등)."""
    exists = db.scalar(
        select(UserOpportunityAction).where(
            UserOpportunityAction.company_id == company_id,
            UserOpportunityAction.opportunity_id == opportunity_id,
            UserOpportunityAction.action_type == "participated",
        )
    )
    if not exists:
        db.add(UserOpportunityAction(
            company_id=company_id, opportunity_id=opportunity_id, action_type="participated"
        ))


@router.get("", response_model=list[PursuitItem])
def list_pursuits(company_id: CurrentCompany, db: DbSession) -> list[PursuitItem]:
    """진행 중인 공고 목록(최근 갱신순). 프론트가 단계별 칼럼으로 그룹화."""
    company = db.get(Company, company_id)
    rows = db.execute(
        select(Pursuit, Opportunity, Match.score)
        .join(Opportunity, Opportunity.id == Pursuit.opportunity_id)
        .outerjoin(
            Match,
            and_(Match.opportunity_id == Opportunity.id, Match.company_id == company_id),
        )
        .where(Pursuit.company_id == company_id)
        .order_by(Pursuit.updated_at.desc())
        .limit(500)  # 동일 테넌트 메모리 증폭 방어(파이프라인은 통상 수십 건)
    ).all()
    return [
        PursuitItem(stage=p.stage, note=p.note, opportunity=_item(o, score, company))
        for p, o, score in rows
    ]


@router.post("", status_code=201)
def add_pursuit(body: PursuitIn, company_id: CurrentCompany, db: DbSession) -> dict:
    """공고를 파이프라인에 추가(멱등). 기본 단계 reviewing."""
    stage = body.stage or "reviewing"
    if stage not in PURSUIT_STAGES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"잘못된 단계: {stage}")
    if db.get(Opportunity, body.opportunity_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "공고를 찾을 수 없습니다.")

    existing = db.scalar(
        select(Pursuit).where(
            Pursuit.company_id == company_id,
            Pursuit.opportunity_id == body.opportunity_id,
        )
    )
    if existing is None:
        db.add(Pursuit(company_id=company_id, opportunity_id=body.opportunity_id, stage=stage))
        if stage in ("submitted", "done"):
            _record_participated(db, company_id, body.opportunity_id)
        db.commit()
        return {"ok": True, "stage": stage, "created": True}
    return {"ok": True, "stage": existing.stage, "created": False}


@router.patch("/{opportunity_id}")
def update_pursuit(
    opportunity_id: uuid.UUID, body: PursuitPatch, company_id: CurrentCompany, db: DbSession
) -> dict:
    """단계/메모 변경. submitted·done 도달 시 'participated' 기록(멱등)."""
    pursuit = db.scalar(
        select(Pursuit).where(
            Pursuit.company_id == company_id,
            Pursuit.opportunity_id == opportunity_id,
        )
    )
    if pursuit is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "진행 항목이 없습니다.")

    if body.stage is not None:
        if body.stage not in PURSUIT_STAGES:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"잘못된 단계: {body.stage}")
        pursuit.stage = body.stage
        if body.stage in ("submitted", "done"):
            _record_participated(db, company_id, opportunity_id)
    if body.note is not None:
        pursuit.note = body.note or None

    db.commit()
    return {"ok": True, "stage": pursuit.stage}


@router.delete("/{opportunity_id}", status_code=204)
def remove_pursuit(opportunity_id: uuid.UUID, company_id: CurrentCompany, db: DbSession) -> None:
    db.execute(
        delete(Pursuit).where(
            Pursuit.company_id == company_id,
            Pursuit.opportunity_id == opportunity_id,
        )
    )
    db.commit()
