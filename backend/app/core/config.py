"""앱 설정 (pydantic-settings). .env 로 주입. 정본: docs 04-architecture/*."""
from __future__ import annotations

from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # App
    app_env: str = "local"
    api_v1_prefix: str = "/api/v1"
    tz: str = "Asia/Seoul"
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    # Infra
    database_url: str = "postgresql+psycopg://bizradar:bizradar@localhost:5432/bizradar"
    redis_url: str = "redis://localhost:6379/0"

    # 운영자(플랫폼 집계 North Star 지표 접근) 이메일 — 쉼표 구분. 비면 운영 지표 비활성.
    admin_emails: str = ""

    # Auth
    jwt_alg: str = "HS256"
    jwt_secret: str = "change-me"
    jwt_access_ttl_min: int = 30
    jwt_refresh_ttl_days: int = 14
    # DB 저장 시크릿(LLM API 키 등) 대칭 암호화 마스터 키. 미설정 시 jwt_secret 파생.
    # 운영에서는 강한 랜덤값 권장(변경 시 기존 암호문 복호화 불가).
    app_secret_key: str = ""
    # 리프레시 토큰은 httpOnly 쿠키로 보관(XSS 탈취 차단). access 토큰은 클라 메모리+
    # Authorization 헤더 유지 → API는 헤더 인증 그대로(CSRF 표면 최소).
    refresh_cookie_name: str = "bizradar_refresh"
    # 리프레시 쿠키는 1st-party fetch(/auth/refresh·/logout)에서만 쓰이므로 strict로 둬도
    # 비용이 없고 CSRF·Lax 유예창 모호성을 제거한다.
    cookie_samesite: str = "strict"

    # Collectors
    ingest_buffer_days: int = 2
    ingest_backfill_days: int = 90
    ingest_max_pages: int = 200
    http_timeout_connect: float = 5.0
    http_timeout_read: float = 30.0
    narajangter_service_key: str = ""
    # base는 /1230000 뒤 서비스 경로 prefix(/ad,/as,/ao)까지 포함해야 함(명세 확인).
    # prefix 누락 시 404 — docs/06-data api ref/README-narajangter-api.md §0 참고.
    narajangter_base_url: str = "https://apis.data.go.kr/1230000/ad/BidPublicInfoService"
    narajangter_scsbid_base_url: str = "https://apis.data.go.kr/1230000/as/ScsbidInfoService"
    narajangter_opnstd_base_url: str = "https://apis.data.go.kr/1230000/ao/PubDataOpnStdService"
    bizinfo_crtfc_key: str = ""
    bizinfo_base_url: str = "https://www.bizinfo.go.kr/uss/rss/bizinfoApi.do"
    bizinfo_page_unit: int = 100          # 기업마당 페이지당 건수
    ingest_seen_streak_stop: int = 50     # 역순 cutoff: 연속 seen 임계(서버 날짜필터 부재 대비)
    detail_http_delay_ms: int = 500       # 상세 페이지 정중한 요청 간격(ms)
    llm_detail_model: str = "claude-opus-4-8"  # 상세 보강 추출(최신 Claude)
    kstartup_service_key: str = ""
    kstartup_base_url: str = "https://apis.data.go.kr/B552735/kisedKstartupService01"
    ntis_mode: str = "api"
    ntis_service_key: str = ""
    # 보안: 서비스키가 쿼리스트링으로 전송되므로 평문 http 금지(MITM 키 유출). https 고정.
    ntis_base_url: str = "https://apis.data.go.kr/1721000/msitannouncementinfo"

    # Collection schedule — 매일 KST 09:00 수집 (celery timezone=Asia/Seoul).
    collect_schedule_hour: int = 9
    collect_schedule_minute: int = 0

    # Embedding (벡터 저장/검색 = PostgreSQL pgvector. 별도 벡터 DB 없음.)
    embedding_provider: str = "bge"
    embedding_model: str = "intfloat/multilingual-e5-large"
    embedding_dim: int = 1024          # pgvector vector(N) 차원 — 변경 시 마이그레이션 필요
    embedding_version: str = "e5-large:v1"
    # voyage_api_key: str = ""        # 제거 (voyage → fastembed BGE 교체)
    # Qdrant 제거(pgvector로 통합). 복귀 필요 시 아래 + qdrant-client + compose 복원.
    # qdrant_url: str = "http://localhost:6333"
    # qdrant_api_key: str = ""

    # Matching
    match_threshold: int = 35  # LLM off·fallback 현실 상한 ~55(tech30+industry15+region10), 도메인 일치만 통과
    match_retrieval_top_n: int = 50
    # 매칭 시 LLM 재평가는 규칙점수 상위 K개 공고에만 적용(비용·지연 제어). 0이면 전체.
    match_llm_top_k: int = 10

    # ── LLM 공급자 (멀티: anthropic | openai | gemini) ──────────────────
    # 기본 공급자. 런타임 선택은 DB app_settings('llm')가 .env 기본값을 덮는다.
    # 키는 .env 기본값 또는 설정 UI 입력값을 암호화해 app_settings(DB)에 저장(set_provider_key).
    llm_provider: str = "anthropic"
    # Anthropic (Claude) — 키 넣으면 AI 근거 활성(optional)
    llm_model: str = "claude-opus-4-8"      # = Anthropic 모델
    anthropic_api_key: str = ""
    # OpenAI
    openai_api_key: str = ""
    openai_model: str = "gpt-5.4"
    # Google Gemini
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.5-flash"

    # Notification
    kakao_provider: str = "solapi"
    kakao_sender_key: str = ""          # 발신프로필(pfId) — SOLAPI 알림톡 from
    kakao_template_briefing: str = ""   # 승인된 알림톡 템플릿 코드
    # SOLAPI 인증(API Key/Secret + HMAC-SHA256). 사업자·발신프로필 확보 후 주입.
    solapi_api_key: str = ""
    solapi_api_secret: str = ""
    solapi_base_url: str = "https://api.solapi.com"
    notify_send_hour: int = 8
    notify_fallback_sms: bool = True
    briefing_top_n: int = 3

    # Billing (test 모드 — 사업자 확보 전 live 불가)
    payment_provider: str = "toss"
    toss_mode: str = "test"
    toss_client_key: str = ""
    toss_secret_key: str = ""
    # 웹훅 서명 검증용 공유 시크릿(HMAC-SHA256). 미설정 시 웹훅은 fail-closed(401).
    toss_webhook_secret: str = ""
    billing_plan_default: str = "basic_monthly"

    @property
    def cookie_secure(self) -> bool:
        """운영(비-local)에선 https 전제 → Secure 쿠키. local http 개발에선 비활성."""
        return self.app_env.strip().lower() != "local"

    @model_validator(mode="after")
    def _enforce_prod_secrets(self) -> "Settings":
        """비-local 환경에서 약한 시크릿이면 부팅 거부(fail-closed).

        local 기본값에서는 무동작 → 개발 흐름 영향 없음. 공개 저장소라 시크릿이 약하면
        토큰 위조·저장키(LLM/카카오) 복호화가 가능하므로, 운영에서는 'change-me'·빈 값뿐
        아니라 **32자 미만**도 거부한다(JWT_SECRET=서명키, APP_SECRET_KEY=암호화 마스터키).
        """
        if self.app_env.strip().lower() != "local":
            weak: list[str] = []
            if self.jwt_secret in ("", "change-me") or len(self.jwt_secret) < 32:
                weak.append("JWT_SECRET(>=32 chars)")
            if not self.app_secret_key or len(self.app_secret_key) < 32:
                # 저장 시크릿 암호화 마스터키 — 짧으면 DB 유출 시 brute-force 위험.
                weak.append("APP_SECRET_KEY(>=32 chars)")
            if weak:
                raise ValueError(
                    f"APP_ENV={self.app_env}에서 안전하지 않은 시크릿: "
                    f"{', '.join(weak)} — 강한 랜덤값으로 설정해야 부팅됩니다."
                )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
