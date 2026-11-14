import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { RunButton } from "./RunButton";

describe("RunButton", () => {
  it("누르면 onRun 을 부른다", async () => {
    const onRun = jest.fn();
    render(<RunButton loading={false} onRun={onRun} />);
    await userEvent.click(screen.getByRole("button", { name: "실행" }));
    expect(onRun).toHaveBeenCalledTimes(1);
  });

  it("실행 중에는 로딩 표시를 하고 다시 누를 수 없으며, 취소 버튼을 보여 준다", async () => {
    const onRun = jest.fn();
    const onCancel = jest.fn();
    render(<RunButton loading onRun={onRun} onCancel={onCancel} />);
    const btn = screen.getByRole("button", { name: "실행 중…" });
    expect(btn).toBeDisabled();
    expect(btn).toHaveAttribute("aria-busy", "true");
    await userEvent.click(screen.getByRole("button", { name: "취소" }));
    expect(onCancel).toHaveBeenCalled();
    expect(onRun).not.toHaveBeenCalled();
  });

  it("실행할 수 없으면 비활성화하고 이유를 보여 준다", () => {
    render(<RunButton loading={false} disabled disabledReason="입력 JSON 오류" onRun={jest.fn()} />);
    expect(screen.getByRole("button", { name: "실행" })).toBeDisabled();
    expect(screen.getByText("입력 JSON 오류")).toBeInTheDocument();
  });
});
