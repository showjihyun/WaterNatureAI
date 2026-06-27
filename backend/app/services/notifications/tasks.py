"""Daily Briefing 발송(KST). 정본: docs/04-architecture/daily-briefing.md §8.

카카오 알림톡(SOLAPI)로 기업별 추천 Top-N 전달.
- 멱등: (company_id, briefing_date) 유니크(notifications) → 1일 1회.
- 대상: notification_settings.enabled AND active_subscribed(구독 active/trialing).
- 발송 결과 → notifications(channel='alimtalk') 기록 + user_opportunity_actions='notified'.

🚧 실발송은 SOLAPI 키·발신프로필·템플릿 심사 후. 키 없으면 provider가 RuntimeError →
   notifications.status='failed' 로 기록(에러로 죽지 않음). Beat 엔트리는 유지.
"""
from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import or_, select

from app.core.celery_app import celery_app
from app.core.config import settings
from app.db.base import SessionLocal
from app.db.models.accounts import Company, KeywordWatch, NotificationSetting
from app.db.models.billing import Subscription
from app.db.models.notification import Notification
from app.db.models.opportunity import Match, Opportunity, UserOpportunityAction
from app.services.billing.provider import active_subscribed
from app.services.keyword_watch import keyword_match_rows
from app.services.notifications.provider import (
    NotificationProvider,
    NotRegisteredOrBlocked,
    SolapiProvider,
)
from app.services.reminders import reminder_days_for, upcoming_reminders

# 브리핑에 포함할 키워드 매칭 = 최근 N일 수집분(매일 같은 것 반복 방지).
_BRIEFING_KEYWORD_DAYS = 14

logger = logging.getLogger(__name__)


def _today_kst() -> date:
    """발송 기준일(멱등 키). Celery timezone=Asia/Seoul → 로컬 today."""
    return datetime.now().date()


def _fmt_budget(opp) -> str:
    """예산 표기 — budget_amount(파싱값) 우선 한국식 단위, 없으면 budget_raw."""
    amt = getattr(opp, "budget_amount", None)
    if amt:
        if amt >= 100_000_000:
            eok = amt / 100_000_000
            return f"{eok:.1f}억원".replace(".0억", "억")
        if amt >= 10_000:
            return f"{amt // 10_000:,}만원"
        return f"{amt:,}원"
    return getattr(opp, "budget_raw", None) or "-"


def _d_day(deadline: datetime | None, today: date) -> str:
    """마감까지 D-day 문자열. 없으면 '-', 지났으면 'D+n'."""
    if deadline is None:
        return "-"
    diff = (deadline.date() - today).days
    if diff == 0:
        return "D-day"
    return f"D-{diff}" if diff > 0 else f"D+{-diff}"


# 브리핑 엔트리: (opportunity, score|None, matched_keywords). 키워드 매칭은 score 없을 수 있음.
BriefingEntry = tuple[Opportunity, "int | None", list[str]]


def render_briefing_variables(
    company_name: str, entries: list[BriefingEntry], today: date
) -> dict:
    """알림톡 템플릿 `#{}` 변수 매핑(자유서술 X — 고정 골격 + 변수 치환).

    템플릿(daily-briefing.md §3) 자리표시자:
      #{회사명} #{건수}
      #{공고1명} #{점수1} #{규모1} #{디데이1} …
    AI 매칭은 점수, 키워드-only는 점수 공란(템플릿이 고정 줄 수면 운영에서 정리).
    """
    variables: dict[str, str] = {
        "회사명": company_name,
        "건수": str(len(entries)),
    }
    for i, (opp, score, _matched) in enumerate(entries, start=1):
        variables[f"공고{i}명"] = opp.title or ""
        variables[f"점수{i}"] = str(score) if score is not None else ""
        variables[f"규모{i}"] = _fmt_budget(opp)
        variables[f"디데이{i}"] = _d_day(opp.deadline, today)
    return variables


def _entries_to_sms(company_name: str, entries: list[BriefingEntry]) -> str:
    """폴백 SMS 본문 — AI 매칭은 '적합도 N', 키워드-only는 '키워드 X'."""
    lines = [f"[WaterNature] {company_name}님 오늘의 추천 {len(entries)}건"]
    for i, (opp, score, matched) in enumerate(entries, start=1):
        if score is not None:
            tag = f"적합도 {score}"
        elif matched:
            tag = f"키워드 {matched[0]}"
        else:
            tag = ""
        lines.append(f"{i}. {opp.title}" + (f" ({tag})" if tag else ""))
    return "\n".join(lines)


