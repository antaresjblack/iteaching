# AI 赋能教学督导系统（后端）

## 项目介绍

AI 赋能教学督导系统（AI Teaching Supervision System）面向教学督导和教师自监督场景。系统后续将围绕课堂录音处理、师生发言识别、BOPPPS 教学评价、人工督导评价和教学改进跟踪展开。

当前项目只是后端基础框架，尚未实现完整业务流程，也不会调用任何 AI 模型或第三方大模型 API。仓库中的 AI 模块目前只有抽象接口，用于约束后续实现。

## 技术栈

- Python 3.11+
- FastAPI、Uvicorn
- Pydantic v2、pydantic-settings
- SQLAlchemy 2.x、Alembic
- PyJWT、passlib、bcrypt
- pytest、pytest-asyncio、httpx
- Ruff、Black
- SQLite（开发默认，可切换 MySQL 或 PostgreSQL）

本阶段没有引入 PyTorch、TensorFlow、Whisper、Transformers、pyannote、Celery 或 Redis。

## 目录结构

```text
backend/
├── app/
│   ├── api/                 # HTTP 路由、版本管理和依赖注入
│   │   └── v1/endpoints/    # v1 端点实现
│   ├── core/                # 配置、日志、异常和安全工具
│   ├── db/                  # SQLAlchemy Base、Engine 和 Session
│   ├── models/              # SQLAlchemy 业务模型（当前仅基础混入类）
│   ├── schemas/             # Pydantic 请求/响应模型与统一响应结构
│   ├── repositories/        # 数据访问层，禁止 Router 直接操作数据库
│   ├── services/            # 业务逻辑层
│   ├── ai/interfaces/       # ASR、说话人、BOPPPS、建议生成抽象接口
│   ├── storage/             # 文件存储抽象接口
│   ├── tasks/               # 耗时任务编排预留
│   ├── utils/               # 通用无状态工具预留
│   └── main.py              # FastAPI 应用组装入口
├── alembic/                 # 数据库迁移环境与版本目录
├── tests/                   # pytest 测试
├── .env.example             # 环境变量示例
├── requirements.txt         # 运行依赖
├── requirements-dev.txt     # 开发和测试依赖
└── pyproject.toml           # Python、pytest、Black、Ruff 配置
```

项目依赖方向统一为：

```text
API / Router -> Service -> Repository -> Database
```

- `api`：接收请求、参数验证、调用 Service、返回统一响应。
- `core`：承载跨模块配置、日志、异常处理和安全能力。
- `db`：创建数据库引擎、会话工厂和声明式 Base。
- `models`：存放未来的 User、Course、AudioRecord、Evaluation 等数据库模型。
- `schemas`：定义 API 输入输出，不承担数据库访问。
- `repositories`：封装数据库读写，供 Service 使用。
- `services`：编排业务规则和 Repository，不依赖 HTTP 细节。
- `ai`：隔离 AI 能力契约；当前没有模型实现或模型调用。
- `storage`：隔离本地磁盘、MinIO、OSS、S3 等未来存储实现。
- `tasks`：预留录音识别、说话人识别和教学分析等耗时任务的编排位置。

## 安装

以下命令在 Windows PowerShell 中执行：

```powershell
cd backend
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
```

需要运行测试和代码质量工具时，安装开发依赖：

```powershell
python -m pip install -r requirements-dev.txt
```

## 配置

复制示例配置后按环境修改：

```powershell
Copy-Item .env.example .env
```

没有 `.env` 时也可以使用开发默认值启动。主要变量包括应用信息、API 前缀、监听地址、数据库 URL、JWT、安全时长、上传目录、上传大小、日志级别和 CORS 来源。

`CORS_ORIGINS` 可使用 JSON 数组或逗号分隔字符串，例如：

```dotenv
CORS_ORIGINS=["http://localhost:3000","http://localhost:5173"]
# 或：CORS_ORIGINS=http://localhost:3000,http://localhost:5173
```

开发默认数据库是 `sqlite:///./data/app.db`。切换 MySQL 或 PostgreSQL 时，需要安装对应 SQLAlchemy 驱动，并在 `.env` 中替换 `DATABASE_URL`。生产环境必须设置随机且至少 32 字节的 `JWT_SECRET_KEY`。

## 启动

在 `backend/` 目录执行：

```powershell
uvicorn app.main:app --reload
```

也可使用配置中的监听地址和端口：

```powershell
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

启动后可访问：

- 健康检查：`http://127.0.0.1:8000/api/v1/health`
- Swagger：`http://127.0.0.1:8000/docs`
- ReDoc：`http://127.0.0.1:8000/redoc`

## 数据库迁移

创建新模型后，先在 `app/models/__init__.py` 中导入模型，再执行：

```powershell
alembic revision --autogenerate -m "describe change"
alembic upgrade head
```

当前阶段没有创建业务表，因此迁移版本目录为空。

## 测试与代码质量

```powershell
pytest
ruff check .
black --check .
python -m compileall app
```

## 当前 API

### `GET /api/v1/health`

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "status": "ok"
  }
}
```

## 异步任务预留

当前 `app/tasks/` 仅为空模块。后续可先用 FastAPI `BackgroundTasks` 处理轻量后台操作；录音识别、说话人识别和 BOPPPS 分析等长耗时、需要重试或横向扩展的任务，再按实际需求引入 Celery + Redis。本阶段不安装这两项依赖。

## 后续计划

- 课堂录音上传和存储实现
- ASR 语音识别
- 说话人识别与教师/学生发言区分
- BOPPPS 六维教学评分、证据和问题分析
- 督导人工评价
- 教师自监督流程
- 个性化教学改进建议
- 历史课堂评价对比
- 教学改进效果跟踪
