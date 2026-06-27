"""통합: GET /opportunities sort 파라미터 + posted_at 노출 + feasibility 필터.

- sort=score (기본) / deadline / posted / budget / feasibility 각각 검증.
- posted_at 필드가 응답에 포함되는지 확인.
- 미허용 sort 값 → score 폴백(200) 확인.
- /recommendations/today 응답에도 posted_at 포함 확인.
- feasibility 필터: go/no_go/review 단독, 조합(+sort=budget), 역량미설정=0건, 잘못된값=전체.
- TEST_DATABASE_URL 없으면 skip.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone, timedelta

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL not set — integration test skipped",
)


class _TxSession:
    """commit→flush (conftest rollback이 격리 담당)."""

    def __init__(self, session):
        self._s = session

    def __getattr__(self, name):
        return getattr(self._s, name)

    def commit(self):
        self._s.flush()


@pytest.fixture()
def client(db_session):
    from app.api.deps import get_current_company_id  # noqa: PLC0415
    from app.db.base import get_session  # noqa: PLC0415
    from app.main import app  # noqa: PLC0415

    tx = _TxSession(db_session)

    def _override_session():
        yield tx

    app.dependency_overrides[get_session] = _override_session
    try:
        yield TestClient(app, raise_server_exceptions=True)
    finally:
        app.dependency_overrides.pop(get_session, None)
        app.dependency_overrides.pop(get_current_company_id, None)


@pytest.fixture()
def auth(client):
    """register → (headers, company_id)."""
    email = f"sort_{uuid.uuid4().hex[:8]}@example.com"
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "passw0rd!", "company_name": "정렬테스트기업"},
    )
    assert resp.status_code == 201, resp.text
    token = resp.json()["access_token"]

    from app.core.security import decode_access_token  # noqa: PLC0415

    company_id = uuid.UUID(decode_access_token(token)["company_id"])
    return {"Authorization": f"Bearer {token}"}, company_id


def _make_opp(
    db_session,
    *,
    suffix: str,
    category: str = "용역",
    budget_amount: int | None = None,
    deadline_days: int | None = None,
    posted_days_ago: int | None = None,
    status: str = "open",
) -> uuid.UUID:
    """테스트용 공고를 삽입하고 ID를 반환."""
    from app.db.models.opportunity import Opportunity  # noqa: PLC0415

    now = datetime.now(timezone.utc)
    opp_id = uuid.uuid4()
    deadline = (now + timedelta(days=deadline_days)) if deadline_days is not None else None
    posted_at = (now - timedelta(days=posted_days_ago)) if posted_days_ago is not None else None

    opp = Opportunity(
        id=opp_id,
        source="narajangter",
        source_uid=f"sort_test_{suffix}_{opp_id.hex[:6]}",
        title=f"정렬테스트 공고 {suffix}",
        category=category,
        budget_amount=budget_amount,
        posted_at=posted_at,
        deadline=deadline,
        status=status,
        is_canonical=True,
        raw_json={},
        content_hash=("b" + suffix[:1]) * 32,
    )
    db_session.add(opp)
    db_session.flush()
    return opp_id


def _make_match(db_session, company_id: uuid.UUID, opp_id: uuid.UUID, score: int) -> None:
    from app.db.models.opportunity import Match  # noqa: PLC0415

    match = Match(
        company_id=company_id,
        opportunity_id=opp_id,
        score=score,
        reason=f"테스트 매칭 score={score}",
    )
    db_session.add(match)
    db_session.flush()


@pytest.fixture()
def seeded(auth, db_session, client):
    """4개 공고 + 매칭 시드. 반환: (headers, company_id, opp_ids dict)."""
    headers, company_id = auth

    # 역량 설정 (feasibility 테스트용)
    client.put(
        "/api/v1/company/profile",
        headers=headers,
        json={
            "tech_level": 3,
            "max_project_budget": 1_000_000_000,
            "capable_categories": ["용역"],
        },
    )

    # 공고 4개: 마감·등록일·예산·점수 각각 다름
    id_a = _make_opp(db_session, suffix="A", category="용역",
                     budget_amount=100_000_000, deadline_days=5,  posted_days_ago=10)
    id_b = _make_opp(db_session, suffix="B", category="물품",
                     budget_amount=500_000_000, deadline_days=30, posted_days_ago=3)
    id_c = _make_opp(db_session, suffix="C", category="용역",
                     budget_amount=200_000_000, deadline_days=15, posted_days_ago=7)
    id_d = _make_opp(db_session, suffix="D", category="공사",
                     budget_amount=900_000_000, deadline_days=2,  posted_days_ago=1)

    _make_match(db_session, company_id, id_a, score=90)
    _make_match(db_session, company_id, id_b, score=60)
    _make_match(db_session, company_id, id_c, score=75)
    _make_match(db_session, company_id, id_d, score=50)

    return headers, company_id, {"A": id_a, "B": id_b, "C": id_c, "D": id_d}


# ─── 기본 sort=score ──────────────────────────────────────────────────────────

def test_sort_score_default(client, seeded):
    """sort 미지정(기본=score) → 점수 내림차순."""
    headers, _, ids = seeded
    resp = client.get("/api/v1/opportunities", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    scores = [i["score"] for i in body["items"]]
    assert scores == sorted(scores, reverse=True), f"score desc 아님: {scores}"


def test_sort_score_explicit(client, seeded):
    """sort=score 명시 → 점수 내림차순."""
    headers, _, ids = seeded
    resp = client.get("/api/v1/opportunities?sort=score", headers=headers)
    assert resp.status_code == 200, resp.text
    scores = [i["score"] for i in resp.json()["items"]]
    assert scores == sorted(scores, reverse=True)


# ─── sort=deadline ────────────────────────────────────────────────────────────

def test_sort_deadline(client, seeded):
    """sort=deadline → 마감 임박순(asc), nulls last."""
    headers, _, ids = seeded
    resp = client.get("/api/v1/opportunities?sort=deadline", headers=headers)
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    deadlines = [i["deadline"] for i in items if i["deadline"] is not None]
    assert deadlines == sorted(deadlines), f"deadline asc 아님: {deadlines}"
    # 시드 기준: D(2일)<A(5일)<C(15일)<B(30일)
    opp_ids_in_order = [i["opportunity_id"] for i in items]
    assert opp_ids_in_order.index(str(ids["D"])) < opp_ids_in_order.index(str(ids["A"]))
    assert opp_ids_in_order.index(str(ids["A"])) < opp_ids_in_order.index(str(ids["C"]))
    assert opp_ids_in_order.index(str(ids["C"])) < opp_ids_in_order.index(str(ids["B"]))


# ─── sort=posted ──────────────────────────────────────────────────────────────

def test_sort_posted(client, seeded):
    """sort=posted → 최신 등록순(posted_at desc), nulls last."""
    headers, _, ids = seeded
    resp = client.get("/api/v1/opportunities?sort=posted", headers=headers)
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    posted_vals = [i["posted_at"] for i in items if i["posted_at"] is not None]
    assert posted_vals == sorted(posted_vals, reverse=True), f"posted_at desc 아님: {posted_vals}"
    # 시드 기준: D(1일전) > B(3일전) > C(7일전) > A(10일전)
    opp_ids_in_order = [i["opportunity_id"] for i in items]
    assert opp_ids_in_order.index(str(ids["D"])) < opp_ids_in_order.index(str(ids["B"]))
    assert opp_ids_in_order.index(str(ids["B"])) < opp_ids_in_order.index(str(ids["C"]))
    assert opp_ids_in_order.index(str(ids["C"])) < opp_ids_in_order.index(str(ids["A"]))


# ─── sort=budget ──────────────────────────────────────────────────────────────

def test_sort_budget(client, seeded):
    """sort=budget → 예산 큰 순(desc), nulls last."""
    headers, _, ids = seeded
    resp = client.get("/api/v1/opportunities?sort=budget", headers=headers)
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    budgets = [i["budget_amount"] for i in items if i["budget_amount"] is not None]
    assert budgets == sorted(budgets, reverse=True), f"budget desc 아님: {budgets}"
    # 시드 기준: D(9억)>B(5억)>C(2억)>A(1억)
    opp_ids_in_order = [i["opportunity_id"] for i in items]
    assert opp_ids_in_order.index(str(ids["D"])) < opp_ids_in_order.index(str(ids["B"]))
    assert opp_ids_in_order.index(str(ids["B"])) < opp_ids_in_order.index(str(ids["C"]))
    assert opp_ids_in_order.index(str(ids["C"])) < opp_ids_in_order.index(str(ids["A"]))


# ─── sort=feasibility ─────────────────────────────────────────────────────────

def test_sort_feasibility(client, seeded):
    """sort=feasibility → go(용역) 앞, no_go(물품·공사) 뒤."""
    headers, _, ids = seeded
    resp = client.get("/api/v1/opportunities?sort=feasibility", headers=headers)
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    verdicts = [
        (i["feasibility"]["verdict"] if i["feasibility"] else None)
        for i in items
    ]
    # go=0, review=1, no_go=2, None=3 — 오름차순이어야 함
    _RANK = {"go": 0, "review": 1, "no_go": 2, None: 3}
    ranks = [_RANK.get(v, 3) for v in verdicts]
    assert ranks == sorted(ranks), f"feasibility 정렬 틀림: {verdicts}"

    # 역량=용역 → A·C(용역)=go 가 앞에 와야 함
    go_ids = {str(ids["A"]), str(ids["C"])}
    nongo_ids = {str(ids["B"]), str(ids["D"])}
    opp_ids_in_order = [i["opportunity_id"] for i in items]
    first_nongo = next(i for i, oid in enumerate(opp_ids_in_order) if oid in nongo_ids)
    last_go = max(i for i, oid in enumerate(opp_ids_in_order) if oid in go_ids)
    assert last_go < first_nongo, "go 공고가 no_go보다 앞에 있어야 함"


# ─── posted_at 응답 포함 ─────────────────────────────────────────────────────

def test_posted_at_in_opportunities_response(client, seeded):
    """GET /opportunities 응답 items에 posted_at 필드가 있음."""
    headers, _, _ = seeded
    resp = client.get("/api/v1/opportunities", headers=headers)
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    assert len(items) > 0
    for item in items:
        assert "posted_at" in item, f"posted_at 필드 없음: {item['opportunity_id']}"


def test_posted_at_value_correct(client, seeded):
    """posted_at 값이 실제 삽입된 값과 일치."""
    headers, _, ids = seeded
    resp = client.get("/api/v1/opportunities", headers=headers)
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    # 공고 A의 posted_at은 약 10일 전 — None이 아니어야 함
    item_a = next(i for i in items if i["opportunity_id"] == str(ids["A"]))
    assert item_a["posted_at"] is not None


def test_posted_at_in_recommendations_today(client, seeded):
    """GET /recommendations/today 응답에도 posted_at 포함."""
    headers, _, _ = seeded
    resp = client.get("/api/v1/recommendations/today", headers=headers)
    assert resp.status_code == 200, resp.text
    items = resp.json()
    assert len(items) > 0
    for item in items:
        assert "posted_at" in item, f"posted_at 필드 없음: {item['opportunity_id']}"


# ─── 미허용 sort 값 폴백 ──────────────────────────────────────────────────────

def test_invalid_sort_falls_back_to_score(client, seeded):
    """미허용 sort 값 → 200 + score 내림차순(폴백)."""
    headers, _, _ = seeded
    resp = client.get("/api/v1/opportunities?sort=unknown_field", headers=headers)
    assert resp.status_code == 200, resp.text
    scores = [i["score"] for i in resp.json()["items"]]
    assert scores == sorted(scores, reverse=True)


# ─── total·페이지네이션 일관성 ───────────────────────────────────────────────

def test_total_consistent_across_sort_modes(client, seeded):
    """sort별 total이 동일해야 함(필터 없으므로 4개)."""
    headers, _, _ = seeded
    totals = {}
    for s in ("score", "deadline", "posted", "budget", "feasibility"):
        r = client.get(f"/api/v1/opportunities?sort={s}", headers=headers)
        assert r.status_code == 200
        totals[s] = r.json()["total"]
    assert len(set(totals.values())) == 1, f"sort별 total 불일치: {totals}"


# ─── 중복 공고 dedup ─────────────────────────────────────────────────────────

def _make_opp_named(
    db_session, *, suffix: str, title: str, agency: str, budget_amount: int,
    deadline_days: int | None = None,
) -> uuid.UUID:
    """동일 title/agency/budget·서로 다른 source_uid 공고(중복 재게시 모사)."""
    from app.db.models.opportunity import Opportunity  # noqa: PLC0415

    now = datetime.now(timezone.utc)
    opp_id = uuid.uuid4()
    opp = Opportunity(
        id=opp_id,
        source="narajangter",
        source_uid=f"dup_{suffix}_{opp_id.hex[:8]}",
        title=title,
        agency=agency,
        budget_amount=budget_amount,
        deadline=(now + timedelta(days=deadline_days)) if deadline_days is not None else None,
        status="open",
        is_canonical=True,
        raw_json={},
        content_hash=opp_id.hex,  # 서로 다른 content_hash(=현실: 재게시마다 hash 다름)
    )
    db_session.add(opp)
    db_session.flush()
    return opp_id


def test_duplicate_opportunities_deduped(client, auth, db_session):
    """동일 공고가 서로 다른 source_uid로 2건(둘 다 canonical·open) → 목록은 1건(최고점)."""
    headers, company_id = auth

    title, agency, budget = "중복공고 데이터구축 용역", "한국정보화진흥원", 300_000_000
    id_lo = _make_opp_named(db_session, suffix="lo", title=title, agency=agency,
                            budget_amount=budget, deadline_days=10)
    id_hi = _make_opp_named(db_session, suffix="hi", title=title, agency=agency,
                            budget_amount=budget, deadline_days=10)
    _make_match(db_session, company_id, id_lo, score=70)
    _make_match(db_session, company_id, id_hi, score=88)

    resp = client.get("/api/v1/opportunities", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    same = [i for i in body["items"] if i["title"] == title]
    assert len(same) == 1, f"중복 공고가 dedup 되지 않음: {len(same)}건"
    assert same[0]["score"] == 88, "dedup 시 최고 적합도(score=88) 1건이 유지되어야 함"
    assert same[0]["opportunity_id"] == str(id_hi)


def test_duplicate_opportunities_deadline_present(client, auth, db_session):
    """중복 제거 후 남은 항목에도 d_day가 채워져야 함(추천과 동일, '마감일 미정' 방지)."""
    headers, company_id = auth

    title, agency, budget = "중복공고 마감일 검증", "조달청", 120_000_000
    id_a = _make_opp_named(db_session, suffix="a", title=title, agency=agency,
                           budget_amount=budget, deadline_days=10)
    id_b = _make_opp_named(db_session, suffix="b", title=title, agency=agency,
                           budget_amount=budget, deadline_days=10)
    _make_match(db_session, company_id, id_a, score=60)
    _make_match(db_session, company_id, id_b, score=90)

    resp = client.get("/api/v1/opportunities", headers=headers)
    assert resp.status_code == 200, resp.text
    item = next(i for i in resp.json()["items"] if i["title"] == title)
    assert item["deadline"] is not None
    assert item["d_day"] is not None, "목록 응답에 d_day가 채워져야 함(추천과 동일)"


def test_d_day_in_opportunities_response(client, seeded):
    """GET /opportunities 응답 items에 d_day 필드가 채워짐(추천과 동일 계산)."""
    headers, _, _ = seeded
    resp = client.get("/api/v1/opportunities", headers=headers)
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    assert len(items) > 0
    for item in items:
        # 시드 공고는 모두 deadline 있음 → d_day 비어 있으면 안 됨
        assert item.get("d_day") is not None, f"d_day 누락: {item['opportunity_id']}"


# ─── feasibility 필터 ─────────────────────────────────────────────────────────

def test_feasibility_filter_go_only(client, seeded):
    """?feasibility=go → go verdict 공고만 반환(A·C=용역 → go)."""
    headers, _, ids = seeded
    resp = client.get("/api/v1/opportunities?feasibility=go", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    items = body["items"]
    # 모든 반환 항목이 go이어야 함
    for item in items:
        assert item["feasibility"] is not None, "go 필터 결과에 feasibility=None 항목 포함"
        assert item["feasibility"]["verdict"] == "go", f"go 아닌 verdict 포함: {item['feasibility']['verdict']}"
    # 역량=용역 → A·C(용역)만 go
    returned_ids = {i["opportunity_id"] for i in items}
    assert str(ids["A"]) in returned_ids, "공고 A(용역=go)가 go 필터 결과에 없음"
    assert str(ids["C"]) in returned_ids, "공고 C(용역=go)가 go 필터 결과에 없음"
    assert str(ids["B"]) not in returned_ids, "공고 B(물품=no_go)가 go 필터 결과에 포함됨"
    assert str(ids["D"]) not in returned_ids, "공고 D(공사=no_go)가 go 필터 결과에 포함됨"
    # total도 필터 후 개수와 일치해야 함
    assert body["total"] == len(items), f"total({body['total']}) != items 수({len(items)})"


def test_feasibility_filter_no_go_only(client, seeded):
    """?feasibility=no_go → no_go verdict 공고만 반환(B·D = 물품·공사 → no_go)."""
    headers, _, ids = seeded
    resp = client.get("/api/v1/opportunities?feasibility=no_go", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    items = body["items"]
    for item in items:
        assert item["feasibility"] is not None
        assert item["feasibility"]["verdict"] == "no_go", f"no_go 아닌 verdict: {item['feasibility']['verdict']}"
    returned_ids = {i["opportunity_id"] for i in items}
    assert str(ids["B"]) in returned_ids, "공고 B(물품=no_go)가 no_go 필터 결과에 없음"
    assert str(ids["D"]) in returned_ids, "공고 D(공사=no_go)가 no_go 필터 결과에 없음"
    assert str(ids["A"]) not in returned_ids, "공고 A(용역=go)가 no_go 필터 결과에 포함됨"
    assert str(ids["C"]) not in returned_ids, "공고 C(용역=go)가 no_go 필터 결과에 포함됨"
    assert body["total"] == len(items)


def test_feasibility_filter_go_with_sort_budget(client, seeded):
    """?feasibility=go&sort=budget → go 공고만, 예산 내림차순 정렬."""
    headers, _, ids = seeded
    resp = client.get("/api/v1/opportunities?feasibility=go&sort=budget", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    items = body["items"]
    # 모두 go이어야 함
    for item in items:
        assert item["feasibility"] is not None
        assert item["feasibility"]["verdict"] == "go"
    # 예산 내림차순(C=2억 > A=1억 이므로 C가 앞)
    budgets = [i["budget_amount"] for i in items if i["budget_amount"] is not None]
    assert budgets == sorted(budgets, reverse=True), f"budget desc 아님: {budgets}"
    returned_ids = [i["opportunity_id"] for i in items]
    assert returned_ids.index(str(ids["C"])) < returned_ids.index(str(ids["A"])), \
        "C(2억)가 A(1억)보다 앞이어야 함"


def test_feasibility_filter_no_capability_returns_zero(client, auth, db_session):
    """역량 미설정 회사 → feasibility=go 필터 시 0건(feasibility=None 항목은 제외)."""
    headers, company_id = auth
    # 역량 미설정 상태로 공고 시드
    opp_id = _make_opp(db_session, suffix="nocap", category="용역",
                       budget_amount=100_000_000, deadline_days=10)
    _make_match(db_session, company_id, opp_id, score=80)

    resp = client.get("/api/v1/opportunities?feasibility=go", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 0, f"역량 미설정 시 feasibility=go 결과가 0이어야 함. got total={body['total']}"
    assert body["items"] == [], f"역량 미설정 시 items가 빈 목록이어야 함. got {body['items']}"


def test_feasibility_filter_invalid_value_returns_all(client, seeded):
    """잘못된 feasibility 값 → 무시(전체 반환, total=4)."""
    headers, _, _ = seeded
    resp = client.get("/api/v1/opportunities?feasibility=invalid_verdict", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 4, f"잘못된 feasibility 값이면 전체(4)여야 함. got {body['total']}"
