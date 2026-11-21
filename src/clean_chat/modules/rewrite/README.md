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

## Gemini / LiteLLM 설정

Gemini가 문장을 생성하고 LiteLLM이 공통 API 연결을 담당합니다. VESSL/GPU나 로컬 모델은 필요 없습니다.

```bash
uv sync --extra rewrite
uv run --extra rewrite sim rewrite
```

레포 루트 `.env`에 팀에서 허용한 키와 모델을 설정합니다. 키는 Git/채팅/로그에 올리지 않습니다.

```dotenv
GEMINI_API_KEY=전달받은_키
LLM_MODEL=gemini/gemini-3.1-flash-lite
LLM_BACKEND=api
```

- `LLM_API_KEY`도 별칭으로 지원하지만 `GEMINI_API_KEY`가 우선입니다. 변수별 환경 설정이 .env보다 우선합니다.
- 모델명을 임의로 채우지는 않습니다. 모델 접두어 gemini/가 없으면 붙입니다. api/rule/local 설정 중 local은 미지원입니다.
- 키/모델이 없으면 검토한 규칙만 사용하고, 모르는 표현은 null입니다. rule은 AI 생성이 아닙니다.

## 입력을 어디서 받나

실제 앱은 앞 단계 `analyze`가 뽑은 `analysis.feedback_spans`를 받습니다. 시뮬레이터에서만 사람이
게임 피드백 부분을 원문 그대로 입력합니다. 예: 원문 `야 정글 바론을 왜 쳐`, 피드백 `바론을 왜 쳐`.
질문은 `바론을 공격하시는 이유가 있나요?`처럼 질문으로 유지하며, 금지 명령으로 단정하지 않습니다.

## 반복 초기화 지연 개선

이전에는 시뮬레이터가 Python과 LiteLLM을 매번 새로 시작해 10초 이상 걸리기도 했습니다.
현재 rewrite는 **127.0.0.1의 인증된 전용 작업자**에서 SDK와 API 연결을 재사용합니다.

- 최초 준비는 비동기입니다. 준비 중인 입력을 오래 붙잡지 않고 콘솔에 준비 상태를 표시합니다.
- 준비 후 시뮬레이터는 새 Python 프로세스를 만들지 않고 작업자의 실제 run()을 호출합니다.
  다른 모듈과 테스트용 CLEAN_CHAT_SIM_TARGET은 원래 실행 경로를 유지합니다.
- API 키는 RPC에 넣지 않습니다. 작업자가 로컬 설정에서 읽습니다. 로컬 연결 토큰/포트와 로그는
  Git 제외 폴더 `.clean-chat/`에만 저장하고, 외부 인터페이스에 바인딩하지 않습니다.
- API 동시 실행은 하나로 제한하고, 15분간 사용하지 않으면 작업자를 종료합니다.
  코드 변경은 fingerprint로 감지해 새 작업자를 준비합니다. 연결 코드 수정 시 시뮬레이터를 재시작하세요.
- run()은 3초 예산 안에서 결과를 반환합니다. RPC/화면 대기와 네트워크 연결 수명을 분리해
  늦은 결과는 버리되 연결을 매번 취소/재초기화하지 않습니다. 재시도는 하지 않습니다.
- Gemini 3 계열은 짧은 문장 작업에 맞춰 minimal 추론과 짧은 출력 예산을 사용합니다.
  네트워크/모델 지연 때문에 모든 요청이 성공하는 것은 아니며, 시간 초과에는 규칙/null로 안전하게 처리합니다.

## 의미·안전 검사와 예비 규칙

API에는 선택된 피드백과 필요한 포지션 단어만 보냅니다. 전체 원문, raw, 화자/대상 메타데이터는
보내지 않고, 알려진 닉네임이 피드백에 있으면 요청을 포기합니다. 키나 외부 오류 본문은 로그에 쓰지 않습니다.
욕설, 새 게임 대상/수치, 금지/긍정 반전 등을 보수적으로 검사합니다. `궁금`을 궁극기 `궁`으로
오인하지 않으며 존댓말 종결형과 공손한 질문형을 허용합니다. 모든 한국어 의미를 완벽히 검증하지는 못합니다.

키 없음/통신 실패/시간 초과 시, 바론·용·전령·포탑·타워·억제기·넥서스에 대한 명확한 단일 지시는
일반 규칙으로 처리할 수 있습니다. 예: `바론 먼저 치라고` → `바론 먼저 공격해 주세요`.
금지와 질문의 뜻을 유지하고, 모호한 복합 지시는 임의로 해석하지 않습니다.
결과의 backend=api는 실제 생성, backend=rule은 예비 규칙입니다. null은 안전하게 반환할 문장이 없다는 뜻입니다.

## 검증 및 변경 범위

```bash
uv run --extra rewrite pytest tests/test_rewrite.py -v
```

단위 테스트는 가짜 응답/SDK mock_response로 네트워크 없이 계약과 실패 경로를 검증합니다.
별도로 로컬 키로 합성 피드백을 실제 Gemini에 보내 응답/지연도 측정했습니다.
키나 실제 유저 채팅을 테스트/fixture에 저장하지 않았고 기대값 명세도 바꾸지 않았습니다.

필수 범위 예외: LiteLLM 설치의 `pyproject.toml`/`uv.lock`, 반복 프로세스 시작 제거를 위한
`sim/server.py`의 rewrite 전용 위임입니다. core 계약과 다른 모듈의 구현은 바꾸지 않았습니다.
리드 리뷰에서 이 의존성/시뮬레이터 연결 변경을 함께 확인해 주세요.

공식 문서: https://docs.litellm.ai/docs/providers/gemini · https://docs.litellm.ai/docs/completion/input
