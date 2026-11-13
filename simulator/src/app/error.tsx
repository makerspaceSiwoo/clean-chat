"use client";
/** 페이지 단위 오류 화면 (Next.js 라우트 Error Boundary) */
export default function RouteError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <div role="alert" className="rounded-xl border border-red-200 bg-red-50 p-8">
      <p className="text-lg font-semibold text-red-900">화면을 그리는 중 오류가 났습니다</p>
      <p className="mt-2 font-mono text-xs text-red-800">{error.message}</p>
      <button type="button" onClick={reset} className="mt-4 rounded-lg bg-red-700 px-4 py-2 text-sm text-white hover:bg-red-800">
        다시 시도
      </button>
    </div>
  );
}
