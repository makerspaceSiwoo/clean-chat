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

## 현재 구현 — 속도 우선

- 한국어 Windows 내장 OCR로 채팅 이미지 전체를 **한 번만** 인식합니다. PowerShell 엔진은 같은 프로세스 안에서 재사용합니다.
- 원본 RGB 해상도를 유지합니다. 확대, 행 검출/분할, 반복 자모 픽셀 분석, 대비 변경 재인식은 실행하지 않습니다. 긴 변이 2600px를 넘는 큰 이미지만 축소합니다.
- `image_path`는 이미 채팅창 영역이므로 화면 좌표 `region`으로 다시 자르지 않습니다.
- 기존 줄바꿈 병합과 OcrResult JSON 계약, 콘솔 텍스트 표시를 유지합니다. 신뢰도는 Windows 엔진에서 제공하지 않으므로 `None`입니다.
- `ㅋㅋㅋ`, `ㅗㅗㅗ`, 작은 한글/컬러 글자의 정확도는 보조 인식 버전보다 낮아질 수 있습니다. 사전이나 문맥으로 원문을 추측해 대체하지 않습니다.
- 기존 `repeats.py`와 `alphabet.py`의 후보 재검사 코드는 기본 OCR 경로에서 호출하지 않습니다. 출력의 한국어·영어·숫자·기호 제한은 유지하며 판독 불가 문자는 `�`로 표시합니다.
- 모델 호출 1회가 전체 실행시간 1초를 보장하는 것은 아닙니다. 시뮬레이터는 매번 새 프로세스를 만들므로 엔진 초기화가 매번 포함됩니다.
- Windows PowerShell과 한국어 OCR 언어 팩이 필요합니다. PaddleOCR는 사용하지 않습니다.

```powershell
uv run sim ocr
$env:PYTHONUTF8 = "1"
uv run pytest -q
```

Windows OCR API: https://learn.microsoft.com/en-us/uwp/api/windows.media.ocr.ocrengine
