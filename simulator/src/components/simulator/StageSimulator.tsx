"use client";
/**
 * 모듈 시뮬레이션 화면 본체 (PC 고정 3단: 입력 | 실행·결과 | 체크리스트).
 * API 는 useApi() 로 주입받은 클라이언트만 쓴다 → Mock/HTTP 교체나 테스트에서 화면 코드는 그대로.
 */
import { useEffect, useMemo, useState } from "react";
import { useApi } from "@/api/ApiProvider";
import { useStageRun } from "@/hooks/useStageRun";
import { evaluateChecklist } from "@/lib/checklist";
import { deepEqual, prettyJson, safeParseJson } from "@/lib/json";
import type { FixtureCase } from "@/mocks/fixtures";
import type { ModuleMeta } from "@/modules/registry";
import { ErrorBoundary } from "../ErrorBoundary";
import { Checklist } from "./Checklist";
import { CUSTOM_CASE, InputPanel } from "./InputPanel";
import { ResultPanel } from "./ResultPanel";
import { RunButton } from "./RunButton";

interface Props {
  meta: ModuleMeta;
  cases: FixtureCase[];
}

export function StageSimulator({ meta, cases }: Props) {
  const { client, config, mockScenario, setMockScenario } = useApi();
  const first = cases[0];
  const [caseId, setCaseId] = useState<string>(first?.caseId ?? CUSTOM_CASE);
  const [text, setText] = useState<string>(first ? prettyJson(first.input) : "{}");
  const [runNo, setRunNo] = useState(0);
  const { state, run, reset } = useStageRun(client, meta.stageId);

  // 응답 흉내(장애) 설정은 화면마다 "정상"에서 시작 → 다른 모듈로 넘어가며 오류 흉내가 남아 헷갈리지 않게
  useEffect(() => setMockScenario("normal"), [meta.stageId, setMockScenario]);

  const selected = cases.find((c) => c.caseId === caseId);
  const parsed = useMemo(() => safeParseJson(text), [text]);
  const edited = selected !== undefined && (!parsed.ok || !deepEqual(parsed.value, selected.input));
  const expected = selected !== undefined && !edited ? selected.expected : undefined;
  // 기대값은 "실행할 때의 입력" 기준 → 실행 후 입력을 고치면 비교를 숨긴다
  const [ranExpected, setRanExpected] = useState<unknown>(undefined);

  const selectCase = (id: string) => {
    setCaseId(id);
    const c = cases.find((x) => x.caseId === id);
    if (c) setText(prettyJson(c.input));
    setRanExpected(undefined);
    reset();
  };

  const onRun = () => {
    if (!parsed.ok) return;
    setRanExpected(expected);
    setRunNo((n) => n + 1);
    void run(parsed.value);
  };

  const response = state.phase === "success" || state.phase === "error" ? state.response : undefined;
  const checklist = response ? evaluateChecklist({ meta, response, expected: ranExpected, apiMode: config.apiMode }) : null;

  return (
    <div className="grid grid-cols-[420px_minmax(0,1fr)_340px] gap-5">
      <InputPanel
        inputType={meta.inputType}
        cases={cases}
        selectedCaseId={caseId}
        onSelectCase={selectCase}
        text={text}
        onTextChange={setText}
        parseError={parsed.ok ? undefined : parsed.error}
        edited={edited}
        onFormat={() => parsed.ok && setText(prettyJson(parsed.value))}
        onRestore={() => selected && setText(prettyJson(selected.input))}
        mockScenario={config.apiMode === "mock" ? mockScenario : undefined}
        onMockScenario={config.apiMode === "mock" ? setMockScenario : undefined}
      />

      <section aria-label="실행과 결과" className="flex min-w-0 flex-col gap-4">
        <div className="flex items-center justify-between rounded-xl border border-slate-200 bg-white p-4">
          <RunButton
            loading={state.phase === "loading"}
            disabled={!parsed.ok}
            disabledReason={parsed.ok ? undefined : "입력 JSON 을 고쳐야 실행할 수 있습니다"}
            onRun={onRun}
            onCancel={reset}
          />
          <p className="font-mono text-xs text-slate-500">
            POST /stages/{meta.stageId}/run
          </p>
        </div>
        <ErrorBoundary name="결과" resetKey={runNo}>
          <ResultPanel state={state} outputType={meta.outputType} summaryFields={meta.summaryFields} expected={ranExpected} />
        </ErrorBoundary>
      </section>

      <ErrorBoundary name="체크리스트" resetKey={runNo}>
        <Checklist key={`${meta.stageId}-${runNo}`} items={checklist} manualChecks={meta.manualChecks} />
      </ErrorBoundary>
    </div>
  );
}
