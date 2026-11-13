import type { Config } from "tailwindcss";

// PC 전용 도구: 반응형 접두사(sm:, md:, lg: ...)를 쓰지 않는다. 화면 폭은 layout 의 min-width 로 고정.
const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Pretendard", "Apple SD Gothic Neo", "Malgun Gothic", "system-ui", "sans-serif"],
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "Consolas", "monospace"],
      },
    },
  },
  plugins: [],
};

export default config;
