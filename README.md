# StudyPilot · 本地 AI 助教

WorkBuddy 架构（模式 / 技能 / 专家团 / 连接器 / 项目空间）× DeepPilot 式三层记忆的本地学习助手。

## 架构

```
┌─ frontend (React+Vite, :5173) ─────────────────────────┐
│  学习对话(Ask/Plan/Craft) 知识库 测验 记忆图谱            │
└──────────────────────┬─────────────────────────────────┘
                       │ /api
┌──────────────────────▼──────────── backend (FastAPI, :8178) ─┐
│ 专家团路由 qa/examiner/grader/planner                        │
│ 技能 quiz.generate / quiz.grade / note.summarize / plan.study│
│ 三层记忆 L1镜像 → L2摘要(LLM压缩) → L3长期档案(错题/薄弱点)     │
│ RAG: pymupdf解析 → 分块 → BGE向量 → 余弦检索(带引用)           │
│ 连接器: 本地上传 + MCP 客户端骨架(connectors.py)               │
│ 存储: SQLite(data/studypilot.db) + uploads/                  │
└──────────────────────┬───────────────────────────────────────┘
                       │ OpenAI 兼容 /v1
            llama-server / Ollama / LM Studio / 云端API
```

## 启动

### 方式一：桌面应用（推荐）

- 桌面双击 **StudyPilot** 快捷方式（已创建，带应用图标、无控制台黑窗）
- 或运行 `studypilot/启动桌面版.bat`（带控制台，便于看日志）
- 桌面端数据/日志：`backend/desktop.log`；关窗即退出，重复双击不会起第二个服务（自动复用 8178 的已有服务）

单进程桌面应用：pywebview（Edge WebView2）原生窗口 + 内嵌 FastAPI 服务 + 托管前端构建产物。
前端改动后需先 `cd frontend && pnpm build` 再打开桌面端。图标源文件 `backend/app.ico`。

### 方式二：开发模式（前后端热更新）

```bash
# 1) 模型后端（.env 中 LLM_BASE_URL / LLM_API_KEY / LLM_MODEL 可配，
#    兼容 llama-server / Ollama / LM Studio / 云端 API）
cd backend && uv sync
uv run uvicorn app.main:app --host 127.0.0.1 --port 8178
# 2) 前端
cd frontend && pnpm install && pnpm dev   # http://localhost:5173
```

## 使用闭环

1. 新建课程空间（如"清华普通物理"）
2. 知识库页上传讲义 PDF → 自动分块向量化
3. 学习对话：Ask 答疑（带引用，"出题/计划"关键词自动路由专家）→ Craft 技能生成讲义总结
4. 测验页生成题目 → 答题 → 交卷判分 → 错题自动写入 L3 记忆
5. 记忆图谱页查看掌握/薄弱/错题分布；继续提问时助教会结合薄弱点个性化作答

## MCP 扩展

`POST /api/connectors/mcp {"name":"fs","command":["npx","-y","@modelcontextprotocol/server-filesystem","C:/path"]}`
注册后 `connectors.McpClient` 可 list_tools / call_tool。
