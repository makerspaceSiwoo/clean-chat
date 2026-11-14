import { render, screen } from "@testing-library/react";
import { ModuleCard } from "./ModuleCard";
import { ModuleGrid } from "./ModuleGrid";
import { MODULES } from "@/modules/registry";
import { META } from "@/test/fixtures";

describe("ModuleCard", () => {
  it("모듈 번호·이름·입출력과 실행 페이지 링크를 보여 준다", () => {
    render(<ModuleCard meta={META} exampleCount={10} />);
    const card = screen.getByTestId("module-card-parse");
    expect(card).toHaveAttribute("href", "/modules/parse");
    expect(card).toHaveTextContent("②");
    expect(card).toHaveTextContent("ParseRequest → ParseResult");
    expect(card).toHaveTextContent("예시 입력 10개");
  });
});

describe("ModuleGrid", () => {
  it("모듈 5개 카드를 그린다", () => {
    render(<ModuleGrid modules={MODULES} exampleCounts={{}} />);
    expect(screen.getAllByRole("link")).toHaveLength(5);
  });

  it("모듈이 없으면 빈 상태 안내를 보여 준다", () => {
    render(<ModuleGrid modules={[]} exampleCounts={{}} />);
    expect(screen.getByText("등록된 모듈이 없습니다.")).toBeInTheDocument();
  });
});
