@echo off
REM 발표용 Windows PC에서 더블클릭으로 실행 (uv 설치 필요: docs/SETUP.md)
cd /d %~dp0\..
uv sync --extra ui --extra capture --extra ml --extra report
uv run lolguard app --source screen
pause
