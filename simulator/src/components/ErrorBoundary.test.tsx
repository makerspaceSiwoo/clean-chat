import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { ErrorBoundary } from "./ErrorBoundary";

function Bomb({ explode }: { explode: boolean }) {
  if (explode) throw new Error("렌더링 폭발");
  return <p>정상</p>;
}

function Harness() {
  const [explode, setExplode] = useState(true);
  return (
    <>
      <button type="button" onClick={() => setExplode(false)}>
        고치기
      </button>
      <ErrorBoundary name="결과">
        <Bomb explode={explode} />
      </ErrorBoundary>
    </>
  );
}

describe("ErrorBoundary", () => {
  beforeEach(() => jest.spyOn(console, "error").mockImplementation(() => {}));
  afterEach(() => jest.restoreAllMocks());

  it("자식이 예외를 내면 안내를 보여 주고, 다시 그리기로 복구한다", async () => {
    render(<Harness />);
    expect(screen.getByRole("alert")).toHaveTextContent("결과 영역을 그리다 오류가 났습니다");
    await userEvent.click(screen.getByRole("button", { name: "고치기" }));
    await userEvent.click(screen.getByRole("button", { name: "다시 그리기" }));
    expect(screen.getByText("정상")).toBeInTheDocument();
  });
});
