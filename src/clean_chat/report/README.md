# report (WP6) — 신고 문구 + 고소장

명세: `docs/MODULES.md`의 `report / complaint` 절 · 입출력 예시: `fixtures/report/`, `fixtures/complaint/`

| 파일 | 내용 | 수정 |
|---|---|---|
| `stage.py` | `ReportStage`, `ComplaintStage` | ❌ (리드) |
| `impl.py` | `ReportWriter`, `ComplaintWriter` | ✅ |
| `templates/`, `fonts/` | 고소장 양식, 한글 폰트(라이선스 확인) | ✅ 추가 |

```bash
uv run python -m clean_chat.report --impl mock --check
uv run python -m clean_chat.report complaint --impl mock --check
uv run python -m clean_chat.report complaint          # 내 구현 실행 (uv sync --extra report)
```
