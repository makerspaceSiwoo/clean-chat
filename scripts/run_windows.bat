@echo off
REM 발표용 Windows PC에서 더블클릭으로 실행 (uv 설치 필요: docs/SETUP.md)
cd /d %~dp0\..
set PYTHONUTF8=1
REM 분류 모델(analyze)과 순화(rewrite)까지 설치한다. 모델 가중치와 Gemini 키는 앱의 첫 실행 준비 화면에서 받는다.
uv sync --extra ui --extra ocr --extra analyze --extra rewrite --extra report
uv run app
pause
