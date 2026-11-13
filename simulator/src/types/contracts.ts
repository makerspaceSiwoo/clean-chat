/**
 * 데스크톱 앱 Stage 계약의 TypeScript 사본 (원본: src/clean_chat/core/schemas.py, SCHEMA_VERSION 0.6.0).
 *
 * - 화면이 "어떤 모양의 데이터가 오가는지" 한눈에 보이게 하려는 문서용 타입이다.
 * - 런타임 검증은 하지 않는다(실제 값은 fixtures/백엔드가 보낸 JSON 그대로). 필수 필드 확인은 체크리스트가 한다.
 * - schemas.py 가 바뀌면 이 파일과 modules/registry.ts 의 requiredFields 를 함께 고친다.
 */

export const SCHEMA_VERSION = "0.6.0";

export type Source = "ocr" | "demo" | "self_input";
export type Channel = "team" | "all" | "system" | "ping" | "unknown";
export type HarmType = "profanity" | "family_insult" | "sexual_harassment" | "blame" | "instigation";
export type Level = 0 | 1 | 2 | 3;
export type Action =
  | "show"
  | "show_masked"
  | "show_rewritten"
  | "hide"
  | "copy"
  | "copy_masked"
  | "copy_rewritten"
  | "block";

export interface Player {
  name: string;
  champion?: string | null;
  team?: string | null;
  position?: string | null;
  is_me: boolean;
}

export interface Region {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface Frame {
  id: string;
  ts: number;
  image_path: string;
  region: Region;
}

export interface RawLine {
  id: string;
  ts: number;
  text: string;
  source: Source;
  ocr_confidence?: number | null;
}

export interface OcrResult {
  frame_id: string;
  lines: RawLine[];
}

export interface OutgoingText {
  id: string;
  ts: number;
  text: string;
}

export interface ChatMessage {
  id: string;
  ts: number;
  source: Source;
  channel: Channel;
  speaker: string | null;
  champion?: string | null;
  text: string;
  is_me: boolean;
  raw: string;
}

export interface ParseResult {
  line_id: string;
  message: ChatMessage | null;
}

export interface NormalizedMessage extends ChatMessage {
  text_norm: string;
  hints: string[];
}

export interface Classification {
  msg_id: string;
  level: Level;
  harm_types: HarmType[];
  has_feedback: boolean;
  scores: Record<string, number>;
  model_version: string;
}

export interface RewriteRequest {
  message: NormalizedMessage;
  classification: Classification;
}

export interface Rewrite {
  msg_id: string;
  feedback_spans: string[];
  rewritten: string | null;
  backend: string;
}

export interface PolicyRequest {
  message: NormalizedMessage;
  classification: Classification;
  rewrite?: Rewrite | null;
  players: Player[];
}

export interface Decision {
  msg_id: string;
  is_me: boolean;
  action: Action;
  display_text: string | null;
  target?: string | null;
  report: boolean;
  complaint_candidate: boolean;
  reason: string;
}

export interface Incident {
  msg: NormalizedMessage;
  classification: Classification;
  decision: Decision;
  rewrite?: Rewrite | null;
}

export interface GameSession {
  id: string;
  started_at: number;
  ended_at?: number | null;
  players: Player[];
  incidents: Incident[];
}

export interface ReportRequest {
  session: GameSession;
  speaker: string;
}

export interface ReportDraft {
  speaker: string;
  text: string;
  incident_ids: string[];
}

export interface ComplaintRequest {
  session: GameSession;
  speaker: string;
  complainant: string;
  output_dir: string;
}

export interface ComplaintDraft {
  speaker: string;
  summary: string;
  incident_ids: string[];
  pdf_path?: string | null;
}

/** Stage 이름 → 입력/출력 타입. 새 Stage 가 생기면 여기와 registry.ts 에 추가한다. */
export interface StageContracts {
  ocr: { input: Frame; output: OcrResult };
  parse: { input: RawLine; output: ParseResult };
  compose: { input: OutgoingText; output: ChatMessage };
  normalize: { input: ChatMessage; output: NormalizedMessage };
  classify: { input: NormalizedMessage; output: Classification };
  rewrite: { input: RewriteRequest; output: Rewrite };
  incoming_policy: { input: PolicyRequest; output: Decision };
  outgoing_policy: { input: PolicyRequest; output: Decision };
  report: { input: ReportRequest; output: ReportDraft };
  complaint: { input: ComplaintRequest; output: ComplaintDraft };
}

export type StageId = keyof StageContracts;
export type StageInput<S extends StageId> = StageContracts[S]["input"];
export type StageOutput<S extends StageId> = StageContracts[S]["output"];
