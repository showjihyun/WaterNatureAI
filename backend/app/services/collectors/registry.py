"""수집기 레지스트리. 신규 소스 = sources INSERT + 여기 등록.

운영 활성화: 나라장터만. 기업마당/K-Startup/NTIS는 BaseCollector로 구현·테스트
완료됐으나 운영 비활성(아래 사유) — 준비되면 COLLECTORS에 한 줄로 재등록.
  · bizinfo : BIZINFO_CRTFC_KEY 미보유 + enrich_detail(상세 추출) 미구현
  · kstartup: **활성 완료(2026-06-22)** — B552735 승인 확인, 라이브 필드/평면형 envelope 검증,
              최신순 _MAX_PAGES 한정 수집. COLLECTORS 등록됨.
  · ntis    : **활성 완료(2026-06-23)** — 15074634 승인+공식 명세 반영, 라이브 배열형 envelope
              (NtisClient)·필드(subject/viewUrl/deptName/pressDt) 확정. 마감 부재 → 게시일
              신선도 기반 status. COLLECTORS 등록됨.
구현 코드와 단위/통합/스모크 테스트는 보존(collector-base-bizinfo.md,
collector-kstartup-ntis.md). 활성화 시 `scripts/_probe_sources.py`로 라이브 응답 확인.
"""
from __future__ import annotations

from app.services.collectors.base import BaseCollector
from app.services.collectors.kstartup import KStartupCollector
from app.services.collectors.narajangter import NarajangterCollector
from app.services.collectors.ntis import NtisCollector

# 운영 활성 수집기 — run_all(09:00)이 순회.
COLLECTORS: dict[str, type[BaseCollector]] = {
    NarajangterCollector.source_code: NarajangterCollector,
    KStartupCollector.source_code: KStartupCollector,  # 활성(2026-06-22, B552735 승인 확인)
    NtisCollector.source_code: NtisCollector,  # 활성(2026-06-23, 15074634 승인+라이브 envelope 확정)
}

# 비활성(준비 시 위 dict로 이동) — import는 유지하지 않아 미사용 경고 방지:
#   from app.services.collectors.bizinfo import BizinfoCollector
#   from app.services.collectors.kstartup import KStartupCollector
#   from app.services.collectors.ntis import NtisCollector
