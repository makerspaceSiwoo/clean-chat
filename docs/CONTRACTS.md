# 통신 포맷 (계약)

> 코드 기준: `src/clean_chat/core/schemas.py` · 예시 기준: `fixtures/<stage>/*.jsonl`
> 이 문서와 코드가 다르면 **코드가 맞습니다**.

## 1. 규칙
1. 모듈 사이에는 **pydantic 모델 객체**만 주고받습니다(같은 프로세스 안에서 함수 호출).
2. 파일이나 테스트에서는 **JSONL**(한 줄 = 모델 1개 JSON)로 저장합니다. 사람이 읽고 고칠 수 있습니다.
3. 모든 Stage는 **입력 모델 1개 → 출력 모델 1개**입니다. 입력이 여러 개 필요하면 `~Request` 봉투 모델로 묶습니다.
4. 각 Stage의 `fixtures/<stage>/input.jsonl` n번째 줄 ↔ `expected.jsonl` n번째 줄이 짝입니다.
5. 계약 변경은 "계약 변경 요청" 이슈 → 리드가 `schemas.py` 수정 + `SCHEMA_VERSION` 올림 + fixtures 갱신.

## 2. Stage별 입출력

| Stage | 입력 | 출력 | fixtures |
|---|---|---|---|
| ocr | `Frame` | `OcrResult` | `fixtures/ocr/` |
| parse | `RawLine` | `ParseResult` | `fixtures/parse/` |
| normalize | `ChatMessage` | `NormalizedMessage` | `fixtures/normalize/` |
| classify | `NormalizedMessage` | `Classification` | `fixtures/classify/` |
| rewrite | `RewriteRequest` | `Rewrite` | `fixtures/rewrite/` |
| policy | `PolicyRequest` | `Decision` | `fixtures/policy/` |
| report | `ReportRequest` | `ReportDraft` | `fixtures/report/` |
| complaint | `ComplaintRequest` | `ComplaintDraft` | `fixtures/complaint/` |
| (전체) | `RawLine` 시나리오 | `Incident` | `fixtures/scenario/` |

## 3. 모델 요약

```
Frame        { id, ts, image_path, region{x,y,w,h} }
OcrResult    { frame_id, lines: RawLine[] }
RawLine      { id, ts, text, source: ocr|demo|self_input, ocr_confidence? }
ParseResult  { line_id, message: ChatMessage | null }
ChatMessage  { id, ts, source, channel: team|all|system|ping|unknown, speaker?, champion?, text, is_me, raw }
NormalizedMessage = ChatMessage + { text_norm, hints[] }
Classification { msg_id, level: 0~3, harm_types[], has_feedback, scores{}, model_version }
RewriteRequest { message: NormalizedMessage, classification }
Rewrite      { msg_id, feedback_spans[], rewritten?, backend }
PolicyRequest { message, classification, rewrite?, players: Player[] }
Decision     { msg_id, is_me, action, display_text?, target?, report, complaint_candidate, reason }
Incident     { msg, classification, decision, rewrite? }     ← UI·저장·신고가 쓰는 최종 기록
PhaseEvent   { ts, phase: idle|in_game|post_game, raw? }   ← 단계 감지기 출력 (raw = LCU 원본 값)
GameSession  { id, started_at, ended_at?, players: Player[], incidents: Incident[] }   ← 게임 1판 기록
ReportRequest { session: GameSession, speaker }   → ReportDraft { speaker, text, incident_ids[] }
ComplaintRequest { session: GameSession, speaker, complainant, output_dir } → ComplaintDraft { speaker, summary, incident_ids[], pdf_path? }
Player       { name, champion?, team?, position?, is_me }
```

### 열거값
- `level`: 0 정상 · 1 경미 · 2 악성 · 3 법적 대응 후보 (SPEC 4-2)
- `harm_types`: `profanity` 욕설 · `family_insult` 패드립 · `sexual_harassment` 성희롱 · `blame` 비난 · `instigation` 정치질
- `action` (타 유저): `show` · `show_masked` · `show_rewritten` · `hide`
- `action` (내 채팅): `copy` · `copy_masked` · `copy_rewritten` · `block`
- `phase`: `idle` 대기 · `in_game` 게임 중 · `post_game` 게임 종료 (HANDOFF 5-2). report/complaint 는 `post_game` 에서만 실행

### 게임 세션
- `GameSession.incidents` 에는 **다른 유저 채팅(흐름 A)만** 기록합니다. 내 채팅(흐름 B)은 복사/차단으로 끝납니다.
- 저장 위치: `.clean-chat/sessions/<id>.jsonl` (로컬 전용, git 제외)

## 4. 예시 (fixtures/parse 1줄)
```json
// input.jsonl
{"id":"L3","ts":1762920003.0,"text":"[팀] 원딜러 (징크스): 야 정글 ㅂㅅ아 용 먼저 치라고","source":"ocr","ocr_confidence":0.95}
// expected.jsonl
{"line_id":"L3","message":{"id":"L3","ts":1762920003.0,"source":"ocr","channel":"team","speaker":"원딜러","champion":"징크스","text":"야 정글 ㅂㅅ아 용 먼저 치라고","is_me":false,"raw":"[팀] 원딜러 (징크스): 야 정글 ㅂㅅ아 용 먼저 치라고"}}
```

## 5. 모듈 개별 테스트 방법
```bash
uv run python -m clean_chat.parse --impl mock --check   # 형식 확인 (항상 통과)
uv run python -m clean_chat.parse                       # 내 실제 구현으로 fixtures 실행
uv run python -m clean_chat.parse --check               # 기대값과 몇 개 일치하는지
uv run python -m clean_chat.parse --in my_cases.jsonl --out result.jsonl
uv run clean-chat run --real parse,normalize            # 내 모듈만 실제로, 나머지 mock으로 전체 흐름
uv run pytest -q                                      # 구현된 모듈만 자동 검사 (미구현은 skip)
```
