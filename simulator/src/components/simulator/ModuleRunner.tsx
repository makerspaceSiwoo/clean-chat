"use client";
/**
 * 모듈 실행 화면: 입력 JSON(+ 이미지) → 실행 → 실제 모듈 함수의 output 또는 오류.
 * Mock·기대값 비교·체크리스트는 없다 (ADR-0017). 구현이 없으면 서버가 501 을 돌려주고 그대로 오류로 보여 준다.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { useApi } from "@/api/ApiProvider";
import type { InputExample } from "@/examples/examples";
import { useModuleRun } from "@/hooks/useModuleRun";
import { checkImageFile, fileToBase64, uploadPath, withImagePath } from "@/lib/image";
import { prettyJson, safeParseJson } from "@/lib/json";
import type { ModuleMeta } from "@/modules/registry";
import { getContract } from "@/shared/contracts";
import { ErrorBoundary } from "../ErrorBoundary";
import { type AttachedImage, ImageAttach } from "./ImageAttach";
import { CUSTOM_INPUT, InputPanel } from "./InputPanel";
import { ResultPanel } from "./ResultPanel";
import { RunButton } from "./RunButton";

interface Props {
  meta: ModuleMeta;
  examples: InputExample[];
}

export function ModuleRunner({ meta, examples }: Props) {
  const { client, config } = useApi();
  const contract = getContract(meta.moduleId);
  const first = examples[0];
  const [exampleId, setExampleId] = useState<string>(first?.exampleId ?? CUSTOM_INPUT);
  const [text, setText] = useState<string>(first ? prettyJson(first.input) : "{}");
  const [runNo, setRunNo] = useState(0);
  const { state, run, reset } = useModuleRun(client);

  const selected = examples.find((c) => c.exampleId === exampleId);
  const parsed = useMemo(() => safeParseJson(text), [text]);

  // 이미지 첨부 (meta.imageField 가 있는 모듈만). 미리보기 blob URL 은 바꾸거나 화면을 떠날 때 해제한다
  const [image, setImage] = useState<AttachedImage | null>(null);
  const [imageError, setImageError] = useState<string | undefined>(undefined);
  const imageUrl = useRef<string | null>(null);
  const replaceImage = (next: AttachedImage | null) => {
    if (imageUrl.current) URL.revokeObjectURL(imageUrl.current);
    imageUrl.current = next?.url ?? null;
    setImage(next);
  };
  useEffect(
    () => () => {
      if (imageUrl.current) URL.revokeObjectURL(imageUrl.current);
    },
    [],
  );

  const attachImage = (file: File) => {
    const field = meta.imageField;
    if (field === undefined) return;
    const invalid = checkImageFile(file);
    if (invalid) return setImageError(invalid);
    const next = parsed.ok ? withImagePath(parsed.value, field, uploadPath(file.name)) : undefined;
    if (next === undefined) return setImageError("입력 JSON 을 먼저 고쳐야 이미지를 첨부할 수 있습니다");
    setImageError(undefined);
    replaceImage({ name: file.name, size: file.size, url: URL.createObjectURL(file), file });
    setText(prettyJson(next));
  };

  const clearImage = () => {
    replaceImage(null);
    setImageError(undefined);
  };

  /** 첨부 빼기: 미리보기를 지우고, 경로 필드를 고른 예시의 원래 값으로 되돌린다 */
  const detachImage = () => {
    const field = meta.imageField;
    const next = field && parsed.ok ? withImagePath(parsed.value, field, "") : undefined;
    if (field && next) {
      const original = selected ? (selected.input as Record<string, unknown> | null)?.[field] : undefined;
      if (original === undefined) delete next[field];
      else next[field] = original;
      setText(prettyJson(next));
    }
    clearImage();
  };

  const selectExample = (id: string) => {
    setExampleId(id);
    clearImage();
    const c = examples.find((x) => x.exampleId === id);
    if (c) setText(prettyJson(c.input));
    reset();
  };

  const onRun = async () => {
    if (!parsed.ok) return;
    setRunNo((n) => n + 1);
    const upload = image ? { name: image.name, base64: await fileToBase64(image.file) } : undefined;
    void run({ moduleId: meta.moduleId, input: parsed.value, image: upload });
  };

  return (
    <div className="grid grid-cols-[460px_minmax(0,1fr)] gap-5">
      <InputPanel
        inputType={contract.input}
        examples={examples}
        selectedExampleId={exampleId}
        onSelectExample={selectExample}
        text={text}
        onTextChange={setText}
        parseError={parsed.ok ? undefined : parsed.error}
        onFormat={() => parsed.ok && setText(prettyJson(parsed.value))}
        onRestore={() => {
          if (!selected) return;
          setText(prettyJson(selected.input));
          clearImage();
        }}
        attachment={
          meta.imageField !== undefined ? (
            <ImageAttach field={meta.imageField} image={image} error={imageError} onAttach={attachImage} onClear={detachImage} />
          ) : undefined
        }
      />

      <section aria-label="실행과 결과" className="flex min-w-0 flex-col gap-4">
        <div className="flex items-center justify-between rounded-xl border border-slate-200 bg-white p-4">
          <RunButton
            loading={state.phase === "loading"}
            disabled={!parsed.ok}
            disabledReason={parsed.ok ? undefined : "입력 JSON 을 고쳐야 실행할 수 있습니다"}
            onRun={() => void onRun()}
            onCancel={reset}
          />
          <p className="font-mono text-xs text-slate-500">
            POST {config.apiBaseUrl}/modules/{meta.moduleId}/run
          </p>
        </div>
        <ErrorBoundary name="결과" resetKey={runNo}>
          <ResultPanel state={state} outputType={contract.output} />
        </ErrorBoundary>
      </section>
    </div>
  );
}
