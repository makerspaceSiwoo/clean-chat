import Link from "next/link";

export default function NotFound() {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-10 text-center">
      <p className="text-lg font-semibold">찾을 수 없는 페이지입니다</p>
      <p className="mt-2 text-sm text-slate-600">등록되지 않은 모듈이거나 주소가 잘못되었습니다.</p>
      <Link href="/" className="mt-4 inline-block text-sm text-slate-900 underline">
        모듈 목록으로
      </Link>
    </div>
  );
}