def _briefing_rules(cfg: NotificationSetting | None) -> tuple[int, list[str]]:
    """맞춤 알림 규칙(#4) → 적용값 (min_score, excluded_sources).

    cfg.min_score 미설정 시 전역 기본(match_threshold). excluded_sources 없으면 전체 소스.
    """
    if cfg is None:
        return settings.match_threshold, []
    threshold = cfg.min_score if cfg.min_score is not None else settings.match_threshold
    return threshold, list(cfg.excluded_sources or [])


def _top_matches(
    db,
    company_id: uuid.UUID,
    limit: int,
    *,
    min_score: int | None = None,
    excluded_sources: list[str] | None = None,
) -> list[tuple[Match, Opportunity]]:
    """기업 추천 Top-N: score≥임계값 · is_canonical · open · 제외소스 아님, score desc.

    min_score 미지정 시 전역 match_threshold. excluded_sources 의 소스는 브리핑에서 제외(#4 규칙).
    """
    threshold = min_score if min_score is not None else settings.match_threshold
    # '관심없음(hidden)' 처리분은 브리핑에서도 제외(#3 피드백 루프 — 추천과 일관).
    hidden = (
        select(UserOpportunityAction.opportunity_id)
        .where(
            UserOpportunityAction.company_id == company_id,
            UserOpportunityAction.action_type == "hidden",
        )
        .scalar_subquery()
    )
    stmt = (
        select(Match, Opportunity)
        .join(Opportunity, Match.opportunity_id == Opportunity.id)
        .where(
            Match.company_id == company_id,
            Match.score >= threshold,
            Opportunity.is_canonical.is_(True),
            Opportunity.status == "open",
            # 마감 경과분 제외(sweep 지연 대비). 마감 미제공(NTIS 등)은 유지.
            or_(Opportunity.deadline.is_(None), Opportunity.deadline >= datetime.now(timezone.utc)),
            Opportunity.id.not_in(hidden),
        )
    )
    if excluded_sources:
        stmt = stmt.where(Opportunity.source.not_in(excluded_sources))
    rows = db.execute(stmt.order_by(Match.score.desc()).limit(limit)).all()
    return [(r[0], r[1]) for r in rows]


def _briefing_entries(db, company_id: uuid.UUID, cfg: NotificationSetting | None) -> list[BriefingEntry]:
    """브리핑 대상 = AI Top-N + 키워드 워치 매칭(중복·hidden·제외소스 제거).

    AI 매칭은 점수순 먼저, 그 뒤 최근 키워드 매칭(점수 무관 — 워치는 '적합도와 별개로 원함').
    """
    min_score, excluded = _briefing_rules(cfg)
    ai = _top_matches(db, company_id, settings.briefing_top_n,
                      min_score=min_score, excluded_sources=excluded)
    entries: list[BriefingEntry] = [(opp, match.score, []) for match, opp in ai]
    seen = {opp.id for _, opp in ai}

    keywords = [
        w.keyword
        for w in db.scalars(
            select(KeywordWatch).where(KeywordWatch.company_id == company_id)
        ).all()
    ]
    if keywords:
        # keyword_match_rows: hidden 제외·open·canonical 적용(min_score 미적용 — 의도).
        kw_rows = keyword_match_rows(
            db, company_id, keywords,
            limit=settings.briefing_top_n, recent_days=_BRIEFING_KEYWORD_DAYS, order="created",
        )
        for opp, score, matched, _saved in kw_rows:
            if opp.id in seen or (excluded and opp.source in excluded):
                continue
            entries.append((opp, score, matched))
            seen.add(opp.id)
    return entries


def build_briefing_preview(db, company_id: uuid.UUID) -> dict:
    """발송 없이 '오늘의 브리핑' 미리보기 데이터 생성(실 Top-N 매칭 기반).

    카카오 알림톡으로 나갈 내용 그대로 렌더 + 발송 가능 여부 진단(차단 요인 목록).
    부수효과 없음(notifications/액션 미기록).
    """
    company = db.get(Company, company_id)
    cfg = db.get(NotificationSetting, company_id)
    today = _today_kst()
    entries = _briefing_entries(db, company_id, cfg)  # AI Top-N + 키워드 매칭
    company_name = company.name if company else ""
    variables = render_briefing_variables(company_name, entries, today)

    items = [
        {
            "title": opp.title or "",
            "score": score,
            "agency": opp.agency or "",
            "budget": _fmt_budget(opp),
            "dday": _d_day(opp.deadline, today),
            "source": opp.source,
            "matched_keywords": matched,
        }
        for opp, score, matched in entries
    ]

    # 발송 가능 여부 진단(실발송 차단 요인).
    sub = db.scalar(select(Subscription).where(Subscription.company_id == company_id))
    blockers: list[str] = []
    if cfg is not None and not cfg.enabled:
        blockers.append("알림이 비활성화됨")
    if not (company and company.phone):
        blockers.append("수신 휴대폰 번호 미등록")
    if sub is None or sub.status not in ("active", "trialing"):
        blockers.append("미구독(구독 시 발송)")
    keys_ready = bool(
        settings.solapi_api_key
        and settings.solapi_api_secret
        and settings.kakao_sender_key
        and settings.kakao_template_briefing
    )
    if not keys_ready:
        blockers.append("SOLAPI 발신프로필·템플릿 미설정(사업자 후)")

    return {
        "company_name": company_name,
        "today": today.isoformat(),
        "count": len(entries),
        "channel": cfg.channel if cfg is not None else "alimtalk",
        "send_hour": cfg.send_hour if cfg is not None else settings.notify_send_hour,
        "items": items,
        "variables": variables,
        "sms_fallback_text": _entries_to_sms(company_name, entries),
        "would_send": not blockers,
        "blockers": blockers,
        # 사용자가 설정한 맞춤 알림 규칙(#4) 원값 — 미설정 시 None/[](UI 칩은 설정 시에만).
        "min_score": cfg.min_score if cfg is not None else None,
        "excluded_sources": list(cfg.excluded_sources or []) if cfg is not None else [],
    }


