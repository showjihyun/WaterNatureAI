// 한국표준산업분류(KSIC) 대분류 — 표준 '업종' 축.
// 백엔드 app/services/ksic.py SECTIONS 와 동기화(코드·순서 일치). 코드 'ETC'=기타.
// 공고 industry 코드 → 표시 라벨, 필터/설정 선택지로 사용.

export interface KsicSection {
  code: string;
  name: string; // 필터/설정용 전체 명
  short: string; // 배지용 단축 명
}

export const KSIC_SECTIONS: KsicSection[] = [
  { code: "J", name: "정보통신(IT·SW)", short: "IT·SW" },
  { code: "F", name: "건설업", short: "건설" },
  { code: "E", name: "환경(수도·하수·폐기물)", short: "환경" },
  { code: "M", name: "전문·과학·기술 서비스", short: "전문·기술" },
  { code: "Q", name: "보건·의료·복지", short: "보건·의료" },
  { code: "P", name: "교육 서비스", short: "교육" },
  { code: "C", name: "제조업", short: "제조" },
  { code: "D", name: "전기·가스·에너지", short: "에너지" },
  { code: "A", name: "농업·임업·어업", short: "농림어업" },
  { code: "H", name: "운수·물류·창고", short: "운수·물류" },
  { code: "G", name: "도매·소매", short: "도소매" },
  { code: "N", name: "사업시설·사업지원 서비스", short: "사업지원" },
  { code: "R", name: "예술·스포츠·문화", short: "문화·예술" },
  { code: "ETC", name: "기타", short: "기타" },
];

const NAME = new Map(KSIC_SECTIONS.map((s) => [s.code, s.name]));
const SHORT = new Map(KSIC_SECTIONS.map((s) => [s.code, s.short]));

/** 코드 → 표시명. short=true 면 배지용 단축명. 없으면 null. */
export function ksicName(code: string | null | undefined, short = false): string | null {
  if (!code) return null;
  return (short ? SHORT : NAME).get(code) ?? null;
}

/** 필터·설정 선택지 — '기타'(ETC) 제외(선택 의미 있는 실제 업종만). */
export const KSIC_CHOICES: KsicSection[] = KSIC_SECTIONS.filter((s) => s.code !== "ETC");
