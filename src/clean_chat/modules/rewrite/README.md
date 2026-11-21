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

## Gemini / LiteLLM 설정 (키·모델 제공 전 개발)

팀 안내에 따라 문장 생성은 **LiteLLM의 Gemini API**를 사용합니다. VESSL/GPU나 로컬 모델 다운로드는 필요 없습니다.
Gemini 모델은 아직 미정이므로 기본 모델명을 임의로 지정하지 않습니다.

```bash
uv sync --extra rewrite
uv run --extra rewrite sim rewrite
```

API 키가 없는 동안은 검토된 일부 표현만 규칙으로 바꿉니다. 이때 `backend="rule"`이고 **AI가 생성한 결과가 아닙니다.**
규칙에 없는 표현은 `rewritten=null`입니다. `null`은 프로그램 오류가 아니며, 순화 문장을 반환하지 않았다는 뜻입니다.
시뮬레이터의 디버깅 콘솔에서 키/모델 미설정, 규칙 변환, 규칙에 없는 표현, 시간 초과 등을 구분할 수 있습니다.

팀장님께 키와 모델명을 받으면 레포 루트 `.env`에 설정합니다. 키는 채팅이나 Git에 올리지 않습니다.

```dotenv
GEMINI_API_KEY=전달받은_키
LLM_MODEL=gemini/전달받은_모델명
LLM_BACKEND=api
```

위 값은 자리 표시자이므로 실제 값으로 교체해야 합니다. `gemini/` 접두어 없는 모델명은 자동으로 붙입니다.
기존 `LLM_API_KEY`도 별칭으로 지원하지만 `GEMINI_API_KEY`가 우선입니다.
각 변수는 환경 변수가 `.env`보다 우선합니다. `LLM_BACKEND`가 없으면 settings의 api/rule/local을 따르고,
초기값 none은 이 모듈의 api 준비 모드로 해석합니다. 미지원 local은 null을 반환합니다.

### 지연·오류·개인정보

- 유효한 키/모델이 설정된 경우, 모듈을 불러올 때 LiteLLM SDK를 한 번 준비합니다. **최초 SDK 로딩은 느릴 수 있습니다.**
  이는 AI 모델 다운로드가 아니며 문장 생성 전 초기화입니다. 시뮬레이터는 실행마다 새 프로세스이므로 전체 소요 시간에는 이 로딩도 포함됩니다.
- 준비 후 run()의 API 대기는 2.7초, 전체 문장 생성 예산은 3초입니다. 재시도는 하지 않습니다.
  키/모델 없음, SDK/통신/인증/파싱 실패, 시간 초과는 규칙으로 대체하거나 null을 반환합니다.
- API에는 선택된 피드백과 필요한 포지션 단어만 보냅니다. 전체 원문, raw, 화자/대상 메타데이터를 보내지 않습니다.
  알려진 닉네임이 피드백에 있으면 요청을 포기합니다. 원문/키/외부 오류 본문을 모듈 로그에 남기지 않습니다.
- SDK의 메시지 디버깅 로그와 원격 비용표 자동 조회를 끕니다. 실제 호출은 Google Gemini로 이루어지며
  데이터 처리 정책은 팀이 선택한 Gemini 계정/요금제의 정책을 확인해야 합니다.
- 욕설, 여러 문장, 새 게임 대상/수치, 부정 반전 등은 보수적으로 거절합니다. 모든 한국어 의미와 우회 욕설을
  완벽히 검증하지는 못하므로 실키 제공 후 다양한 문장의 생성 품질과 지연을 별도로 확인해야 합니다.
- 표시/숨김/클립보드/신고 정책과 입출력 계약은 변경하지 않습니다.

### 검증과 리뷰 범위

```bash
uv run --extra rewrite pytest tests/test_rewrite.py -v
```

키가 없는 테스트는 LiteLLM 호출 가짜 응답과 SDK의 mock_response로 연결 규격/실패 경로를 검증합니다.
**실제 Gemini 생성 품질을 검증한 것이 아닙니다.** 앱/시뮬레이터에 가짜 생성 모드를 추가하지 않습니다.

패키지 설치를 위해 `pyproject.toml`의 rewrite extra와 `uv.lock`이 변경되었습니다.
이는 모듈 범위 밖의 필수 의존성 변경이므로 리드 리뷰가 필요합니다(가이드의 의존성 예외).

공식 문서: https://docs.litellm.ai/docs/providers/gemini · https://docs.litellm.ai/docs/completion/input

### 2026-11-21 실제 API 개발 확인

로컬 개발 설정에서 `gemini/gemini-3.1-flash-lite`를 사용해 합성 피드백을 실제 순화했습니다.
이 모델은 개발용 선택이며 팀의 최종 모델 지정은 별도로 따릅니다. 키와 로컬 .env는 커밋하지 않습니다.

- `미니맵 좀 보라고` → `미니맵을 조금 더 신경 써 주시면 좋겠습니다.` (API, 약 1.78초)
- `혼자 들어가지 말라고` → `단독 진입은 자제해 주세요.` (API, 약 1.02초)
- 실제 응답에서 `감사하겠습니다`와 `자제해 주세요`를 잘못 거절하던 후처리를 수정하고 회귀 테스트를 추가했습니다.
- 최초 연결에서는 약 4.27초가 측정되어 3초 예산을 초과했습니다. 실제 run()에서는 제한을 늘리지 않고
  안전하게 규칙/None으로 처리합니다. 시뮬레이터는 매 실행 새 프로세스이므로 초기 지연이 반복될 수 있습니다.
  위 두 성공 사례가 모든 입력/네트워크에서 3초 이내 성공을 보장하지 않습니다.
