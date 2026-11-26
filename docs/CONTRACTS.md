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
                  ← target = 공격 대상의 **닉네임** (한 명으로 못 좁히면 포지션 단어 "정글", 없으면 null) — ADR-0020
④ RewriteRequest { message: ChatMessage, analysis: Analysis }
   Rewrite        { msg_id, rewritten?, backend }
⑤ ReportRequest  { kind: report|complaint, session: GameSession, speaker, complainant?, output_dir?, evidence_ids?, evidence[], applied_charge_ids[] }
   ReportDraft    { kind, speaker, text, incident_ids[], pdf_path?, evidence[], applied_charge_ids[] }

구성 (core/)
   Decision       { msg_id, is_me, action, display_text?, target?, report, complaint_candidate, reason }   ← core/policy.py
   Incident       { msg: ChatMessage, analysis, decision, rewrite? }   ← UI·저장·신고가 쓰는 최종 기록
   PhaseEvent     { ts, phase: idle|in_game|post_game, raw? }
   GameSession    { id, started_at, ended_at?, players: Player[], incidents: Incident[] }
   PostGameResult { session_id, reports: ReportDraft[], complaints: ReportDraft[] }
   Player         { name, champion?, team?, position?, is_me }   ← position 은 비어 있을 수 있음. 채팅은 `닉네임 (챔피언)` 뿐이라 포지션은 챔피언으로 추정 (ADR-0020)
```

### 열거값
- `level`: 0 정상 · 1 경미 · 2 악성 · 3 법적 대응 후보 (SPEC 4-2)
- `harm_types`: `profanity` 욕설 · `family_insult` 패드립 · `sexual_harassment` 성희롱 · `blame` 비난 · `instigation` 정치질 · `threat` 협박(ADR-0021)
- `action` (타 유저): `show` · `show_masked` · `show_rewritten` · `hide`
- `action` (내 채팅): `copy` · `copy_masked` · `copy_rewritten` · `block`
- `phase`: `idle` 대기 · `in_game` 게임 중 · `post_game` 게임 종료. report 는 `post_game` 에서만 실행
- `kind`: `report` 신고 문구 · `complaint` 고소장 초안(+PDF)

### 신고·고소 초안의 근거 (1.1.0)

- core는 요청의 경기·화자와 `report` 또는 `complaint_candidate` 표시를 기준으로 원문을 추린다. `evidence_ids`를 생략하면 해당 기록 전체, 목록을 주면 그중 일치하는 기록만 `evidence`에 시간순으로 담는다. `ChatMessage.raw`는 OCR 원본 줄이고 `text`는 정규화 전 본문이다. `ts`는 유닉스 시각이다.
- 고소장 후보의 분석 유형 `threat`, `family_insult`, `sexual_harassment`는 각각 초안의 `threat`(협박죄), `insult`(모욕죄), `tme`(통신매체이용음란죄)에 연결한다. 이는 초안에 표시할 분류다. `coerce`, `extort`, `privacy`, `defame`도 전체 카탈로그에 보존한다. 대응 분석 신호가 없는 항목은 자동 적용하지 않는다.
- `ReportRequest.applied_charge_ids`는 core가 계산한다. 같은 화자의 고소장 후보 전체를 기준으로 중복을 제거하며, 증거 첨부 선택과 독립적이다. 신고 요청이나 일치하는 유형이 없는 경우 빈 목록이다. 클라이언트는 이 ID를 그대로 적용해 `CHARGE_CATALOG`에서 조회하고, 미리보기와 PDF에 쓴다(사용자 선택 없음).
- report 모듈은 요청의 원문으로 문서 본문을 작성하고 실제 인용한 `incident_ids`를 반환한다. core는 모듈 호출 경계에서 이 ID를 첨부 대상과 대조해 결과의 `evidence`를 채우고, 요청과 동일한 `applied_charge_ids`를 결과에 싣는다. 예전 결과를 읽을 때 새 필드는 빈 목록으로 시작한다.

### 조각(span) 규칙
- `profanity_spans`, `feedback_spans` 는 `message.text`(원문)에 **그대로 있는** 조각입니다. 정책표가 비속어를 `**` 로 가리고(L1), rewrite 가 피드백 조각을 다듬습니다.

### 게임 세션
- `GameSession.incidents` 에는 **다른 유저 채팅(흐름 A)만** 기록합니다. 내 채팅(흐름 B)은 복사/차단으로 끝납니다.
- 저장 위치: `.clean-chat/sessions/<id>.jsonl` (로컬 전용, git 제외)

## 4. 예시 (fixtures/parse 1줄)
```json
// input.jsonl
{"line":{"id":"L3","ts":1762920003.0,"text":"[팀] 불꽃남자 (징크스): 야 정글 ㅂㅅ아 용 먼저 치라고","source":"ocr","ocr_confidence":0.95},"my_name":"나"}
// expected.jsonl
{"line_id":"L3","message":{"id":"L3","ts":1762920003.0,"source":"ocr","channel":"team","speaker":"불꽃남자","champion":"징크스","text":"야 정글 ㅂㅅ아 용 먼저 치라고","text_norm":"야 정글 병신아 용 먼저 치라고","hints":["lexicon:ㅂㅅ"],"is_me":false,"raw":"[팀] 불꽃남자 (징크스): 야 정글 ㅂㅅ아 용 먼저 치라고"}}
```

## 5. 모듈 개별 테스트 방법
```bash
uv run sim parse                                      # 브라우저: 입력 → 디버깅 콘솔 → 반환값 (예시 입력 = fixtures)
uv run pytest tests/test_parse.py                     # 구현하면 자동 검사 (구현 전은 skip)
```


### 데스크톱의 시스템 메시지

`ParseResult.system_text`는 인식된 핑·시스템 이벤트를 사용자에게 보여 줄 문구입니다. 유저 채팅은 기존의 `message`로 전달합니다. `system_text`의 기본값은 `None`이며 JSON에서는 생략합니다. 예전 모듈에서 `message=None`만 반환하면 인식 가능한 정형 알림만 복원합니다.
