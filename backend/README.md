# AI 赋能教学督导系统（后端）

更新：AI Worker v2支持“依据不足”、空分数、结构化证据和评价标准版本，见 [v2契约](docs/ai-worker-v2.md)。使用前执行新增数据库迁移，前端须兼容null分数。

该后端覆盖账号与课程权限、隐私授权录音上传、AI 处理任务协议、评价展示、督导评语与分数校准、改进建议和历史对比。AI 模型由其他成员通过独立进程接入；本项目不执行转写、说话人识别或模型评分。

## 技术栈

- Python 3.11+、FastAPI、Pydantic v2
- SQLAlchemy 2.x、Alembic、SQLite（开发默认）
- PyJWT、passlib、bcrypt
- pytest、httpx、Ruff、Black
- 上传格式由 `ffprobe` 校验，需要本机安装 FFmpeg 工具集

## 目录结构

```text
backend/
├── app/api/                 # HTTP 路由、依赖和鉴权
├── app/core/                # 配置、日志、异常和安全工具
├── app/db/                  # SQLAlchemy 引擎、Session 与 Base
├── app/models/              # 用户、课程、录音、任务、评价和督导模型
├── app/schemas/             # 请求、响应与 AI 结果契约
├── app/services/            # 音频校验、隐私遮蔽和建议规则
├── app/ai/interfaces/       # 与模型实现解耦的 AI 抽象接口
├── alembic/versions/        # 数据库迁移
├── docs/                    # Worker 联调协议
└── tests/                   # 自动化测试
```

## 安装、配置和启动

以下命令在 Windows PowerShell 中执行：

```powershell
cd backend
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
```

在 `.env` 中为 `INITIAL_ADMIN_PASSWORD` 设置强密码，并替换 `JWT_SECRET_KEY` 和 `AI_SERVICE_TOKEN`。生产环境会拒绝默认或短密钥，并要求配置首个管理员密码。首次启动且管理员尚不存在时，后端会按该配置创建管理员；不设置管理员密码则不会创建默认账号。上传目录默认为 `./uploads`，不应映射为静态公开目录。

```powershell
alembic upgrade head
uvicorn app.main:app --reload
```

健康检查：`http://127.0.0.1:8000/api/v1/health`；Swagger：`http://127.0.0.1:8000/docs`；OpenAPI：`http://127.0.0.1:8000/openapi.json`。

## 已实现接口

所有 JSON 响应采用 `code/message/data` 包装。

- `POST /api/v1/auth/login`、`GET /api/v1/auth/me`：登录和当前用户。
- `GET/POST /api/v1/users`：管理员查看和创建账号。
- `GET/POST /api/v1/courses`、`GET /api/v1/courses/{id}`：课程创建、教师分配和按角色隔离访问。
- `POST /api/v1/courses/{id}/recordings`：上传 WAV、MP3 或 M4A。要求录制时间和明确授权确认，在 multipart 解析前限制整个请求体，并分块写入私有目录；POSIX 系统目录/文件权限为 `0700`/`0600`，Windows 部署应通过 NTFS ACL 限定服务账号访问。使用 `ffprobe` 检查容器、音频流和真实格式。
- `GET /api/v1/recordings/{id}/status`：轮询 `QUEUED`、`PROCESSING`、`SUCCEEDED`、`FAILED`。
- `GET /api/v1/recordings/{id}/audio`、`DELETE /api/v1/recordings/{id}`：按课程权限读取原始音频，或删除音频及关联任务、转写、评价、建议、评语和校准记录。
- `/api/v1/internal/tasks/*`：AI Worker 领取任务、下载音频、续租、回传结果或失败；需要服务令牌和领取返回的任务令牌。
- `GET /api/v1/recordings/{id}/evaluation`、`GET /api/v1/evaluations/{id}`：单次评价详情。
- `GET /api/v1/courses/{id}/evaluations`：课程历史评价分页查询。
- `GET /api/v1/courses/{id}/comparison`：最近两次已完成课堂的总分及 BOPPPS 六维变化。
- `POST /api/v1/evaluations/{id}/reviews`、`POST /api/v1/evaluations/{id}/calibrations`：督导追加评语和人工校准；教师只读。

角色权限：管理员可管理全部数据并创建账号；督导创建课程并只能访问自己负责的课程；教师只能访问分配给自己的课程。所有录音、评价和历史接口均检查课程归属。

AI Worker 请求/响应样例、结果字段及重试协议见 [docs/ai-worker-integration.md](docs/ai-worker-integration.md)。

## 隐私和结果约定

后端保存授权确认时间与版本。音频仅通过带权限检查的接口读取，删除录音会一并删除其业务数据。评价原始模型结果保存在数据库中，但不会通过标准评价接口返回。标准接口对常见手机号、邮箱和中国身份证号做基础规则遮蔽；规则遮蔽不能保证识别所有个人信息。

`basic` 结果允许暂缺六维分数；`boppps` 结果必须提交导入、目标、前测、参与式学习、后测、总结六项 0–100 分数。未由 AI 提交建议时，后端根据教学问题和低于 60 分的维度生成最多三条固定模板建议。

## 测试与代码质量

```powershell
pytest
ruff check .
black --check .
python -m compileall app
alembic upgrade head
alembic check
```

模拟 Worker 测试仅证明后端契约和流程，不代表真实转写准确率或评价有效性。后两项需在接入其他成员的模型后共同验收。