@celery_app.task(name="notifications.send_daily_briefings")
def send_daily_briefings() -> dict:
    """수신동의(enabled) AND 구독(active/trialing) 기업 루프 → 개별 브리핑 디스패치.

    Returns: {"dispatched": <건수>, "skipped": <대상 외>}.
    """
    db = SessionLocal()
    dispatched = 0
    skipped = 0
    try:
        today = _today_kst()
        rows = db.execute(
            select(Company, Subscription)
            .join(NotificationSetting, NotificationSetting.company_id == Company.id)
            .join(Subscription, Subscription.company_id == Company.id)
            .where(NotificationSetting.enabled.is_(True))
        ).all()
        for company, sub in rows:
            # 구독 게이트(billing.md §6): active/trialing 만 발송 대상.
            if not active_subscribed(sub.status):
                skipped += 1
                continue
            send_company_briefing.delay(str(company.id), today.isoformat())
            dispatched += 1
        logger.info("send_daily_briefings: dispatched=%d skipped=%d", dispatched, skipped)
        return {"dispatched": dispatched, "skipped": skipped}
    finally:
        db.close()


def _reminder_text(company_name: str, opp, today: date) -> str:
    """마감 리마인더 단문(SMS/LMS) 본문."""
    return (
        f"[WaterNature] {company_name}님, 관심 공고 '{opp.title}' 마감이 "
        f"{_d_day(opp.deadline, today)} 입니다. 잊지 마세요!"
    )


