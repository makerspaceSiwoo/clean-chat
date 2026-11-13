import { render, screen } from "@testing-library/react";
import { ModuleCard } from "./ModuleCard";
import { ModuleGrid } from "./ModuleGrid";
import { MODULES } from "@/modules/registry";
import { META } from "@/test/fixtures";

describe("ModuleCard", () => {
  it("모듈 정보와 시뮬레이션 페이지 링크를 보여 준다", () => {
    render(<ModuleCard meta={META} caseCount={6} />);
    const card = screen.getByTestId("module-card-incoming_policy");
    expect(card).toHaveAttribute("href", "/modules/incoming_policy");
    expect(card).toHaveTextContent("수신 정책");
    expect(card).toHaveTextContent("PolicyRequest → Decision");
    expect(card).toHaveTextContent("Mock 6건");
  });

  it("Mock 케이스가 없으면 0건을 경고색으로 표시한다", () => {
    render(<ModuleCard meta={META} caseCount={0} />);
    expect(screen.getByText("Mock 0건")).toHaveClass("text-amber-700");
  });
});

describe("ModuleGrid", () => {
  it("등록된 모든 모듈 카드를 흐름별 섹션으로 나눠 그린다", () => {
    render(<ModuleGrid modules={MODULES} caseCounts={{}} />);
    for (const m of MODULES) expect(screen.getByTestId(`module-card-${m.stageId}`)).toBeInTheDocument();
    expect(screen.getAllByRole("region")).toHaveLength(4);
  });

  it("모듈이 없으면 빈 상태 안내를 보여 준다", () => {
    render(<ModuleGrid modules={[]} caseCounts={{}} />);
    expect(screen.getByText("등록된 모듈이 없습니다.")).toBeInTheDocument();
  });
});
