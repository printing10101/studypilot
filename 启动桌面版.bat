@echo off
rem StudyPilot 桌面端启动（前端+后端；模型服务请另行启动 llama-server / Ollama）
cd /d %~dp0backend
where uv >nul 2>nul
if errorlevel 1 (
  echo [StudyPilot] 未检测到 uv，请先安装：https://docs.astral.sh/uv/
  echo             安装后在 backend 目录执行 uv sync，再重新运行本脚本。
  pause
  exit /b 1
)
uv run python desktop.py
if errorlevel 1 pause
