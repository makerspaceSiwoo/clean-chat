# ④ rewrite — 순화 — 피드백만 공손한 문장으로

명세: `docs/MODULES.md`의 `rewrite` 절 · 계약: `docs/CONTRACTS.md` · 예시: `fixtures/rewrite/`

**할 일은 `impl.py` 의 `run(RewriteRequest) -> Rewrite` 함수 하나입니다.** docstring 의 예시·순서·주의를 따라 본문을 채우세요.

| 파일 | 내용 | 수정 |
|---|---|---|
| `impl.py` | `run()` + 제안용 도우미 함수 (`_`로 시작, 바꿔도 됨) | ✅ |
| 그 밖의 파일 | 이 폴더 안에 자유롭게 추가 (사전, 프롬프트, 내부 모듈) | ✅ |
| `fixtures/rewrite/input.jsonl` | 입력 예시 추가 | ✅ |
| `fixtures/rewrite/expected.jsonl` | 기대값 (명세) | 리드 승인 |
| `tests/test_rewrite.py` | 내 테스트 추가 | ✅ |

- **구현 방식: 외부 LLM API** (`backend="api"`). 로컬 LLM 보다 빠르고(0.5~1.5초 예상) 앱 크기·게임 성능에 부담이 없습니다. 키가 없거나 실패·시간 초과면 규칙(`"rule"`)으로 대체하거나 `rewritten=None`. 채팅 본문만 보내고 닉네임은 보내지 않습니다.
- 생성 모듈: 출력 형식만 자동 검사합니다.
- 구성이 L2 이상이고 `feedback_spans` 가 있을 때만 부릅니다. API 키는 `.env`(git 금지).
- 브랜치는 `rewrite/<작업 내용>` 으로 만듭니다(예: `rewrite/first-try`). PR 에서 위 표의 범위 밖 파일을 바꾸면 CI `module-scope` 가 실패합니다(CONTRIBUTING.md).
- 다른 모듈 폴더는 import 하지 않습니다. 함수 이름 `run` 과 입출력 타입은 바꾸지 않습니다(바꿔야 하면 "계약 변경 요청" 이슈).

```bash
uv run sim rewrite                         # 브라우저: 입력 | 디버깅 콘솔(print·logging·오류) | 반환값
uv run pytest tests/test_rewrite.py        # 자동 테스트 (구현 전이면 skip)
uv run python scripts/pack_context.py rewrite   # 웹 AI 채팅에 첨부할 맥락 묶음
```
모듈 코드를 고친 뒤 시뮬레이터에서 [실행]만 다시 누르면 됩니다(서버를 다시 켤 필요 없음).

## 구현과 실행 설정

`run()`은 입력/출력 계약을 유지하며 외부 OpenAI Chat Completions API를 사용합니다.
추가 패키지는 없습니다(표준 라이브러리 HTTP + 기존 pydantic). 기본 모델은 `gpt-4.1-mini`입니다.
공식 계약: https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create
모델: https://developers.openai.com/api/docs/models/gpt-4.1-mini

레포 루트 `.env`에 다음 값을 설정하세요. 이 파일은 커밋하지 않습니다.

```dotenv
LLM_API_KEY=본인의_API_키
LLM_MODEL=gpt-4.1-mini
LLM_BACKEND=api
```

- 환경 변수가 `.env`보다 우선합니다. `LLM_BACKEND`가 없으면 `settings.llm_backend`의
  `api`/`rule`/`local`을 따릅니다. 초기값 `none`은 이 모듈의 API 기본 설정으로 해석합니다.
- `rule`은 네트워크 없이 검토된 표현만 순화합니다. 미지원 `local`/비정상 설정은 `None`입니다.
- API 키 없음·통신/인증/파싱 실패·시간 초과면 규칙으로 대체합니다. 규칙에 없는 표현은 `None`입니다.
  API가 위험한 문장을 반환한 경우에는 `backend="api", rewritten=None`으로 거절합니다.
- API 대기는 최대 2.7초(전체 3초 예산의 여유)입니다. 재시도하지 않습니다.
  DNS나 느린 응답에도 호출자는 제한 시간 후 돌아옵니다. 늦은 결과는 버리고, 실제 요청이 끝날
  때까지 프로세스당 새 API 작업을 추가하지 않습니다. 대기 작업은 daemon이라 프로세스 종료를 막지 않습니다.
- API에는 검증한 피드백과 문맥상 필요한 포지션 단어만 전송합니다. 전체 본문도 보내지 않습니다. `raw`, 화자/대상 필드, ID, 메타데이터는
  보내지 않습니다. 입력에서 알려진 화자/대상 닉네임을 지우고, 그 이름이 피드백에 포함되면 요청을 포기합니다.
  원문·키·HTTP 오류 본문은 모듈 로그에 남기지 않습니다. `store=false`로 요청합니다.
- 출력에서 욕설(분석의 profanity_spans 포함), 여러 문장, 명령조, 알려진 닉네임, 새 수치·게임 용어,
  금지/긍정 반전을 보수적으로 검사합니다. 이 검사와 프롬프트가 모든 한국어 의미·우회 욕설을
  완벽하게 검증하는 것은 아닙니다. 규칙은 검토한 소수 표현만 지원하며 애매하면 `None`입니다.
- 이 모듈은 표시·숨김·클립보드·신고 정책을 결정하지 않습니다.

```bash
uv run sim rewrite
uv run pytest tests/test_rewrite.py -v
```

테스트는 네트워크를 가짜 응답으로 대체해 API 요청 형식·인증/통신 실패·시간 초과·개인정보·안전 검사를
확인합니다. 실제 API 품질/지연 측정은 별도 키를 설정한 시뮬레이터에서 확인해야 합니다.
