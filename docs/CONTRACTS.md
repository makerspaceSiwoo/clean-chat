# 통신 포맷 (계약)

> 코드 기준: `src/clean_chat/core/schemas.py`(모델), `core/modules.py`(모듈 → 입출력 연결표) · 예시 기준: `fixtures/<모듈>/*.jsonl`
> 이 문서와 코드가 다르면 **코드가 맞습니다**.

## 1. 규칙
1. 모듈 = **함수 1개**: `src/clean_chat/modules/<모듈>/impl.py` 의 `run(입력 모델) -> 출력 모델` (ADR-0017).
2. 모듈 사이에는 **pydantic 모델 객체**만 주고받습니다(같은 프로세스 안에서 함수 호출). 시뮬레이터는 같은 모델을 JSON 으로 넘깁니다.
3. 파일이나 테스트에서는 **JSONL**(한 줄 = 모델 1개 JSON)로 저장합니다.
4. `fixtures/<모듈>/input.jsonl` n번째 줄 ↔ `expected.jsonl` n번째 줄이 짝입니다.
5. 계약 변경은 "계약 변경 요청" 이슈 → 리드가 `schemas.py` 수정 + `SCHEMA_VERSION` 올림 + fixtures 갱신.
6. **Mock 은 없습니다.** 구현 전 함수는 `NotImplementedError` 를 던지고, 앱·시뮬레이터는 그대로 "구현 안 됨" 을 보여 줍니다.

## 2. 모듈별 입출력

| # | 모듈 | 입력 | 출력 | fixtures |
|---|---|---|---|---|
| ① | ocr | `Frame` | `OcrResult` | `fixtures/ocr/` |
| ② | parse | `ParseRequest` | `ParseResult` | `fixtures/parse/` |
| ③ | analyze | `AnalyzeRequest` | `Analysis` | `fixtures/analyze/` |
| ④ | rewrite | `RewriteRequest` | `Rewrite` | `fixtures/rewrite/` |
| ⑤ | report | `ReportRequest` | `ReportDraft` | `fixtures/report/` |

구성(리드)이 쓰는 모델: `Decision`, `Incident`(정책표 결과), `PhaseEvent`, `GameSession`, `PostGameResult`.

전체 흐름 예시 (`fixtures/scenario/`, Mac 에서 `uv run app` 이 재생하는 데모 입력)
| 파일 | 내용 |
|---|---|
| `lines.jsonl` | 흐름 A: 다른 유저 채팅 `RawLine` |
| `outgoing.jsonl` | 흐름 B: 내 입력 문장 `{id, ts, text}` |
| `phases.jsonl` | 가짜 단계 감지기가 재생하는 `PhaseEvent` (idle → in_game → post_game) |
| `players.jsonl` | 게임 참가자 `Player` (가짜 감지기의 명단) |

## 3. 모델 요약

```
① Frame          { id, ts, image_path, region{x,y,w,h} }
   OcrResult      { frame_id, lines: RawLine[] }                ← 보이는 줄 전부 (프레임 사이 중복 제거는 구성)
   RawLine        { id, ts, text, source: ocr|demo|self_input, ocr_confidence? }
② ParseRequest   { line: RawLine, my_name }                     ← 내 입력은 source=self_input (본문만)
   ParseResult    { line_id, message: ChatMessage | null }       ← 시스템 메시지·핑·잡음은 null
   ChatMessage    { id, ts, source, channel: team|all|unknown, speaker, champion?, text, text_norm, hints[], is_me, raw }
③ AnalyzeRequest { message: ChatMessage, history: ChatMessage[], players: Player[] }
   Analysis       { msg_id, target?, level: 0~3, harm_types[], profanity_spans[], feedback_spans[], scores{}, model_version }
④ RewriteRequest { message: ChatMessage, analysis: Analysis }
   Rewrite        { msg_id, rewritten?, backend }
⑤ ReportRequest  { kind: report|complaint, session: GameSession, speaker, complainant?, output_dir? }
   ReportDraft    { kind, speaker, text, incident_ids[], pdf_path? }

구성 (core/)
   Decision       { msg_id, is_me, action, display_text?, target?, report, complaint_candidate, reason }   ← core/policy.py
   Incident       { msg: ChatMessage, analysis, decision, rewrite? }   ← UI·저장·신고가 쓰는 최종 기록
   PhaseEvent     { ts, phase: idle|in_game|post_game, raw? }
   GameSession    { id, started_at, ended_at?, players: Player[], incidents: Incident[] }
   PostGameResult { session_id, reports: ReportDraft[], complaints: ReportDraft[] }
   Player         { name, champion?, team?, position?, is_me }
```

### 열거값
- `level`: 0 정상 · 1 경미 · 2 악성 · 3 법적 대응 후보 (SPEC 4-2)
- `harm_types`: `profanity` 욕설 · `family_insult` 패드립 · `sexual_harassment` 성희롱 · `blame` 비난 · `instigation` 정치질
- `action` (타 유저): `show` · `show_masked` · `show_rewritten` · `hide`
- `action` (내 채팅): `copy` · `copy_masked` · `copy_rewritten` · `block`
- `phase`: `idle` 대기 · `in_game` 게임 중 · `post_game` 게임 종료. report 는 `post_game` 에서만 실행
- `kind`: `report` 신고 문구 · `complaint` 고소장 초안(+PDF)

### 조각(span) 규칙
- `profanity_spans`, `feedback_spans` 는 `message.text`(원문)에 **그대로 있는** 조각입니다. 정책표가 비속어를 `**` 로 가리고(L1), rewrite 가 피드백 조각을 다듬습니다.

### 게임 세션
- `GameSession.incidents` 에는 **다른 유저 채팅(흐름 A)만** 기록합니다. 내 채팅(흐름 B)은 복사/차단으로 끝납니다.
- 저장 위치: `.clean-chat/sessions/<id>.jsonl` (로컬 전용, git 제외)

## 4. 예시 (fixtures/parse 1줄)
```json
// input.jsonl
{"line":{"id":"L3","ts":1762920003.0,"text":"[팀] 원딜러 (징크스): 야 정글 ㅂㅅ아 용 먼저 치라고","source":"ocr","ocr_confidence":0.95},"my_name":"나"}
// expected.jsonl
{"line_id":"L3","message":{"id":"L3","ts":1762920003.0,"source":"ocr","channel":"team","speaker":"원딜러","champion":"징크스","text":"야 정글 ㅂㅅ아 용 먼저 치라고","text_norm":"야 정글 병신아 용 먼저 치라고","hints":["lexicon:ㅂㅅ"],"is_me":false,"raw":"[팀] 원딜러 (징크스): 야 정글 ㅂㅅ아 용 먼저 치라고"}}
```

## 5. 모듈 개별 테스트 방법
```bash
uv run sim parse                                      # 브라우저: 입력 → 디버깅 콘솔 → 반환값 (예시 입력 = fixtures)
uv run pytest tests/test_parse.py                     # 구현하면 자동 검사 (구현 전은 skip)
```
