"""수집 Celery 태스크. 06:00 run_all → 소스별 독립 실행(부분 실패 격리)."""
from __future__ import annotations

from celery.utils.log import get_task_logger

from app.core.celery_app import celery_app
from app.services.collectors._redact import redact_secrets
from app.services.collectors.registry import COLLECTORS

logger = get_task_logger(__name__)



@celery_app.task(
    name="collectors.run_all",
    bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=3,
)
def run_all(self) -> dict[str, int]:
    """등록된 수집기를 순차 실행. 소스 하나 실패가 전체를 막지 않도록 격리."""
    results: dict[str, int] = {}
    for code, cls in COLLECTORS.items():
        try:
            results[code] = cls().run()
        except Exception as exc:  # noqa: BLE001
            results[code] = -1
            # TODO: Sentry/Langfuse 알림
            logger.warning("collector %s failed: %s", code, redact_secrets(str(exc)))
    return results


@celery_app.task(name="collectors.narajangter")
def collect_narajangter() -> int:
    return COLLECTORS["narajangter"]().run()


@celery_app.task(name="collectors.run_scsbid")
def run_scsbid() -> int:
    """나라장터 낙찰정보(ScsbidInfoService) 수집. 임베딩 enqueue 없음."""
    from app.services.collectors.scsbid import ScsbidCollector  # noqa: PLC0415
    return ScsbidCollector().run()


@celery_app.task(
    name="collectors.enrich_detail",
    bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=4,
)
def enrich_detail(self, source_code: str, opp_id: str) -> None:
    """상세 본문 추출(requires_detail=True 소스). 정본: collector-base-bizinfo §3.4.

    임시 구현: 상세 추출은 기업마당 자체 키(BIZINFO_CRTFC_KEY)+상세 HTML 파서+LLM에 의존해
    아직 미구현. 워커 크래시 루프를 막고 추천 파이프라인에 태우기 위해, 우선 list 단계
    데이터로 **임베딩만 enqueue**한다(예산·자격은 추후 보강).
    TODO: 상세 HTML 파싱 + LLM 추출 → 보강 필드 UPDATE → content_hash 재계산 → 재임베딩
          (구조 파서 우선, 누락분만 LLM; collector-base-bizinfo §3.4).
    """
    from app.services.embedding.tasks import embed_opportunity  # noqa: PLC0415

    embed_opportunity.delay(opp_id)
