"""통합: send_company_briefing(카카오 알림톡) — notifications channel=alimtalk · 멱등.

실 PG(alembic 스키마) + SolapiProvider 모킹(외부 실호출 0). TEST_DATABASE_URL 없으면 skip.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.services.notifications.provider import NotRegisteredOrBlocked, SendResult

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL not set — integration test skipped",
)


# ── SessionLocal 패치 헬퍼(공유 트랜잭션 보존) ───────────────────────────────

class _NoCloseSession:
    """공유 트랜잭션 보존 래퍼: close/rollback no-op, commit→flush.

    태스크 내부 db.commit()이 conftest의 외부 트랜잭션을 닫지 않도록 flush로 강등.
    검증은 같은 세션에서 읽고, 격리는 conftest rollback이 담당.
    """

    def __init__(self, session):
        self._s = session

    def __getattr__(self, name):
        return getattr(self._s, name)

    def commit(self):
        self._s.flush()

    def close(self):
        pass

    def rollback(self):
        pass


def _patch_session(db_session):
    return patch(
        "app.services.notifications.tasks.SessionLocal",
        return_value=_NoCloseSession(db_session),
    )


# ── 픽스처: 회사 + phone + 추천(matches/opportunities) ──────────────────────

@pytest.fixture()
def briefing_ctx(db_session):
    from app.core.config import settings
    from app.db.models.accounts import Company
    from app.db.models.opportunity import Match, Opportunity

    cid = uuid.uuid4()
    db_session.add(
        Company(id=cid, name="브리핑테스트기업", phone="01012345678", onboarding_status="ready")
    )
    db_session.flush()

    opp_ids = []
    for i in range(3):
        oid = uuid.uuid4()
        opp_ids.append(oid)
        db_session.add(
            Opportunity(
                id=oid,
                source="bizinfo",
                source_uid=f"brief-{oid}",
                title=f"공공 사업 {i}",
                agency="행안부",
                region="서울",
                category="IT",
                status="open",
                is_canonical=True,
                deadline=datetime.now(timezone.utc) + timedelta(days=10 + i),
                budget_raw="1억원",
                raw_json={},
                content_hash=f"hash{i}" + "0" * 58,
            )
        )
    # 공고 먼저 flush(FK 충족) — Match↔Opportunity relationship 미정의라 UoW 순서 보장 안 됨.
    db_session.flush()
    for i, oid in enumerate(opp_ids):
        db_session.add(
            Match(
                id=uuid.uuid4(),
                company_id=cid,
                opportunity_id=oid,
                score=settings.match_threshold + 10 + i,
            )
        )
    db_session.flush()
    return {"company_id": cid, "opp_ids": opp_ids}


def _today() -> str:
    return datetime.now().date().isoformat()


# ── 테스트 ───────────────────────────────────────────────────────────────────

class TestSendCompanyBriefing:
    def test_sends_alimtalk_and_records(self, db_session, briefing_ctx):
        from sqlalchemy import select

        from app.db.models.notification import Notification
        from app.db.models.opportunity import UserOpportunityAction
        from app.services.notifications.tasks import send_company_briefing

        provider = MagicMock()
        provider.send_alimtalk.return_value = SendResult(
            provider_msg_id="M1", channel="alimtalk"
        )

        with _patch_session(db_session), patch(
            "app.services.notifications.tasks.settings"
        ) as s:
            s.briefing_top_n = 3
            s.match_threshold = 0  # _top_matches 가 db_session 쓰므로 패치된 settings 사용
            s.kakao_template_briefing = "TMPL"
            s.kakao_provider = "solapi"
            s.notify_fallback_sms = True
            result = send_company_briefing(
                str(briefing_ctx["company_id"]), _today(), _provider=provider
            )

        assert result == "sent"
        provider.send_alimtalk.assert_called_once()
        # 인자: phone, template_code, variables
        call = provider.send_alimtalk.call_args
        assert call.args[0] == "01012345678"
        assert "회사명" in call.args[2]

        notif = db_session.scalar(
            select(Notification).where(
                Notification.company_id == briefing_ctx["company_id"]
            )
        )
        assert notif is not None
        assert notif.channel == "alimtalk"
        assert notif.status == "sent"
        assert notif.provider_msg_id == "M1"

        # notified 액션 3건(공고 수)
        actions = db_session.scalars(
            select(UserOpportunityAction).where(
                UserOpportunityAction.company_id == briefing_ctx["company_id"],
                UserOpportunityAction.action_type == "notified",
            )
        ).all()
        assert len(actions) == 3

    def test_idempotent_second_call_skips(self, db_session, briefing_ctx):
        from sqlalchemy import func, select

        from app.db.models.notification import Notification
        from app.services.notifications.tasks import send_company_briefing

        provider = MagicMock()
        provider.send_alimtalk.return_value = SendResult("M1", "alimtalk")

        with _patch_session(db_session), patch(
            "app.services.notifications.tasks.settings"
        ) as s:
            s.briefing_top_n = 3
            s.match_threshold = 0
            s.kakao_template_briefing = "TMPL"
            s.kakao_provider = "solapi"
            s.notify_fallback_sms = True
            r1 = send_company_briefing(
                str(briefing_ctx["company_id"]), _today(), _provider=provider
            )
            r2 = send_company_briefing(
                str(briefing_ctx["company_id"]), _today(), _provider=provider
            )

        assert r1 == "sent"
        assert r2 == "skip:already_sent"
        # 알림톡은 1회만 호출(멱등).
        assert provider.send_alimtalk.call_count == 1
        count = db_session.scalar(
            select(func.count()).select_from(Notification).where(
                Notification.company_id == briefing_ctx["company_id"]
            )
        )
        assert count == 1

    def test_no_phone_skips(self, db_session):
        from app.db.models.accounts import Company
        from app.services.notifications.tasks import send_company_briefing

        cid = uuid.uuid4()
        db_session.add(Company(id=cid, name="노폰", onboarding_status="ready"))
        db_session.flush()

        provider = MagicMock()
        with _patch_session(db_session), patch(
            "app.services.notifications.tasks.settings"
        ) as s:
            s.briefing_top_n = 3
            s.match_threshold = 0
            s.kakao_template_briefing = "TMPL"
            s.kakao_provider = "solapi"
            s.notify_fallback_sms = True
            result = send_company_briefing(str(cid), _today(), _provider=provider)

        assert result == "skip:no_phone"
        provider.send_alimtalk.assert_not_called()

    def test_fallback_to_sms_on_not_registered(self, db_session, briefing_ctx):
        from sqlalchemy import select

        from app.db.models.notification import Notification
        from app.services.notifications.tasks import send_company_briefing

        provider = MagicMock()
        provider.send_alimtalk.side_effect = NotRegisteredOrBlocked("3008")
        provider.send_sms.return_value = SendResult("SMS1", "sms")

        with _patch_session(db_session), patch(
            "app.services.notifications.tasks.settings"
        ) as s:
            s.briefing_top_n = 3
            s.match_threshold = 0
            s.kakao_template_briefing = "TMPL"
            s.kakao_provider = "solapi"
            s.notify_fallback_sms = True
            result = send_company_briefing(
                str(briefing_ctx["company_id"]), _today(), _provider=provider
            )

        assert result == "fallback_sent"
        provider.send_sms.assert_called_once()
        notif = db_session.scalar(
            select(Notification).where(
                Notification.company_id == briefing_ctx["company_id"]
            )
        )
        assert notif.status == "fallback_sent"
        assert notif.provider_msg_id == "SMS1"

class TestBriefingPreview:
    def test_preview_renders_items_and_diagnoses_blockers(self, db_session, briefing_ctx):
        from app.services.notifications.tasks import build_briefing_preview

        with patch("app.services.notifications.tasks.settings") as s:
            s.briefing_top_n = 3
            s.match_threshold = 0
            s.notify_send_hour = 8
            s.solapi_api_key = ""
            s.solapi_api_secret = ""
            s.kakao_sender_key = ""
            s.kakao_template_briefing = ""
            preview = build_briefing_preview(db_session, briefing_ctx["company_id"])

        assert preview["company_name"] == "브리핑테스트기업"
        assert preview["count"] == 3
        assert len(preview["items"]) == 3
        # 점수 내림차순(상위 매칭 먼저)
        assert preview["items"][0]["score"] >= preview["items"][1]["score"]
        assert preview["items"][0]["title"].startswith("공공 사업")
        assert "회사명" in preview["variables"]
        assert preview["sms_fallback_text"].startswith("[WaterNature]")
        # 키 미설정 + 미구독 → 발송 불가 + 차단요인 진단
        assert preview["would_send"] is False
        assert any("SOLAPI" in b for b in preview["blockers"])
        assert any("미구독" in b for b in preview["blockers"])

    def test_no_keys_records_failed(self, db_session, briefing_ctx):
        """provider 미주입 → SolapiProvider 키 없음 RuntimeError → status=failed(죽지 않음)."""
        from sqlalchemy import select

        from app.db.models.notification import Notification
        from app.services.notifications.tasks import send_company_briefing

        with _patch_session(db_session), patch(
            "app.services.notifications.tasks.settings"
        ) as s:
            s.briefing_top_n = 3
            s.match_threshold = 0
            s.kakao_template_briefing = ""
            s.kakao_provider = "solapi"
            s.notify_fallback_sms = False
            # _provider 미주입 → SolapiProvider() 생성, 키 없음(real settings 빈값).
            result = send_company_briefing(str(briefing_ctx["company_id"]), _today())

        assert result == "failed"
        notif = db_session.scalar(
            select(Notification).where(
                Notification.company_id == briefing_ctx["company_id"]
            )
        )
        assert notif.status == "failed"
        assert notif.error_message is not None
