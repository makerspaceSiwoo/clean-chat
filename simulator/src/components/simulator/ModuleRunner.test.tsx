import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ApiProvider } from "@/api/ApiProvider";
import { parseConfig } from "@/config/env";
import { EXAMPLES, META, OCR_EXAMPLES, OCR_META, errorResponse, okResponse } from "@/test/fixtures";
import type { ModuleApiClient, RunModuleRequest, RunModuleResponse } from "@/types/api";
import { ModuleRunner } from "./ModuleRunner";

function fakeClient(respond: (req: RunModuleRequest) => RunModuleResponse) {
  const calls: RunModuleRequest[] = [];
  const client: ModuleApiClient = {
    runModule: jest.fn(async (req: RunModuleRequest) => {
      calls.push(req);
      return respond(req);
    }),
  };
  return { client, calls };
}

function renderRunner(client: ModuleApiClient, meta = META, examples = EXAMPLES) {
  return render(
    <ApiProvider client={client} config={parseConfig({})}>
      <ModuleRunner meta={meta} examples={examples} />
    </ApiProvider>,
  );
}

describe("ModuleRunner", () => {
  it("고른 예시 입력으로 실제 모듈 서버를 부르고 output 을 보여 준다", async () => {
    const { client, calls } = fakeClient(() => okResponse({ line_id: "L3", message: null }));
    renderRunner(client);
    await userEvent.click(screen.getByRole("button", { name: "실행" }));
    expect(await screen.findByTestId("result-success")).toBeInTheDocument();
    expect(calls[0]).toEqual({ moduleId: "parse", input: EXAMPLES[0]!.input, image: undefined });
    expect(screen.getByTestId("result-json")).toHaveTextContent('"line_id": "L3"');
  });

  it("구현이 없으면(501) 결과 대신 오류를 보여 준다", async () => {
    const { client } = fakeClient(() => errorResponse(501, "모듈 'parse' 구현이 아직 없습니다"));
    renderRunner(client);
    await userEvent.click(screen.getByRole("button", { name: "실행" }));
    expect(await screen.findByTestId("result-error")).toHaveTextContent("501 구현 안 됨");
    expect(screen.queryByTestId("result-json")).not.toBeInTheDocument();
  });

  it("예시를 바꾸면 입력 JSON 이 바뀌고 결과가 초기화된다", async () => {
    const { client } = fakeClient(() => okResponse({}));
    renderRunner(client);
    await userEvent.click(screen.getByRole("button", { name: "실행" }));
    await screen.findByTestId("result-success");
    await userEvent.selectOptions(screen.getByLabelText("예시 입력 (fixtures)"), "e2");
    expect((screen.getByLabelText("입력 JSON") as HTMLTextAreaElement).value).toContain('"L4"');
    expect(screen.getByTestId("result-idle")).toBeInTheDocument();
  });

  it("JSON 이 깨지면 실행할 수 없다", async () => {
    const { client } = fakeClient(() => okResponse({}));
    renderRunner(client);
    const box = screen.getByLabelText("입력 JSON");
    await userEvent.clear(box);
    await userEvent.type(box, "{{ 깨짐");
    expect(screen.getByRole("button", { name: "실행" })).toBeDisabled();
  });

  it("이미지 첨부 칸은 imageField 가 있는 모듈에만 있다", () => {
    const { client } = fakeClient(() => okResponse({}));
    renderRunner(client);
    expect(screen.queryByLabelText("이미지 첨부")).not.toBeInTheDocument();
  });

  describe("이미지 첨부 (OCR)", () => {
    beforeEach(() => {
      URL.createObjectURL = jest.fn(() => "blob:preview");
      URL.revokeObjectURL = jest.fn();
    });

    it("첨부한 이미지를 base64 로 서버에 보낸다", async () => {
      const { client, calls } = fakeClient(() => errorResponse(501, "모듈 'ocr' 구현이 아직 없습니다"));
      renderRunner(client, OCR_META, OCR_EXAMPLES);
      const file = new File(["ABC"], "chat.png", { type: "image/png" });
      await userEvent.upload(screen.getByLabelText("이미지 첨부"), file);
      expect(await screen.findByAltText("첨부한 이미지: chat.png")).toBeInTheDocument();
      expect((screen.getByLabelText("입력 JSON") as HTMLTextAreaElement).value).toContain('"image_path": "uploads/chat.png"');
      await userEvent.click(screen.getByRole("button", { name: "실행" }));
      await waitFor(() => expect(calls).toHaveLength(1));
      expect(calls[0]!.image).toEqual({ name: "chat.png", base64: "QUJD" });
      expect(await screen.findByTestId("result-error")).toHaveTextContent("501");
    });

    it("이미지가 아닌 파일은 거절한다", async () => {
      const { client } = fakeClient(() => okResponse({}));
      renderRunner(client, OCR_META, OCR_EXAMPLES);
      await userEvent.upload(screen.getByLabelText("이미지 첨부"), new File(["x"], "a.txt", { type: "text/plain" }), { applyAccept: false });
      expect(screen.getByRole("alert")).toHaveTextContent("이미지 파일만");
    });

    it("첨부를 빼면 경로가 예시 원래 값으로 돌아간다", async () => {
      const { client } = fakeClient(() => okResponse({}));
      renderRunner(client, OCR_META, OCR_EXAMPLES);
      await userEvent.upload(screen.getByLabelText("이미지 첨부"), new File(["ABC"], "chat.png", { type: "image/png" }));
      await userEvent.click(await screen.findByRole("button", { name: "첨부 빼기" }));
      expect((screen.getByLabelText("입력 JSON") as HTMLTextAreaElement).value).toContain("fixtures/ocr/images/sample_01.png");
      expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:preview");
    });
  });
});
