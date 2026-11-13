import { render, screen, within } from "@testing-library/react";
import { ResultPanel } from "./ResultPanel";
import { META, okResponse } from "@/test/fixtures";

const base = { outputType: "Decision", summaryFields: META.summaryFields };

describe("ResultPanel", () => {
  it("실행 전에는 안내를, 실행 중에는 로딩 상태를 보여 준다", () => {
    const { rerender } = render(<ResultPanel {...base} state={{ phase: "idle" }} />);
    expect(screen.getByTestId("result-idle")).toBeInTheDocument();
    rerender(<ResultPanel {...base} state={{ phase: "loading", startedAt: 0 }} />);
    expect(screen.getByRole("status")).toHaveTextContent("응답을 기다리는 중");
  });

  it("성공하면 상태 코드, 요약 표, 실제 응답과 기대값 JSON 을 보여 준다", () => {
    const output = { action: "show_rewritten", display_text: "용 먼저 치자" };
    render(<ResultPanel {...base} state={{ phase: "success", response: okResponse(output) }} expected={output} />);
    const panel = screen.getByTestId("result-success");
    expect(panel).toHaveTextContent("HTTP 200");
    const table = within(panel).getByRole("table");
    expect(within(table).getByText("show_rewritten")).toBeInTheDocument();
    expect(within(table).getByText("용 먼저 치자")).toBeInTheDocument();
    expect(screen.getByTestId("result-json")).toHaveTextContent('"action": "show_rewritten"');
    expect(screen.getByTestId("expected-json")).toBeInTheDocument();
  });

  it("null 과 없는 필드를 구분해서 보여 준다", () => {
    render(<ResultPanel {...base} state={{ phase: "success", response: okResponse({ action: "hide", display_text: null }) }} />);
    expect(screen.getByText("null")).toBeInTheDocument();
    expect(screen.queryByTestId("expected-json")).not.toBeInTheDocument();
  });

  it("실패하면 오류 문장과 받은 상태 코드를 보여 준다", () => {
    const response = { status: 404, ok: false, output: null, impl: "mock", error: "fixtures 에 없는 입력", durationMs: 3 };
    render(<ResultPanel {...base} state={{ phase: "error", response, message: response.error }} />);
    expect(screen.getByTestId("result-error")).toHaveTextContent("HTTP 404");
    expect(screen.getByRole("alert")).toHaveTextContent("fixtures 에 없는 입력");
  });

  it("네트워크 오류(코드 0)는 '응답 없음' 으로 표시한다", () => {
    const response = { status: 0, ok: false, output: null, impl: "unknown", error: "시간 초과", durationMs: 10000 };
    render(<ResultPanel {...base} state={{ phase: "error", response, message: "시간 초과" }} />);
    expect(screen.getByText("응답 없음")).toBeInTheDocument();
  });
});
