"""나라장터 낙찰정보 수집기 (ScsbidInfoService, 서비스2).

정본: docs/06-data api ref/README-narajangter-api.md §4.
오퍼레이션 4종(물품/용역/공사/외자), inqryDiv=1(등록일시) 기준 증분.
source = 'narajangter_scsbid', source_uid = f"{bidNtceNo}-{bidNtceOrd}-{bidClsfcNo}-{rbidNo}".

BaseCollector.run()을 상속하지 않음 — opportunities+embed 전용 파이프라인과 무관.
awards는 임베딩·변경이력·dedup 대상이 아님.
"""
from __future__ import annotations

import logging
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from itertools import count
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models.opportunity import OpportunityAward, SourceIngestionState
from app.services.collectors._redact import redact_secrets
from app.services.collectors.client import DataGoKrClient
from app.services.collectors.normalize import parse_kst, parse_won, sha256_norm

logger = logging.getLogger(__name__)

# (오퍼레이션 이름, 업무유형 category 레이블)
SCSBID_OPS: list[tuple[str, str]] = [
    ("getScsbidListSttusThng", "물품"),
    ("getScsbidListSttusServc", "용역"),
    ("getScsbidListSttusCnstwk", "공사"),
    ("getScsbidListSttusFrgcpt", "외자"),
]

_FMT = "%Y%m%d%H%M"   # inqryBgnDt / inqryEndDt 포맷
_NUM_OF_ROWS = 1000
SOURCE_CODE = "narajangter_scsbid"


@dataclass
class AwardDTO:
    """낙찰정보 DTO — OpportunityAward 매핑용."""
    source: str
    source_uid: str
    bid_ntce_no: str | None
    bid_ntce_ord: int | None
    bid_clsfc_no: str | None
    rbid_no: str | None
    category: str | None
    title: str | None
    winner_name: str | None
    winner_bizno: str | None
    award_amount: int | None
    award_rate: Decimal | None
    participant_count: int | None
    demand_agency: str | None
    real_opening_at: datetime | None
    final_award_date: date | None
    registered_at: datetime | None
    content_hash: str
    raw_json: dict


def _parse_fnl_sucsf_date(value: str | None) -> date | None:
    """fnlSucsfDate: 'yyyy-MM-dd' (날짜만). None/빈값 → None."""
    if not value:
        return None
    s = str(value).strip()
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        logger.warning("scsbid: fnlSucsfDate 파싱 실패 — value=%r", value)
        return None


