const SOURCE_LABELS: Record<string, string> = {
  narajangter: "나라장터",
  bizinfo: "기업마당",
  kstartup: "K-스타트업",
  ntis: "NTIS",
};

export function sourceLabel(code?: string | null): string {
  if (!code) return "";
  return SOURCE_LABELS[code] ?? code;
}
