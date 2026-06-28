/** @type {import('next').NextConfig} */

// 전역 보안 헤더(A05). 기능에 영향 없는 안전한 항목만 — 클릭재킹/스니핑/리퍼러/권한.
// 참고: 완전한 CSP는 API origin·Toss·폰트 CDN을 환경별로 정밀 튜닝해야 해 별도 후속.
const securityHeaders = [
  { key: "X-Frame-Options", value: "DENY" },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
  // HSTS — http(개발)에선 브라우저가 무시, https(운영)에서만 강제.
  { key: "Strict-Transport-Security", value: "max-age=31536000; includeSubDomains" },
];

const nextConfig = {
  reactStrictMode: true,
  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }];
  },
};

module.exports = nextConfig;
