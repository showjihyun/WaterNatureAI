import type { Config } from "tailwindcss";

const config: Config = {
  // 다크모드: html.dark 클래스로 토글(테마 토글 + 무플래시 스크립트).
  darkMode: "class",
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        // 액션 — 신뢰 azure(라이트/다크 공통). 버튼은 흰 글자라 대비 안전.
        primary: {
          50: "#EFF6FB",
          100: "#D7E9F5",
          200: "#B3D4EC",
          300: "#82B7DD",
          400: "#4A93C7",
          500: "#1F76AE",
          600: "#0369A1", // 기본 액션 — 신뢰 azure
          700: "#075985", // hover
          800: "#0B4A6C",
          900: "#0C3A54",
        },
        // 표면·텍스트는 CSS 변수 → .dark에서 값만 스왑(컴포넌트 수정 불필요). 알파 지원.
        surface: {
          DEFAULT: "rgb(var(--surface) / <alpha-value>)", // 페이지 배경
          card: "rgb(var(--surface-card) / <alpha-value>)", // 카드/패널
          border: "rgb(var(--surface-border) / <alpha-value>)",
          muted: "rgb(var(--surface-muted) / <alpha-value>)", // 옅은 채움(스켈레톤·hover)
        },
        ink: {
          DEFAULT: "rgb(var(--ink) / <alpha-value>)", // 본문/제목
          700: "rgb(var(--ink-700) / <alpha-value>)",
          600: "rgb(var(--ink-600) / <alpha-value>)",
          400: "rgb(var(--ink-400) / <alpha-value>)", // 보조/캡션
        },
        // 차트 카테고리 색 — 다크에서 자동으로 밝아짐(legibility).
        chart: {
          1: "rgb(var(--chart-1) / <alpha-value>)",
          2: "rgb(var(--chart-2) / <alpha-value>)",
          3: "rgb(var(--chart-3) / <alpha-value>)",
          4: "rgb(var(--chart-4) / <alpha-value>)",
          5: "rgb(var(--chart-5) / <alpha-value>)",
        },
      },
      // 낮고 부드러운 elevation(슬레이트 틴트) — 일관 그림자 스케일.
      boxShadow: {
        xs: "0 1px 2px 0 rgb(15 23 42 / 0.05)",
        sm: "0 1px 2px 0 rgb(15 23 42 / 0.06), 0 1px 3px 0 rgb(15 23 42 / 0.05)",
        DEFAULT:
          "0 2px 6px -1px rgb(15 23 42 / 0.08), 0 1px 3px -1px rgb(15 23 42 / 0.05)",
        md: "0 6px 16px -4px rgb(15 23 42 / 0.10), 0 2px 6px -2px rgb(15 23 42 / 0.06)",
        lg: "0 12px 28px -8px rgb(15 23 42 / 0.14)",
      },
      fontFamily: {
        sans: [
          "Pretendard",
          "-apple-system",
          "BlinkMacSystemFont",
          "system-ui",
          "Roboto",
          "Helvetica Neue",
          "Segoe UI",
          "Apple SD Gothic Neo",
          "Noto Sans KR",
          "Malgun Gothic",
          "Apple Color Emoji",
          "Segoe UI Emoji",
          "Segoe UI Symbol",
          "sans-serif",
        ],
        // 헤딩·숫자도 Pretendard로 통일(단정·일관). tabular-nums는 Pretendard 지원.
        display: [
          "Pretendard",
          "-apple-system",
          "BlinkMacSystemFont",
          "system-ui",
          "sans-serif",
        ],
      },
    },
  },
  plugins: [],
};

export default config;
