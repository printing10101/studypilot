@echo off
rem StudyPilot 桌面端启动（自动加载本地模型服务后的前后端）
cd /d %~dp0backend
uv run python desktop.py
