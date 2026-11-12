# classify (WP4)

명세: `docs/MODULES.md`의 `classify` 절 · 입출력 예시: `fixtures/classify/`

| 파일 | 내용 | 수정 |
|---|---|---|
| `stage.py` | `ClassifyStage`: NormalizedMessage → Classification | ❌ (리드) |
| `impl.py` | `Classifier` — 실제 구현 (지금은 비어 있음) | ✅ |
| 그 밖의 파일 | 내부 구현용 파일은 자유롭게 추가 | ✅ |

```bash
uv run python -m lolguard.classify --impl mock --check   # 통신 포맷 확인
uv run python -m lolguard.classify --check               # 내 구현을 fixtures로 실행·비교
uv run lolguard run --real classify                      # 내 모듈만 실제로 전체 흐름
```

학습·평가는 `training/` (Colab). `pyproject.toml`의 `ml` extra(`uv sync --extra ml`).
