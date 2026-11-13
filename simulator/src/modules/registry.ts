/**
 * 모듈(Stage)의 화면·QA 용 메타데이터만 둔다. 새 Stage 가 생기면 여기에 1개 추가 → 홈 카드·시뮬레이션 화면이 생긴다.
 * 입출력 모델 이름과 출력 필드는 공통 계약(shared/contracts.ts)에서 가져온다 — 여기에 베껴 두지 않는다 (ADR-0015).
 * 기준 문서: docs/MODULES.md, docs/SPEC.md 8장(지연 목표)
 */
import type { StageId } from "@/types/contracts";

export type Flow = "A" | "B" | "common" | "post_game";

export const FLOW_LABEL: Record<Flow, string> = {
  A: "흐름 A · 다른 유저 채팅",
  B: "흐름 B · 내 채팅",
  common: "공통 필터 · 두 흐름이 같이 씀",
  post_game: "게임 종료 후",
};

export interface SummaryField {
  label: string;
  /** 출력 JSON 경로 (예: "message.speaker") */
  path: string;
}

export interface ModuleMeta {
  stageId: StageId;
  title: string;
  /** 레포 안 구현 위치 */
  modulePath: string;
  workPackage: string;
  flow: Flow;
  description: string;
  /** 결과 화면 요약 표에 보여 줄 필드 */
  summaryFields: SummaryField[];
  /** 응답 시간 목표(ms). http 모드에서만 검사 */
  latencyBudgetMs: number;
  /** STRICT: 기대값과 정확히 같아야 함(규칙 모듈). 아니면 다르면 경고(AI 모듈) */
  strict: boolean;
  /** 사람이 눈으로 확인할 QA 항목 */
  manualChecks: string[];
  /** 입력 JSON 중 이미지 파일 경로 필드. 있으면 입력 칸에 이미지 첨부가 생긴다 (예: OCR 의 image_path) */
  imageField?: string;
}

