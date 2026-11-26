# data/eval/modules/ — 모듈별 평가 데이터 (ocr · parse · rewrite · report)

각 모듈을 **같은 문제로** 채점하기 위한 데이터입니다. `fixtures/<모듈>/` 의 예시(명세)와 달리 **통과·실패 기준이 아니라 점수를 보는 용도**입니다.
모두 **AI(Claude)가 쓴 가상 대화에서 만든 것이고 검수 전**입니다. 실제 유저의 채팅·닉네임·스크린샷은 없습니다.

```bash
uv run python scripts/score_eval.py parse      # ocr · parse · rewrite · report 중 하나
uv run python scripts/score_eval.py all
```
구현 전인 모듈은 "구현 안 됨"으로 표시하고 넘어갑니다.

| 파일 | 건수 | 입력 → 확인하는 것 |
|---|---|---|
| `parse_cases.jsonl` | 855줄 (채팅 697 · 시스템 메시지·핑·잡음 158 · 내 입력 81 포함) | `ParseRequest` → 채팅 여부, 채널·화자·챔피언·본문·`is_me`·`raw` 가 정확히 같은가. `text_norm` 은 참고 점수(우회 표기가 있는 33줄은 따로 집계) |
| `rewrite_cases.jsonl` | 99건 | `RewriteRequest`(욕설·비난 + 게임 지시가 섞인 문장, analyze 결과 포함) → 순화문이 나오는가, 욕설 조각이 남지 않았는가, 60자 이내인가 |
| `report_sessions.jsonl` · `report_cases.jsonl` | 세션 58판 · 요청 122건 (신고 103 · 고소장 19) | `ReportRequest` → `incident_ids` 가 그 유저의 신고(고소 후보) 기록과 같은가, 원문을 그대로 인용했는가, 고소장에 "법률 자문이 아님" 고지가 있는가 |
| `ocr_cases.jsonl` · `ocr_synth/*.png` | 40장 · 223줄 | `Frame` → 읽은 줄이 정답 줄과 얼마나 같은가(줄 정확 일치율, 글자 오류율) |

## 만든 방법과 한계
- 출처: analyze 모듈의 게임 단위 대화 데이터(가상 게임 154판, 한 판에 10명)와 문장 데이터. 생성 스크립트는 analyze 작업 브랜치에서 실행했습니다(Analysis·Decision 을 실제 analyze·정책표 코드로 채움).
- **parse**: 채팅 줄은 `[팀|전체] 닉네임 (챔피언): 본문` 형식으로 만들었습니다. 시스템 메시지·핑 문구는 **실제 게임 문구를 확인한 것이 아니라 지어낸 틀**입니다(OPEN-09). `text_norm` 정답은 "우회 표기가 이상적으로 복원된 문장"이라 parse 사전(`data/lexicon/`)의 실제 규칙과 다를 수 있어 참고 점수로만 봅니다. `hints` 는 채점하지 않습니다.
- **rewrite**: 정답 문장은 없습니다(표현이 여러 가지라). 금지 조건만 자동으로 확인하고, 자연스러움은 사람이 봐야 합니다. 입력의 `analysis` 는 analyze 모델(kcelectra-base-ft-0.4)의 출력이라 틀린 것도 섞여 있습니다.
- **report**: 세션의 `analysis`·`decision` 도 analyze 와 정책표의 출력입니다. "누구의 어떤 기록을 골라야 하는가"는 세션에서 결정되므로 정확히 채점할 수 있지만, 문구의 품질은 사람이 봐야 합니다. `expect.game_label` 은 대화를 쓴 사람이 붙인 유저별 정답(신고 권고·고소 후보)으로, 참고용입니다.
- **ocr**: **합성 이미지**입니다. 어두운 배경에 글꼴(Apple SD Gothic Neo 15~20px)로 줄을 그린 것이라 실제 게임 화면(반투명 배경, 게임 글꼴, 줄바꿈, 가려짐)보다 훨씬 쉽습니다. 엔진이 한글·초성·기호를 읽는지 보는 최소 확인용이고, 실제 정확도는 `data/ocr_samples/` 의 실제 캡처로 재야 합니다.