def parse_award_item(raw: dict, category: str) -> AwardDTO:
    """raw item dict → AwardDTO.

    필드 매핑: README §4.3 기준. 전 필드 .get() 방어.
    source_uid = f"{bidNtceNo}-{bidNtceOrd}-{bidClsfcNo}-{rbidNo}"
    content_hash = sha256_norm(bid_ntce_no, bid_ntce_ord, winner_bizno, award_amount, final_award_date)
    """
    bid_ntce_no: str | None = raw.get("bidNtceNo") or None
    bid_ntce_ord_raw = raw.get("bidNtceOrd")
    bid_ntce_ord: int | None = None
    if bid_ntce_ord_raw is not None:
        try:
            bid_ntce_ord = int(bid_ntce_ord_raw)
        except (ValueError, TypeError):
            logger.warning("scsbid: bidNtceOrd 변환 실패 — value=%r", bid_ntce_ord_raw)

    bid_clsfc_no: str | None = raw.get("bidClsfcNo") or None
    rbid_no: str | None = raw.get("rbidNo") or None

    # source_uid 조합
    source_uid = (
        f"{bid_ntce_no or ''}-{bid_ntce_ord_raw or ''}"
        f"-{bid_clsfc_no or ''}-{rbid_no or ''}"
    )

    title: str | None = (raw.get("bidNtceNm") or "").strip() or None
    winner_name: str | None = raw.get("bidwinnrNm") or None
    winner_bizno: str | None = raw.get("bidwinnrBizno") or None

    # 낙찰금액: sucsfbidAmt (숫자 문자열 또는 숫자)
    award_amount: int | None = parse_won(str(raw["sucsfbidAmt"]) if raw.get("sucsfbidAmt") is not None else None)

    # 낙찰률: sucsfbidRate
    award_rate: Decimal | None = None
    rate_raw = raw.get("sucsfbidRate")
    if rate_raw is not None:
        try:
            award_rate = Decimal(str(rate_raw))
        except Exception:  # noqa: BLE001
            logger.warning("scsbid: sucsfbidRate 변환 실패 — value=%r", rate_raw)

    # 참가업체수
    participant_count: int | None = None
    prtcpt_raw = raw.get("prtcptCnum")
    if prtcpt_raw is not None:
        try:
            participant_count = int(prtcpt_raw)
        except (ValueError, TypeError):
            pass

    demand_agency: str | None = raw.get("dminsttNm") or None
    real_opening_at: datetime | None = parse_kst(raw.get("rlOpengDt"))
    final_award_date: date | None = _parse_fnl_sucsf_date(raw.get("fnlSucsfDate"))
    registered_at: datetime | None = parse_kst(raw.get("rgstDt"))

    content_hash = sha256_norm(
        bid_ntce_no, bid_ntce_ord, winner_bizno, award_amount, final_award_date
    )

    return AwardDTO(
        source=SOURCE_CODE,
        source_uid=source_uid,
        bid_ntce_no=bid_ntce_no,
        bid_ntce_ord=bid_ntce_ord,
        bid_clsfc_no=bid_clsfc_no,
        rbid_no=rbid_no,
        category=category,
        title=title,
        winner_name=winner_name,
        winner_bizno=winner_bizno,
        award_amount=award_amount,
        award_rate=award_rate,
        participant_count=participant_count,
        demand_agency=demand_agency,
        real_opening_at=real_opening_at,
        final_award_date=final_award_date,
        registered_at=registered_at,
        content_hash=content_hash,
        raw_json=raw,
    )