export const MODULES: readonly ModuleMeta[] = [
  {
    stageId: "ocr",
    title: "OCR",
    modulePath: "src/clean_chat/capture/impl.py",
    workPackage: "WP2",
    flow: "A",
    description: "채팅창 이미지 → 새로 나타난 채팅 줄",
    summaryFields: [
      { label: "프레임", path: "frame_id" },
      { label: "새 줄 수", path: "lines.length" },
      { label: "첫 줄", path: "lines.0.text" },
    ],
    latencyBudgetMs: 500,
    strict: false,
    manualChecks: ["이전 프레임과 겹치는 줄이 빠졌는가?", "오버레이가 캡처 이미지에 찍히지 않았는가?"],
    imageField: "image_path",
  },
  {
    stageId: "parse",
    title: "채팅 줄 분해",
    modulePath: "src/clean_chat/parse/impl.py",
    workPackage: "WP3",
    flow: "A",
    description: "OCR 줄 → 채널·화자·챔피언·본문",
    summaryFields: [
      { label: "채널", path: "message.channel" },
      { label: "화자", path: "message.speaker" },
      { label: "챔피언", path: "message.champion" },
      { label: "본문", path: "message.text" },
      { label: "내 채팅", path: "message.is_me" },
    ],
    latencyBudgetMs: 100,
    strict: true,
    manualChecks: ["raw 가 원본 줄 그대로인가?", "핑·시스템 문구가 채팅으로 잘못 분류되지 않았는가?"],
  },
  {
    stageId: "compose",
    title: "내 입력 메시지화",
    modulePath: "src/clean_chat/parse/impl.py",
    workPackage: "WP3",
    flow: "B",
    description: "오버레이 입력 → ChatMessage (OCR 없이)",
    summaryFields: [
      { label: "출처", path: "source" },
      { label: "채널", path: "channel" },
      { label: "화자", path: "speaker" },
      { label: "내 채팅", path: "is_me" },
    ],
    latencyBudgetMs: 100,
    strict: true,
    manualChecks: ["is_me 가 true 이고 source 가 self_input 인가?"],
  },
  {
    stageId: "normalize",
    title: "우회어 복원",
    modulePath: "src/clean_chat/normalize/impl.py",
    workPackage: "WP3",
    flow: "common",
    description: "시1발 · tlqkf · ㅅ ㅂ → 원래 형태",
    summaryFields: [
      { label: "원문", path: "text" },
      { label: "정리된 문장", path: "text_norm" },
      { label: "보정 힌트", path: "hints" },
    ],
    latencyBudgetMs: 100,
    strict: false,
    manualChecks: ["text·raw 원문은 바뀌지 않았는가? (증거 보존)", "정상 문장을 과하게 고치지 않았는가?"],
  },
  {
    stageId: "classify",
    title: "악성 분류",
    modulePath: "src/clean_chat/classify/impl.py",
    workPackage: "WP4",
    flow: "common",
    description: "등급 L0~L3 · 유해 유형 · 피드백 포함",
    summaryFields: [
      { label: "등급", path: "level" },
      { label: "유해 유형", path: "harm_types" },
      { label: "피드백 포함", path: "has_feedback" },
      { label: "모델", path: "model_version" },
    ],
    latencyBudgetMs: 200,
    strict: false,
    manualChecks: ["분류만 했는가? (숨김·신고 판단 없음)", "대상 없는 혼잣말이 L1 로 나오는가?"],
  },
  {
    stageId: "rewrite",
    title: "피드백 다듬기",
    modulePath: "src/clean_chat/rewrite/impl.py",
    workPackage: "WP5",
    flow: "common",
    description: "악성 문장 → 피드백만 공손하게 (L2↑ & 피드백일 때)",
    summaryFields: [
      { label: "피드백 조각", path: "feedback_spans" },
      { label: "다듬은 문장", path: "rewritten" },
      { label: "백엔드", path: "backend" },
    ],
    latencyBudgetMs: 3000,
    strict: false,
    manualChecks: ["다듬은 문장에 욕설·비난이 남지 않았는가?", "원문에 없는 내용을 지어내지 않았는가?"],
  },
  {
    stageId: "incoming_policy",
    title: "수신 정책",
    modulePath: "src/clean_chat/policy/impl.py",
    workPackage: "WP1",
    flow: "A",
    description: "타 유저 채팅: 표시 · 가림 · 피드백만 · 숨김 + 신고",
    summaryFields: [
      { label: "처리", path: "action" },
      { label: "표시 문장", path: "display_text" },
      { label: "대상", path: "target" },
      { label: "신고", path: "report" },
      { label: "고소 후보", path: "complaint_candidate" },
      { label: "근거", path: "reason" },
    ],
    latencyBudgetMs: 100,
    strict: true,
    manualChecks: ["SPEC 5-1 표와 같은 처리인가?", "숨김(hide)이면 display_text 가 null 인가?"],
  },
  {
    stageId: "outgoing_policy",
    title: "송신 정책",
    modulePath: "src/clean_chat/policy/impl.py",
    workPackage: "WP1",
    flow: "B",
    description: "내 채팅: 복사 · 가려서 복사 · 피드백만 · 차단",
    summaryFields: [
      { label: "처리", path: "action" },
      { label: "복사할 문장", path: "display_text" },
      { label: "대상", path: "target" },
      { label: "근거", path: "reason" },
    ],
    latencyBudgetMs: 100,
    strict: true,
    manualChecks: ["SPEC 5-2 표와 같은 처리인가?", "신고(report) 표시를 하지 않았는가?"],
  },
  {
    stageId: "report",
    title: "신고 문구",
    modulePath: "src/clean_chat/report/impl.py",
    workPackage: "WP6",
    flow: "post_game",
    description: "게임 세션 + 대상 → 복사용 신고 문구",
    summaryFields: [
      { label: "대상", path: "speaker" },
      { label: "기록", path: "incident_ids" },
    ],
    latencyBudgetMs: 3000,
    strict: false,
    manualChecks: ["원문과 시각이 그대로 인용되었는가?", "자동 신고 없이 문구만 만드는가?"],
  },
  {
    stageId: "complaint",
    title: "고소장 초안",
    modulePath: "src/clean_chat/report/impl.py",
    workPackage: "WP6",
    flow: "post_game",
    description: "게임 세션 + 대상 + 고소인 → 초안 + 한글 PDF",
    summaryFields: [
      { label: "피고소인", path: "speaker" },
      { label: "사건 경위", path: "summary" },
      { label: "PDF", path: "pdf_path" },
    ],
    latencyBudgetMs: 5000,
    strict: false,
    manualChecks: ["'법률 자문이 아님' 고지가 있는가?", "PDF 한글이 깨지지 않는가?"],
  },
];

export const FLOW_ORDER: readonly Flow[] = ["A", "B", "common", "post_game"];

export function findModule(stageId: string): ModuleMeta | undefined {
  return MODULES.find((m) => m.stageId === stageId);
}
