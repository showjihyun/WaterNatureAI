"""표시단계 dedup 엔진 (순수 함수 — DB I/O 없음).

정본: docs/04-architecture/display-dedup.md §1 (보수적 병합).
'같은 공고가 다른 source_uid로 재등록된 진짜 중복'만 묶는다:
  **정규화 제목 완전 동일 + 기관 동일(또는 미상) + 예산 동일(또는 미상).**

마감만 다른 재등록(재공고)도 같은 공고로 보고 병합하며, 대표는 마감이 늦은(활성) 건으로 선택
(만료된 옛 등록본은 비대표로 숨김). 의도적으로 보수적(오병합 > 누락):
  - 의미만 비슷한 다른 사업(같은 기관·시기의 다른 'AI 시스템 구축')은 제목이 달라 분리.
  - 공구/차수/지역/분기 분할(…(이양1공구) vs …(이양2공구), …1분기 vs …2분기)은 제목이 달라 분리.
  - 예산이 다르면(다른 계약) 분리.
임베딩(의미 유사도)·문자열 퍼지 매칭은 위 케이스를 과병합하므로 쓰지 않는다.
"""
from __future__ import annotations

import re
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime

# 군집 group_id 안정 생성용 고정 네임스페이스(멤버 집합 → 결정적 UUID).
DEDUP_NAMESPACE = uuid.UUID("d3d0b9c2-1e7a-5b3c-8f4a-9c2e1d6f7a8b")

# 대표 선정 소스 우선순위(정보 충실도, 작을수록 우선). display-dedup.md §2.4.
SOURCE_PRIORITY = {"narajangter": 0, "bizinfo": 1, "kstartup": 2, "ntis": 3}

_WS = re.compile(r"\s+")
_NONWORD = re.compile(r"[^0-9a-z가-힣]+")


@dataclass
class DedupOpp:
    """dedup 입력 — opportunities 행에서 필요한 필드만."""

    id: uuid.UUID
    source: str
    title: str
    agency: str | None
    deadline: datetime | None
    budget_amount: int | None
    posted_at: datetime | None
    description_len: int = 0


def title_key(s: str | None) -> str:
    """제목 정규화 키 — 소문자 + 공백 단일화. 괄호·차수·공구·분기 표기는 보존(다른 계약 구분)."""
    return _WS.sub(" ", s.strip().lower()) if s else ""


def normalize_agency(s: str | None) -> str:
    """기관명 정규화 키 — 공백/기호 제거, 소문자(동일 판정용)."""
    return _NONWORD.sub("", (s or "").lower())


def should_merge(a: DedupOpp, b: DedupOpp) -> bool:
    """진짜 중복(같은 공고 재등록)만 병합 — 정규화 제목·기관·예산이 모두 동일(마감 무관)."""
    if not title_key(a.title) or title_key(a.title) != title_key(b.title):
        return False
    na, nb = normalize_agency(a.agency), normalize_agency(b.agency)
    if na and nb and na != nb:
        return False
    if (
        a.budget_amount is not None
        and b.budget_amount is not None
        and a.budget_amount != b.budget_amount
    ):
        return False
    return True


class UnionFind:
    def __init__(self) -> None:
        self.parent: dict[uuid.UUID, uuid.UUID] = {}

    def add(self, x: uuid.UUID) -> None:
        self.parent.setdefault(x, x)

    def find(self, x: uuid.UUID) -> uuid.UUID:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: uuid.UUID, b: uuid.UUID) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[ra] = rb

    def groups(self) -> list[list[uuid.UUID]]:
        g: dict[uuid.UUID, list[uuid.UUID]] = defaultdict(list)
        for x in self.parent:
            g[self.find(x)].append(x)
        return list(g.values())


def cluster_opportunities(opps: list[DedupOpp]) -> list[list[DedupOpp]]:
    """열린 공고 → 중복 군집 리스트(단건은 [자기] 1-원소 군집).

    블로킹: (정규화 기관, 정규화 제목)으로 버킷 — 제목 완전 동일만 같은 버킷.
    버킷 내에서 should_merge(예산 호환)로 확정 후 union-find.
    """
    by_id = {o.id: o for o in opps}
    uf = UnionFind()
    for o in opps:
        uf.add(o.id)

    buckets: dict[tuple[str, str], list[DedupOpp]] = defaultdict(list)
    for o in opps:
        key = title_key(o.title)
        if key:
            buckets[(normalize_agency(o.agency), key)].append(o)

    for members in buckets.values():
        n = len(members)
        if n < 2:
            continue
        for i in range(n):
            for j in range(i + 1, n):
                if should_merge(members[i], members[j]):
                    uf.union(members[i].id, members[j].id)

    return [[by_id[i] for i in ids] for ids in uf.groups()]


def pick_canonical(members: list[DedupOpp]) -> DedupOpp:
    """대표 선정: 소스 우선 → 마감 늦은(활성 재등록) → 예산/설명 충실 → 최신 게시(§2.4)."""

    def key(o: DedupOpp) -> tuple:
        return (
            SOURCE_PRIORITY.get(o.source, 99),
            0 if o.deadline is not None else 1,
            -(o.deadline.timestamp() if o.deadline else 0.0),  # 마감 늦은(활성) 것 우선
            0 if o.budget_amount is not None else 1,
            -(o.description_len or 0),
            -(o.posted_at.timestamp() if o.posted_at else 0.0),
        )

    return min(members, key=key)


def stable_group_id(member_ids: list[uuid.UUID]) -> uuid.UUID:
    """멤버 집합 → 결정적 group_id(멤버 동일하면 재실행해도 동일)."""
    key = ",".join(sorted(str(i) for i in member_ids))
    return uuid.uuid5(DEDUP_NAMESPACE, key)
