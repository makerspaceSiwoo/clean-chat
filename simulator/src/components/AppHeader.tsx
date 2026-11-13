import Link from "next/link";
import { ConfigWarnings, EnvBadge } from "./EnvBadge";

export function AppHeader() {
  return (
    <header className="border-b border-slate-200 bg-white">
      <div className="flex h-14 items-center justify-between px-8">
        <Link href="/" className="flex items-baseline gap-2">
          <span className="text-base font-semibold text-slate-900">Clean Chat</span>
          <span className="text-sm text-slate-500">모듈 시뮬레이터</span>
        </Link>
        <EnvBadge />
      </div>
      <ConfigWarnings />
    </header>
  );
}
