import { render, screen } from "@testing-library/react";
import { ResultPanel, statusLabel } from "./ResultPanel";
import { errorResponse, okResponse } from "@/test/fixtures";

describe("ResultPanel", () => {
  it("실행 전에는 안내를, 실행 중에는 로딩 상태를 보여 준다", () => {
    const { rerender } = render(<ResultPanel outputType="ParseResult" state={{ phase: "idle" }} />);
    expect(screen.getByTestId("result-idle")).toBeInTheDocument();
    rerender(<ResultPanel outputType="ParseResult" state={{ phase: "loading" }} />);
    expect(screen.getByRole("status")).toHaveTextContent("모듈 실행 중");
  });

  it("성공하면 output JSON 만 보여 준다 (기대값 비교 없음)", () => {
    render(<ResultPanel outputType="ParseResult" state={{ phase: "success", response: okResponse({ line_id: "L0", message: null }) }} />);
    expect(screen.getByTestId("result-success")).toHaveTextContent("HTTP 200");
    expect(screen.getByTestId("result-json")).toHaveTextContent('"line_id": "L0"');
    expect(screen.queryByText(/기대값/)).not.toBeInTheDocument();
  });

  it("구현 없음은 501 과 서버 메시지를 오류로 보여 준다", () => {
    const response = errorResponse(501, "모듈 'parse' 구현이 아직 없습니다");
    render(<ResultPanel outputType="ParseResult" state={{ phase: "error", response, message: response.error! }} />);
    expect(screen.getByTestId("result-error")).toHaveTextContent("501 구현 안 됨");
    expect(screen.getByRole("alert")).toHaveTextContent("구현이 아직 없습니다");
    expect(screen.queryByTestId("result-json")).not.toBeInTheDocument();
  });

  it("상태 코드 이름", () => {
    expect([0, 422, 500, 404].map(statusLabel)).toEqual(["서버 연결 안 됨", "422 입력 형식 오류", "500 모듈 오류", "HTTP 404"]);
  });
});
