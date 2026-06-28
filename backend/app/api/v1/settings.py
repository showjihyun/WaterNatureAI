"""설정 — 수신설정/구독 상태/LLM 공급자(시스템). 정본: dashboard-api.md §7."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.api.deps import CurrentAdmin, CurrentCompany, DbSession
from app.core.security_log import client_ip, log_security_event
from app.db.models.accounts import NotificationSetting
from app.db.models.app_settings import AppSetting
from app.db.models.billing import Subscription
from app.services import llm

router = APIRouter()


def _active_sources() -> list[str]:
    """맞춤 알림 규칙에서 켜고/끌 수 있는 소스 = 현재 운영 활성 수집기."""
    from app.services.collectors.registry import COLLECTORS  # noqa: PLC0415

    return list(COLLECTORS.keys())


class NotificationSettingIn(BaseModel):
    model_config = ConfigDict(extra="forbid")  # 미지정 필드 거부(mass-assignment 방어)

    enabled: bool | None = None
    channel: str | None = None
    send_hour: int | None = None
    send_empty: bool | None = None
    # 맞춤 알림 규칙(#4). min_score=None → 전역 기본 임계값. excluded_sources=[] → 전체 포함.
    min_score: int | None = Field(default=None, ge=0, le=100)
    excluded_sources: list[str] | None = None
    # 마감 리마인더 일수(#D-3). None → 기본 3, 0 → 끄기.
    deadline_reminder_days: int | None = Field(default=None, ge=0, le=60)


def _notification_payload(cfg: NotificationSetting | None) -> dict:
    base = (
        {"enabled": True, "channel": "alimtalk", "send_hour": 8, "send_empty": False,
         "min_score": None, "excluded_sources": [], "deadline_reminder_days": None}
        if cfg is None
        else {"enabled": cfg.enabled, "channel": cfg.channel, "send_hour": cfg.send_hour,
              "send_empty": cfg.send_empty, "min_score": cfg.min_score,
              "excluded_sources": list(cfg.excluded_sources or []),
              "deadline_reminder_days": cfg.deadline_reminder_days}
    )
    base["available_sources"] = _active_sources()
    return base


@router.get("/notification")
def get_notification(company_id: CurrentCompany, db: DbSession) -> dict:
    return _notification_payload(db.get(NotificationSetting, company_id))


@router.put("/notification")
def put_notification(
    body: NotificationSettingIn, company_id: CurrentCompany, db: DbSession
) -> dict:
    # 미지정 필드는 건드리지 않되, 명시적 None(예: min_score 기본 복귀)은 반영(exclude_unset).
    data = body.model_dump(exclude_unset=True)
    if data.get("excluded_sources"):
        allowed = set(_active_sources())
        bad = [s for s in data["excluded_sources"] if s not in allowed]
        if bad:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"알 수 없는 소스: {', '.join(bad)} (가능: {', '.join(sorted(allowed))})",
            )
    cfg = db.get(NotificationSetting, company_id)
    if cfg is None:
        cfg = NotificationSetting(company_id=company_id)
        db.add(cfg)
    for field, value in data.items():
        setattr(cfg, field, value)
    db.commit()
    return _notification_payload(cfg)


@router.get("/notification/preview")
def notification_preview(company_id: CurrentCompany, db: DbSession) -> dict:
    """발송 없이 '오늘의 카카오 알림톡' 미리보기(실 Top-N 매칭 + 발송 진단).

    실제 발송은 사업자등록·발신프로필·템플릿 심사 후 — 여기서는 내용만 렌더.
    """
    from app.services.notifications.tasks import build_briefing_preview  # noqa: PLC0415

    return build_briefing_preview(db, company_id)


class LlmSettingIn(BaseModel):
    model_config = ConfigDict(extra="forbid")  # 미지정 필드 거부(mass-assignment 방어)

    provider: str
    model: str
    # 입력 시 암호화하여 DB 저장(평문 미저장). 미입력이면 기존 키 유지.
    api_key: str | None = None


@router.get("/llm")
def get_llm(admin: CurrentAdmin, db: DbSession) -> dict:
    """현재 활성 LLM 공급자/모델 + 공급자별 설정여부·선택가능 모델.

    키 원문은 절대 노출하지 않는다(설정여부 bool만). 시스템 전역 설정이라 **운영자 전용**
    (어떤 공급자가 설정됐는지 정보가 일반 테넌트에 새지 않도록 GET도 게이트).
    """
    provider, model = llm.get_active_provider_model(db)
    providers = [
        {
            "provider": p,
            "configured": llm.is_provider_configured(p, db),
            "default_model": llm.provider_default_model(p),
            "models": llm.PROVIDER_MODELS[p],
        }
        for p in llm.PROVIDERS
    ]
    return {"provider": provider, "model": model, "providers": providers}


@router.put("/llm")
def put_llm(body: LlmSettingIn, admin: CurrentAdmin, request: Request, db: DbSession) -> dict:
    """활성 LLM 공급자/모델 변경(**시스템 전역 → 운영자 전용**).

    ⚠️ 보안: 이 값/키는 전 테넌트 공통이므로 일반 사용자가 바꾸면 다른 회사의
    LLM 트래픽을 자신의 키로 가로채거나(키 탈취) 무력화(DoS)할 수 있다. 따라서
    ADMIN_EMAILS(운영자)만 허용한다(CurrentAdmin). api_key 입력 시 암호화 저장.
    """
    provider = body.provider.strip()
    model = body.model.strip()
    if provider not in llm.PROVIDERS:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"지원하지 않는 공급자: {provider} (가능: {', '.join(llm.PROVIDERS)})",
        )
    # 키 입력 시 암호화 저장(선택 검증 전에 먼저 저장 → 신규 키로 즉시 선택 가능)
    if body.api_key and body.api_key.strip():
        llm.set_provider_key(db, provider, body.api_key.strip())
    if not llm.is_provider_configured(provider, db):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"{provider} API 키가 없습니다 — 설정에서 키를 입력 후 저장하세요.",
        )
    if not model:
        model = llm.provider_default_model(provider)

    row = db.get(AppSetting, "llm")
    value = {"provider": provider, "model": model}
    if row is None:
        db.add(AppSetting(key="llm", value=value))
    else:
        row.value = value
    db.commit()
    log_security_event(
        "admin_config_change",
        actor=admin,
        ip=client_ip(request),
        outcome="success",
        target="llm",
        provider=provider,
        key_updated=bool(body.api_key and body.api_key.strip()),
    )
    return {"ok": True, "provider": provider, "model": model}


class KakaoSettingIn(BaseModel):
    """카카오/SOLAPI 발신 설정 입력. 빈 문자열/미입력은 '변경 안 함'(기존 값 유지).

    api_key/api_secret은 입력 시 **암호화하여 DB 저장**(평문 미저장)하고 응답에 반환하지 않는다.
    """

    model_config = ConfigDict(extra="forbid")  # 미지정 필드 거부(mass-assignment 방어)

    provider: str | None = None
    sender_key: str | None = None          # SOLAPI 발신프로필 pfId
    template_briefing: str | None = None   # 승인된 알림톡 템플릿 코드
    api_key: str | None = None
    api_secret: str | None = None


@router.get("/kakao")
def get_kakao(admin: CurrentAdmin, db: DbSession) -> dict:
    """카카오/SOLAPI 발신 설정 상태(**운영자 전용**). 시크릿은 설정 여부(bool)만 노출."""
    from app.services.notifications import kakao_config  # noqa: PLC0415

    return kakao_config.kakao_status(db)


@router.put("/kakao")
def put_kakao(body: KakaoSettingIn, admin: CurrentAdmin, request: Request, db: DbSession) -> dict:
    """카카오/SOLAPI 발신 설정 변경(**시스템 전역 → 운영자 전용**).

    ⚠️ 보안: 카카오 발신 계정은 플랫폼 1개라 일반 사용자가 바꾸면 전체 발송을
    가로채거나 무력화할 수 있다. ADMIN_EMAILS(운영자)만 허용(CurrentAdmin).
    api_key/api_secret은 암호화하여 DB 저장하며 응답에 시크릿을 반환하지 않는다.
    """
    from app.services.notifications import kakao_config  # noqa: PLC0415

    kakao_config.set_kakao_config(
        db,
        provider=body.provider,
        sender_key=body.sender_key,
        template_briefing=body.template_briefing,
        api_key=body.api_key,
        api_secret=body.api_secret,
    )
    log_security_event(
        "admin_config_change",
        actor=admin,
        ip=client_ip(request),
        outcome="success",
        target="kakao",
        fields=[
            f
            for f in ("provider", "sender_key", "template_briefing")
            if (getattr(body, f) or "").strip()
        ],
        secrets_updated=bool(
            (body.api_key and body.api_key.strip())
            or (body.api_secret and body.api_secret.strip())
        ),
    )
    return kakao_config.kakao_status(db)


@router.get("/billing")
def get_billing(company_id: CurrentCompany, db: DbSession) -> dict:
    sub = db.scalar(select(Subscription).where(Subscription.company_id == company_id))
    if sub is None:
        return {"status": "none", "plan_code": None}  # 미구독 (사업자 확보 전 test 모드)
    return {
        "status": sub.status, "plan_code": sub.plan_code,
        "current_period_end": sub.current_period_end.isoformat() if sub.current_period_end else None,
    }
