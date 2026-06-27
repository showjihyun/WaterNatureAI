import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        primary: {
          50: "#ECFDFF",
          100: "#D0F7FB",
          200: "#A6EDF4",
          300: "#6FDCE8",
          400: "#2DC2D6",
          500: "#12A4BA",
          600: "#0E8298",
          700: "#0C6678",
          800: "#0E5462",
          900: "#103F49",
        },
        ink: {
          DEFAULT: "#0B1B33",
          700: "#16294A",
          600: "#26405F",
          400: "#5A6B82",
        },
        surface: {
          DEFAULT: "#F4F7FA",
          card: "#FFFFFF",
          border: "#E5EAF0",
        },
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
        display: [
          "var(--font-display)",
          "Space Grotesk",
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