class ScsbidCollector:
    """나라장터 낙찰정보 수집기.

    BaseCollector를 상속하지 않음(임베딩·변경이력·dedup 불필요).
    client / session_factory를 생성자에서 주입받아 테스트 용이성 확보.
    """

    source_code = SOURCE_CODE

    def __init__(
        self,
        client: DataGoKrClient | None = None,
        session_factory: Callable | None = None,
    ) -> None:
        if client is None:
            self.client = DataGoKrClient(
                settings.narajangter_scsbid_base_url,
                settings.narajangter_service_key,
            )
        else:
            self.client = client

        self._session_factory = session_factory

    def _get_session_factory(self) -> Callable:
        if self._session_factory is not None:
            return self._session_factory
        from app.db.base import SessionLocal  # noqa: PLC0415
        return SessionLocal

    def _get_state(self, db: Session) -> SourceIngestionState:
        state = db.get(SourceIngestionState, self.source_code)
        if state is None:
            state = SourceIngestionState(source=self.source_code)
            db.add(state)
            db.commit()
        return state

    def _window(self, state: SourceIngestionState) -> tuple[datetime, datetime]:
        end = datetime.now(timezone.utc)
        if state.last_success_at:
            begin = state.last_success_at - timedelta(days=settings.ingest_buffer_days)
        else:
            begin = end - timedelta(days=settings.ingest_backfill_days)
        return begin, end

    def iter_pages(self, begin: datetime, end: datetime) -> Iterator[tuple[list[dict], str]]:
        """4개 업무유형 순회, 페이지 단위로 (items, category) yield."""
        bgn_str = begin.strftime(_FMT)
        end_str = end.strftime(_FMT)

        for op, category in SCSBID_OPS:
            fetched_total = 0
            for page in count(1):
                payload = self.client.get(op, {
                    "inqryDiv": 1,
                    "inqryBgnDt": bgn_str,
                    "inqryEndDt": end_str,
                    "pageNo": page,
                    "numOfRows": _NUM_OF_ROWS,
                })
                items = self.client.items(payload)
                total_count = self.client.total_count(payload)

                if not items:
                    break

                yield items, category
                fetched_total += len(items)

                if len(items) < _NUM_OF_ROWS:
                    break
                if total_count is not None and fetched_total >= total_count:
                    break
                if page >= settings.ingest_max_pages:
                    logger.warning(
                        "scsbid: MAX_PAGES(%d) 초과 — op=%s, fetched=%d",
                        settings.ingest_max_pages, op, fetched_total,
                    )
                    break

    def _upsert(self, db: Session, dto: AwardDTO) -> bool:
        """(source, source_uid)로 UPSERT. 변경 있으면 True, 없으면 False.

        임베딩 enqueue 없음. opportunity_changes 적재 없음.
        """
        existing = db.scalar(
            select(OpportunityAward).where(
                OpportunityAward.source == dto.source,
                OpportunityAward.source_uid == dto.source_uid,
            )
        )
        now = datetime.now(timezone.utc)

        if existing is None:
            award = OpportunityAward(
                source=dto.source,
                source_uid=dto.source_uid,
                bid_ntce_no=dto.bid_ntce_no,
                bid_ntce_ord=dto.bid_ntce_ord,
                bid_clsfc_no=dto.bid_clsfc_no,
                rbid_no=dto.rbid_no,
                category=dto.category,
                title=dto.title,
                winner_name=dto.winner_name,
                winner_bizno=dto.winner_bizno,
                award_amount=dto.award_amount,
                award_rate=dto.award_rate,
                participant_count=dto.participant_count,
                demand_agency=dto.demand_agency,
                real_opening_at=dto.real_opening_at,
                final_award_date=dto.final_award_date,
                registered_at=dto.registered_at,
                content_hash=dto.content_hash,
                raw_json=dto.raw_json,
                collected_at=now,
                last_seen_at=now,
            )
            db.add(award)
            db.commit()
            return True

        if existing.content_hash != dto.content_hash:
            existing.bid_ntce_no = dto.bid_ntce_no
            existing.bid_ntce_ord = dto.bid_ntce_ord
            existing.bid_clsfc_no = dto.bid_clsfc_no
            existing.rbid_no = dto.rbid_no
            existing.category = dto.category
            existing.title = dto.title
            existing.winner_name = dto.winner_name
            existing.winner_bizno = dto.winner_bizno
            existing.award_amount = dto.award_amount
            existing.award_rate = dto.award_rate
            existing.participant_count = dto.participant_count
            existing.demand_agency = dto.demand_agency
            existing.real_opening_at = dto.real_opening_at
            existing.final_award_date = dto.final_award_date
            existing.registered_at = dto.registered_at
            existing.content_hash = dto.content_hash
            existing.raw_json = dto.raw_json
            existing.last_seen_at = now
            db.commit()
            return True

        # 변경 없음 → last_seen_at 경량 갱신
        existing.last_seen_at = now
        db.commit()
        return False

    def run(self) -> int:
        """수집 실행. 반환값: 처리된 레코드 수."""
        session_factory = self._get_session_factory()
        db: Session = session_factory()
        total = 0
        try:
            state = self._get_state(db)
            begin, end = self._window(state)
            state.last_status = "running"
            state.last_run_at = datetime.now(timezone.utc)
            db.commit()

            for page_items, category in self.iter_pages(begin, end):
                for raw in page_items:
                    dto = parse_award_item(raw, category)
                    self._upsert(db, dto)
                    total += 1

            state.last_status = "success"
            state.last_success_at = end
            state.collected_count = total
            state.error_message = None
            db.commit()
            return total

        except Exception as exc:  # noqa: BLE001
            db.rollback()
            try:
                state = self._get_state(db)
                state.last_status = "failed"
                state.error_message = redact_secrets(str(exc))
                db.commit()
            except Exception:  # noqa: BLE001
                db.rollback()
            raise
        finally:
            db.close()
