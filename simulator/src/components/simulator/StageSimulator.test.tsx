import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ApiProvider } from "@/api/ApiProvider";
import { createMockClient } from "@/api/mockClient";
import { parseConfig } from "@/config/env";
import { CASES, META } from "@/test/fixtures";
import type { RunStageResponse, StageApiClient } from "@/types/api";
import { StageSimulator } from "./StageSimulator";

const config = parseConfig({});

function renderWith(client: StageApiClient) {
  return render(
    <ApiProvider client={client} config={config}>
      <StageSimulator meta={META} cases={CASES} />
    </ApiProvider>,
  );
}

const mock = () => createMockClient({ cases: { incoming_policy: CASES }, latencyMs: 0, timeoutMs: 50 });

describe("StageSimulator (Mock 클라이언트 주입)", () => {
  it("첫 케이스로 실행하면 결과와 체크리스트가 채워진다", async () => {
    renderWith(mock());
    await userEvent.click(screen.getByRole("button", { name: "실행 (테스트)" }));
    const result = await screen.findByTestId("result-success");
    expect(within(result).getByText("용 먼저 치자")).toBeInTheDocument();
    expect(screen.getByTestId("check-status-200")).toHaveAttribute("data-status", "pass");
    expect(screen.getByTestId("check-expected")).toHaveAttribute("data-status", "pass");
    // 실제 공통 계약(Decision 필드 8개) 기준: 코드 + 출력 + 필드 8개 + 기대값 = 11개 모두 통과
    expect(screen.getByTestId("checklist-summary")).toHaveTextContent("자동 11/11 통과");
    expect(screen.getByTestId("check-field-complaint_candidate")).toHaveAttribute("data-status", "pass");
  });

  it("케이스를 바꾸면 입력이 바뀌고 이전 결과가 지워진다", async () => {
    renderWith(mock());
    await userEvent.click(screen.getByRole("button", { name: "실행 (테스트)" }));
    await screen.findByTestId("result-success");
    await userEvent.selectOptions(screen.getByLabelText("Mock 케이스 (fixtures)"), "c2");
    expect(screen.getByTestId("result-idle")).toBeInTheDocument();
    expect((screen.getByLabelText("입력 JSON") as HTMLTextAreaElement).value).toContain('"L4"');
  });

  it("JSON 이 깨지면 실행할 수 없다", async () => {
    renderWith(mock());
    const box = screen.getByLabelText("입력 JSON");
    await userEvent.clear(box);
    await userEvent.type(box, "{{ 깨짐");
    expect(screen.getByRole("button", { name: "실행 (테스트)" })).toBeDisabled();
    expect(screen.getByText(/JSON 형식 오류/)).toBeInTheDocument();
  });

  it("입력을 고치면 fixtures 에 없는 입력 → 404 오류 화면, 기대값 비교는 건너뜀", async () => {
    renderWith(mock());
    const box = screen.getByLabelText("입력 JSON");
    await userEvent.clear(box);
    await userEvent.type(box, '{{"message": {{"id": "X"}}');
    expect(screen.getByText(/수정됨/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "실행 (테스트)" }));
    expect(await screen.findByTestId("result-error")).toHaveTextContent("HTTP 404");
    expect(screen.getByTestId("check-expected")).toHaveAttribute("data-status", "skip");
  });

  it("클라이언트가 예외를 던져도 화면이 깨지지 않고 오류로 보여 준다", async () => {
    const broken: StageApiClient = {
      kind: "http",
      runStage: async () => {
        throw new Error("boom");
      },
    };
    renderWith(broken);
    await userEvent.click(screen.getByRole("button", { name: "실행 (테스트)" }));
    expect(await screen.findByTestId("result-error")).toHaveTextContent("클라이언트 오류: boom");
  });

  it("먼저 보낸 느린 요청의 응답이 나중 결과를 덮지 않는다", async () => {
    const resolvers: ((r: RunStageResponse) => void)[] = [];
    const slow: StageApiClient = {
      kind: "http",
      runStage: () => new Promise((resolve) => resolvers.push(resolve)),
    };
    renderWith(slow);
    const run = () => userEvent.click(screen.getByRole("button", { name: /실행/ }));
    await run();
    await userEvent.click(screen.getByRole("button", { name: "취소" }));
    await run();
    resolvers[1]!({ status: 200, ok: true, output: { action: "hide", display_text: null }, impl: "real", durationMs: 1 });
    resolvers[0]!({ status: 200, ok: true, output: { action: "show", display_text: "옛 응답" }, impl: "real", durationMs: 1 });
    await waitFor(() => expect(screen.getByTestId("result-success")).toBeInTheDocument());
    expect(screen.queryByText("옛 응답")).not.toBeInTheDocument();
  });
});

describe("응답 흉내 (기본 Mock 클라이언트)", () => {
  const fast = parseConfig({ NEXT_PUBLIC_MOCK_LATENCY_MS: "0" });
  // 실제 앱처럼 Provider(레이아웃)는 그대로 두고 화면(StageSimulator)만 다시 연다
  const page = (screenKey: string) => (
    <ApiProvider config={fast}>
      <StageSimulator key={screenKey} meta={META} cases={CASES} />
    </ApiProvider>
  );

  it("서버 오류를 고르면 다음 실행이 500 이 되고, 다른 화면으로 넘어가면 정상으로 돌아온다", async () => {
    const { rerender } = render(page("a"));
    await userEvent.selectOptions(screen.getByLabelText(/응답 흉내/), "server-error");
    await userEvent.click(screen.getByRole("button", { name: "실행 (테스트)" }));
    expect(await screen.findByTestId("result-error")).toHaveTextContent("HTTP 500");
    rerender(page("b"));
    await waitFor(() => expect(screen.getByLabelText(/응답 흉내/)).toHaveValue("normal"));
  });
});
