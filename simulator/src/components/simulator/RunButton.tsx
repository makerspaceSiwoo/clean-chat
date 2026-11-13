"use client";

interface Props {
  loading: boolean;
  disabled?: boolean;
  /** 실행할 수 없는 이유 (버튼 아래 안내) */
  disabledReason?: string;
  onRun: () => void;
  onCancel?: () => void;
}

export function RunButton({ loading, disabled = false, disabledReason, onRun, onCancel }: Props) {
  return (
    <div className="flex items-center gap-3">
      <button
        type="button"
        onClick={onRun}
        disabled={disabled || loading}
        aria-busy={loading}
        className="inline-flex h-10 min-w-[140px] items-center justify-center gap-2 rounded-lg bg-slate-900 px-5 text-sm font-medium text-white transition hover:bg-slate-700 disabled:cursor-not-allowed disabled:bg-slate-300"
      >
        {loading && <span aria-hidden className="h-4 w-4 animate-spin rounded-full border-2 border-white/40 border-t-white" />}
        {loading ? "실행 중…" : "실행 (테스트)"}
      </button>
      {loading && onCancel && (
        <button type="button" onClick={onCancel} className="h-10 rounded-lg border border-slate-300 px-4 text-sm text-slate-700 hover:bg-slate-50">
          취소
        </button>
      )}
      {!loading && disabled && disabledReason && <p className="text-xs text-red-700">{disabledReason}</p>}
    </div>
  );
}
