# ① ocr — OCR — 채팅창 이미지 → 텍스트 줄

명세: `docs/MODULES.md`의 `ocr` 절 · 계약: `docs/CONTRACTS.md` · 예시: `fixtures/ocr/`

**할 일은 `impl.py` 의 `run(Frame) -> OcrResult` 함수 하나입니다.** docstring 의 예시·순서·주의를 따라 본문을 채우세요.

| 파일 | 내용 | 수정 |
|---|---|---|
| `impl.py` | `run()` + 제안용 도우미 함수 (`_`로 시작, 바꿔도 됨) | ✅ |
| 그 밖의 파일 | 이 폴더 안에 자유롭게 추가 (사전, 프롬프트, 내부 모듈) | ✅ |
| `fixtures/ocr/input.jsonl` | 입력 예시 추가 | ✅ |
| `fixtures/ocr/expected.jsonl` | 기대값 (명세) | 리드 승인 |
| `tests/test_ocr.py` | 내 테스트 추가 | ✅ |

- AI 모듈: 출력 형식만 자동 검사합니다. 테스트 이미지는 `fixtures/ocr/images/` (README 참고, 실제 채팅·닉네임이 보이는 스크린샷은 커밋 금지).
- Mac 에서 스크린샷 파일로 개발하고, 실제 게임 화면은 Windows 에서 실측합니다. 화면 캡처와 프레임 사이 중복 제거는 구성(리드)이 합니다.
- 브랜치는 `ocr/<작업 내용>` 으로 만듭니다(예: `ocr/first-try`). PR 에서 위 표의 범위 밖 파일을 바꾸면 CI `module-scope` 가 실패합니다(CONTRIBUTING.md).
- 다른 모듈 폴더는 import 하지 않습니다. 함수 이름 `run` 과 입출력 타입은 바꾸지 않습니다(바꿔야 하면 "계약 변경 요청" 이슈).

```bash
uv run sim ocr                         # 브라우저: 입력 | 디버깅 콘솔(print·logging·오류) | 반환값
uv run pytest tests/test_ocr.py        # 자동 테스트 (구현 전이면 skip)
uv run python scripts/pack_context.py ocr   # 웹 AI 채팅에 첨부할 맥락 묶음
```
모듈 코드를 고친 뒤 시뮬레이터에서 [실행]만 다시 누르면 됩니다(서버를 다시 켤 필요 없음).

## 현재 구현 — RapidOCR + PP-OCRv5 한국어

- Windows와 macOS 모두 RapidOCR의 CPU ONNX Runtime을 사용한다. 환경 변수 설정 없이 이 엔진이 기본으로 실행된다.
- 검출 모델: `ch_PP-OCRv5_det_mobile.onnx`. 인식 모델: `korean_PP-OCRv5_rec_mobile.onnx`.
- 설치: `uv sync --extra ocr`. 실행: `uv run --extra ocr sim ocr`.
- 최초 추론 시 SDK가 필요한 모델을 `.clean-chat/rapidocr/`에 자동 다운로드하고 해시를 검증한다. 첫 실행은 인터넷이 필요하며 이후에는 캐시를 재사용한다. 모델 가중치는 커밋하지 않는다.
- ONNX Runtime은 macOS에서 `>=1.20,<1.24`, 다른 OS에서 `>=1.32,<2`를 사용한다. Intel/Apple Silicon Mac의 휠 의존성 해석을 확인했지만 Mac 실기기 추론은 미검증이다.
- 엔진은 프로세스 안에서 재사용한다. EasyOCR 의존성과 어댑터를 제거했다. 기존 `CLEAN_CHAT_OCR_ENGINE` 환경 변수는 사용하지 않는다.
- 이미지 전체를 한 번 인식하고 같은 행의 영역을 왼쪽부터 합친다. 행 신뢰도는 영역 신뢰도의 최솟값이다. 실패 시 원인을 로그에 남기고 `OcrResult(frame_id=..., lines=[])`를 반환한다.
- 사전과 실제 모델 내부 문자 목록에 `ㅋ`, `ㅗ`, `ㅅ`, `ㅂ`이 포함돼 있다. 포함 여부가 실제 인식률을 보장하지는 않는다.
- [합성 이미지 18장 비교](BENCHMARK.md)에서 CER 13.73%, 평균 1.451초, 자모 욕설 0/9였다. 사용자의 전환 요청에 따라 기본 엔진을 변경했다(ADR-0023). 자모 욕설·속도 개선과 실제 게임 캡처 재평가는 후속 과제다.
- Windows 내장 OCR 브리지는 비교 측정용으로만 유지한다.
