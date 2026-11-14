# contracts — 공통 계약 (자동 생성)

데스크톱 앱(Python)과 웹 시뮬레이터(`simulator/`)가 함께 쓰는 모듈 입출력 계약입니다. ADR-0015, ADR-0017

| 파일 | 내용 | 만드는 법 |
|---|---|---|
| `modules.schema.json` | 모듈 5개(ocr·parse·analyze·rewrite·report)의 입력·출력 모델 (JSON Schema) | `uv run python scripts/export_contracts.py` |

- 원본은 `src/clean_chat/core/schemas.py`와 `core/modules.py`입니다. **이 폴더의 파일은 직접 고치지 않습니다.**
- `schemas.py`를 바꾸면 위 명령으로 다시 만들어 함께 커밋합니다. 잊으면 `pytest`(Python)가 실패합니다.
- 웹앱은 빌드 전에 이 파일에서 TS 타입과 모듈 목록을 자동으로 만듭니다.
