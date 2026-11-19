@echo off
REM 발표용 Windows PC에서 더블클릭으로 실행 (uv 설치 필요: docs/SETUP.md)
cd /d %~dp0\..
set PYTHONUTF8=1
uv sync --extra ui --extra ocr --extra analyze --extra report
uv run app
pause
