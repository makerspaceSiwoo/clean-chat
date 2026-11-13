"use client";
/** 화면 일부가 렌더링 중 예외를 내도 앱 전체가 하얗게 죽지 않게 감싼다. "다시 그리기" 로 복구. */
import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  children: ReactNode;
  /** 무엇이 실패했는지 안내에 쓸 이름 */
  name: string;
  /** 이 값이 바뀌면 오류 상태를 자동으로 지움 (예: 새 실행 번호) */
  resetKey?: unknown;
}

interface State {
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error(`[${this.props.name}] 렌더링 오류`, error, info.componentStack);
  }

  componentDidUpdate(prev: Props): void {
    if (this.state.error && prev.resetKey !== this.props.resetKey) this.setState({ error: null });
  }

  render() {
    if (this.state.error) {
      return (
        <div role="alert" className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">
          <p className="font-medium">{this.props.name} 영역을 그리다 오류가 났습니다.</p>
          <p className="mt-1 font-mono text-xs">{this.state.error.message}</p>
          <button
            type="button"
            onClick={() => this.setState({ error: null })}
            className="mt-3 rounded border border-red-300 bg-white px-3 py-1 text-xs hover:bg-red-100"
          >
            다시 그리기
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
