# iteaching — AI 赋能教学督导系统

面向教学督导和教师自监督场景：课堂录音上传 → AI 转写与 BOPPPS 评价 → 督导人工评语与分数校准 → 历史对比。

## 仓库结构

| 目录 | 说明 |
| --- | --- |
| [backend/](backend/) | FastAPI 后端（已实现完整业务闭环，AI 模型由独立 Worker 进程接入） |
| [frontend/](frontend/) | Vue 3 前端（真实对接后端接口，无 mock） |

## 快速开始

**后端**（详见 [backend/README.md](backend/README.md)）：

```powershell
cd backend
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements-dev.txt
Copy-Item .env.example .env   # 设置 INITIAL_ADMIN_PASSWORD 等
alembic upgrade head
uvicorn app.main:app --reload
```

**前端**（详见 [frontend/README.md](frontend/README.md)）：

```powershell
cd frontend
npm install
Copy-Item .env.example .env
npm run dev
```

**模拟 AI Worker**（前端联调，真实模型就绪前驱动处理环节）：

```powershell
$env:AI_SERVICE_TOKEN = "与 backend/.env 中一致的服务令牌"
python frontend/mock_worker.py
```

## 文档

- [后端实现审计报告](backend/docs/backend-implementation-audit-2026-10-17.md) — 功能实现 + 接口预留核查
- [AI 处理进程联调协议](backend/docs/ai-worker-integration.md)