@celery_app.task(name="notifications.send_deadline_reminders")
def send_deadline_reminders(*, _provider: NotificationProvider | None = None) -> dict:
    """관심/진행 공고 마감 임박분 리마인더(SMS/LMS). 멱등: deadline_reminded 액션(마감일 키).

    대상: 구독(active/trialing) + 알림 enabled + phone 보유. 윈도우=cfg.deadline_reminder_days
    (기본 3, 0=끄기). 실 발송은 SOLAPI 키 게이트 — 키 없으면 send 실패 → 기록 안 함(다음날 재시도).

    Returns: {"sent","skipped","failed"}.
    """
    db = SessionLocal()
    sent = skipped = failed = 0
    try:
        today = _today_kst()
        rows = db.execute(
            select(Company, Subscription)
            .join(NotificationSetting, NotificationSetting.company_id == Company.id)
            .join(Subscription, Subscription.company_id == Company.id)
            .where(NotificationSetting.enabled.is_(True))
        ).all()
        provider = _provider if _provider is not None else SolapiProvider()
        for company, sub in rows:
            if not active_subscribed(sub.status) or not company.phone:
                continue
            cfg = db.get(NotificationSetting, company.id)
            due = upcoming_reminders(db, company.id, reminder_days_for(cfg))
            for opp, _score, _via in due:
                iso = opp.deadline.date().isoformat()
                action = db.scalar(
                    select(UserOpportunityAction).where(
                        UserOpportunityAction.company_id == company.id,
                        UserOpportunityAction.opportunity_id == opp.id,
                        UserOpportunityAction.action_type == "deadline_reminded",
                    )
                )
                if action is not None and (action.meta or {}).get("deadline") == iso:
                    skipped += 1  # 이미 이 마감으로 리마인드함(멱등)
                    continue
                try:
                    provider.send_sms(company.phone, _reminder_text(company.name, opp, today))
                except Exception:  # noqa: BLE001 (키 미설정 등 — 미기록, 다음날 재시도)
                    failed += 1
                    continue
                if action is None:
                    db.add(UserOpportunityAction(
                        company_id=company.id, opportunity_id=opp.id,
                        action_type="deadline_reminded", meta={"deadline": iso},
                    ))
                else:
                    action.meta = {"deadline": iso}  # 마감 변경(정정) → 재리마인드 허용
                sent += 1
        db.commit()
        logger.info(
            "send_deadline_reminders: sent=%d skipped=%d failed=%d", sent, skipped, failed
        )
        return {"sent": sent, "skipped": skipped, "failed": failed}
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@celery_app.task(name="notifications.send_company_briefing")
def send_company_briefing(
    company_id: str,
    briefing_date: str,
    *,
    _provider: NotificationProvider | None = None,
) -> str:
    """기업별 브리핑 발송(멱등). 카카오 알림톡 → notifications + notified 액션.

    Args:
        company_id: 회사 UUID 문자열.
        briefing_date: 발송 기준일(ISO date). 멱등 키.
        _provider: 테스트 모킹용 NotificationProvider 주입. None이면 SolapiProvider.

    Returns: 처리 결과 문자열("sent"|"failed"|"fallback_sent"|"skip:*").
    """
    db = SessionLocal()
    try:
        cid = uuid.UUID(company_id)
        bdate = date.fromisoformat(briefing_date)

        # 멱등: 이미 해당 일자 발송 레코드 존재 시 종료.
        existing = db.scalar(
            select(Notification).where(
                Notification.company_id == cid,
                Notification.briefing_date == bdate,
            )
        )
        if existing is not None:
            logger.info("send_company_briefing: 이미 발송됨 (company=%s date=%s)", cid, bdate)
            return "skip:already_sent"

        company = db.get(Company, cid)
        if company is None:
            logger.warning("send_company_briefing: 회사 없음 %s", cid)
            return "skip:no_company"

        cfg = db.get(NotificationSetting, cid)
        if cfg is not None and not cfg.enabled:
            return "skip:disabled"

        # 수신처 = companies.phone. 없으면 skip + warn (발송 불가).
        if not company.phone:
            logger.warning("send_company_briefing: phone 없음 — skip (company=%s)", cid)
            return "skip:no_phone"

        entries = _briefing_entries(db, cid, cfg)  # AI Top-N + 키워드 매칭(hidden·제외소스 적용)
        send_empty = bool(cfg.send_empty) if cfg is not None else False
        if not entries and not send_empty:
            logger.info("send_company_briefing: 추천 0건 — skip (company=%s)", cid)
            return "skip:no_matches"

        variables = render_briefing_variables(company.name, entries, bdate)
        template_code = settings.kakao_template_briefing
        opp_ids = [opp.id for opp, _, _ in entries]

        notif = Notification(
            id=uuid.uuid4(),
            company_id=cid,
            briefing_date=bdate,
            channel="alimtalk",
            template_code=template_code or None,
            payload={
                "variables": variables,
                "opportunity_ids": [str(oid) for oid in opp_ids],
            },
            status="queued",
            provider=settings.kakao_provider,
        )
        db.add(notif)
        db.flush()

        provider = _provider if _provider is not None else SolapiProvider()
        result_status = "sent"
        try:
            res = provider.send_alimtalk(company.phone, template_code, variables)
            notif.status = "sent"
            notif.provider_msg_id = res.provider_msg_id
            notif.sent_at = datetime.now(timezone.utc)
        except NotRegisteredOrBlocked as exc:
            # 폴백: SMS/LMS 대체발송(설정 시).
            if settings.notify_fallback_sms:
                try:
                    res = provider.send_sms(company.phone, _entries_to_sms(company.name, entries))
                    notif.status = "fallback_sent"
                    notif.provider_msg_id = res.provider_msg_id
                    notif.sent_at = datetime.now(timezone.utc)
                    result_status = "fallback_sent"
                except Exception as exc2:  # noqa: BLE001
                    notif.status = "failed"
                    notif.error_message = f"alimtalk:{exc} / sms:{exc2}"
                    result_status = "failed"
            else:
                notif.status = "failed"
                notif.error_message = str(exc)
                result_status = "failed"
        except Exception as exc:  # noqa: BLE001  (키 미설정 RuntimeError 포함)
            notif.status = "failed"
            notif.error_message = str(exc)
            result_status = "failed"

        # 발송 시도(성공/폴백)면 퍼널 'notified' 액션 기록.
        if result_status in ("sent", "fallback_sent"):
            for oid in opp_ids:
                db.add(
                    UserOpportunityAction(
                        id=uuid.uuid4(),
                        company_id=cid,
                        opportunity_id=oid,
                        action_type="notified",
                    )
                )

        db.commit()
        logger.info(
            "send_company_briefing: company=%s status=%s entries=%d",
            cid, result_status, len(entries),
        )
        return result_status
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
