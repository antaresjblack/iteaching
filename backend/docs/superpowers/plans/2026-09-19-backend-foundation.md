# AI 赋能教学督导系统后端基础 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 创建一个可启动、可迁移、可测试且便于扩展 AI 能力的 FastAPI 后端基础项目。

**Architecture:** 使用应用工厂式组装保持 `main.py` 简洁，依赖方向为 API → Service → Repository → Database。配置、日志、异常、安全、AI 接口和存储接口各自隔离，通过类型化契约连接。

**Tech Stack:** Python 3.11+、FastAPI、Pydantic v2、SQLAlchemy 2.x、Alembic、PyJWT、passlib、pytest、httpx、Ruff、Black

**Spec:** `docs/superpowers/specs/2026-09-19-backend-foundation-design.md`

## Global Constraints

- 只创建后端基础框架，不创建前端或完整业务功能。
- 不引入 PyTorch、TensorFlow、Whisper、Transformers、pyannote、Celery 或 Redis。
- 默认 SQLite，且数据库配置可替换为 MySQL/PostgreSQL。
- Router 不直接操作数据库，AI 层只定义接口。
- 所有公开 API 使用统一响应结构，生产错误响应不得暴露 traceback。

## Review Focus

- 无 `.env` 时应用仍能导入并启动，配置测试覆盖默认值。
- CORS 来源可从环境字符串解析，配置测试覆盖 JSON 和逗号分隔形式。
- JWT 无效或过期时安全工具返回明确失败，安全测试覆盖往返与错误令牌。
- 未处理异常不会泄露异常文本，全局异常测试覆盖 500 响应。
- SQLite 相对路径与 Alembic 使用同一 URL，导入和迁移配置检查覆盖该契约。

---

### Task 1: 建立测试与配置契约

**Files:**
- Create: `tests/test_health.py`
- Create: `tests/test_config.py`
- Create: `tests/test_security.py`
- Create: `tests/test_exceptions.py`
- Create: `pyproject.toml`

**Interfaces:**
- Consumes: FastAPI `TestClient`、Pydantic settings、JWT 与密码散列公开工具。
- Produces: 健康检查、配置、安全和异常行为的可执行验收标准。

- [ ] **Step 1:** 编写健康检查、配置、安全和异常边界测试。
- [ ] **Step 2:** 运行 `pytest`，确认因 `app` 尚不存在而失败。
- [ ] **Step 3:** 创建最小测试配置，使测试发现路径固定为 `tests/`。
- [ ] **Step 4:** 在后续任务实现后运行完整测试套件。

### Task 2: 实现核心应用与 API

**Files:**
- Create: `app/main.py`
- Create: `app/api/v1/router.py`
- Create: `app/api/v1/endpoints/health.py`
- Create: `app/core/config.py`
- Create: `app/core/logging.py`
- Create: `app/core/exceptions.py`
- Create: `app/schemas/common.py`

**Interfaces:**
- Consumes: Task 1 的 HTTP 与配置契约。
- Produces: `app` FastAPI 实例、`settings`、`APIResponse[T]` 与异常处理器注册函数。

- [ ] **Step 1:** 实现设置对象、统一响应泛型和健康端点。
- [ ] **Step 2:** 实现日志与三类全局异常处理器。
- [ ] **Step 3:** 组装生命周期、CORS、路由与异常处理。
- [ ] **Step 4:** 运行相关测试并修复到通过。

### Task 3: 实现数据库、安全和扩展接口

**Files:**
- Create: `app/db/base.py`
- Create: `app/db/session.py`
- Create: `app/models/base.py`
- Create: `app/repositories/base.py`
- Create: `app/core/security.py`
- Create: `app/ai/interfaces/*.py`
- Create: `app/storage/base.py`
- Create: `alembic.ini`
- Create: `alembic/env.py`
- Create: `alembic/script.py.mako`

**Interfaces:**
- Consumes: `settings.database_url`、SQLAlchemy `Base` 和安全测试契约。
- Produces: 数据库会话依赖、通用 Repository、密码/JWT 工具、AI/存储 ABC 和 Alembic 环境。

- [ ] **Step 1:** 实现 SQLAlchemy 2.x Base、Engine、Session 与 Repository 泛型。
- [ ] **Step 2:** 实现密码散列、验证、JWT 创建与解析。
- [ ] **Step 3:** 实现四个 AI ABC 和一个存储 ABC。
- [ ] **Step 4:** 配置 Alembic 并验证应用元数据可导入。

### Task 4: 完成项目元数据、文档与验证

**Files:**
- Create: `.env.example`
- Create: `.gitignore`
- Create: `requirements.txt`
- Create: `requirements-dev.txt`
- Create: `README.md`
- Create: all package `__init__.py` files

**Interfaces:**
- Consumes: 前三项任务产生的真实命令、路径和 API。
- Produces: 可复现安装、启动、迁移、格式化、静态检查和测试说明。

- [ ] **Step 1:** 填写运行与开发依赖及工具配置。
- [ ] **Step 2:** 编写中文 README，确保命令和目录与实现一致。
- [ ] **Step 3:** 运行 `python -m compileall app` 与 `pytest`。
- [ ] **Step 4:** 运行 `ruff check .`、`black --check .` 与应用标题导入命令。
