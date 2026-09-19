# AI 赋能教学督导系统后端基础设计

## 目标与边界

在 `backend/` 中建立可直接启动和测试的 Python 3.11+ FastAPI 后端骨架。当前阶段只提供配置、API 版本管理、统一响应、异常处理、日志、安全工具、SQLAlchemy/Alembic 基础设施、Repository 基类、AI 与存储抽象接口以及测试工具链；不实现前端、业务表、完整认证、异步队列或任何 AI 模型调用。

## 架构

业务代码遵循 `API/Router -> Service -> Repository -> Database` 的依赖方向。`app.main` 只组装应用，配置、日志、异常处理、数据库会话和安全能力分别隔离在 `core/` 与 `db/`。AI 与文件存储通过 ABC 接口形成稳定边界，未来实现不得反向侵入 API 层。

## 运行与配置

应用通过 `pydantic-settings` 读取 `backend/.env`，同时提供开发默认值。SQLite 默认数据库为 `sqlite:///./data/app.db`，数据库 URL 可替换为 MySQL 或 PostgreSQL；CORS 来源以 JSON 数组或逗号分隔字符串配置。FastAPI 生命周期负责创建运行目录，不在 `main.py` 中创建业务表。

## API 与错误

当前仅公开 `GET /api/v1/health`，统一返回 `code/message/data`。`AppException`、请求校验错误和未处理异常均由全局处理器转换成一致结构；未处理异常只记录服务端堆栈，不向客户端暴露 traceback。

## 数据与扩展接口

SQLAlchemy 采用 2.x 声明式 Base、Engine、`sessionmaker` 与请求级会话依赖。Alembic 从应用元数据和配置读取数据库 URL。ASR、说话人识别、BOPPPS 分析、建议生成和文件存储仅提供带类型标注的抽象契约，不提供模型或云服务实现。

## 验证

测试覆盖健康检查、统一异常响应、配置解析和安全工具的关键行为。完成后执行 `python -m compileall app`、`pytest`、Ruff 检查、Black 检查，以及 `python -c "from app.main import app; print(app.title)"`。
