# 后端实现审计报告

- 审计日期：2026-10-17
- 审计对象：`back_ended` 分支 @ `2f49f14`（feat: implement teaching supervision workflows）
- 审计方式：通读全部后端源码（55 个 Python 文件 + 迁移 + 文档），并在本地 venv 实测运行测试套件与质量检查
- 读者：前端开发（用于对齐前后端契约）、后端开发（用于确认问题清单）

## 1. 实测验证结果

环境：Windows 11，Python 3.12，`requirements-dev.txt` 全新安装（清华镜像）。

| 检查项 | 结果 |
| --- | --- |
| `pytest` | **22 passed, 1 skipped**（跳过项为 POSIX 权限位测试，Windows 不支持属预期） |
| `ruff check .` | 全部通过 |
| `black --check .` | 54 个文件全部合规 |
| Alembic 迁移 | `upgrade head` + `alembic check` 通过（由 `tests/test_database.py` 子进程实测覆盖） |

依赖注意项：`bcrypt` 必须 < 5.0（requirements 已约束 `>=4.2,<5.0`，实测 4.0.1 / 4.2.0 / 4.3.0 均全绿）。若装到 bcrypt 5.0.0，passlib 1.7.4 初始化即崩溃（4 个测试失败、登录接口直接 500），这是 passlib 已停维护的已知兼容性问题，团队安装时留意即可。

**结论：后端不是"只有框架"了——业务主流程已完整实现并通过测试，可以直接联调。**

## 2. 已实现功能清单（按模块）

### 2.1 账号与认证
- `POST /api/v1/auth/login`：用户名密码登录，返回 JWT（HS256，30 分钟过期，`sub`=用户 id，附带 `role` claim）+ 用户信息
- `GET /api/v1/auth/me`：当前用户
- `POST /api/v1/users`、`GET /api/v1/users`：仅 admin 可建号/查号；密码 ≥10 位，用户名 `[A-Za-z0-9_.-]` 3-80 位
- 首个管理员：`.env` 配置 `INITIAL_ADMIN_PASSWORD` 后，启动时自动创建（生产环境强制要求配置强密钥）
- 没有 refresh token、没有用户自助注册（需知悉）

### 2.2 角色与权限
- 三种角色：`admin` / `supervisor`（督导）/ `teacher`（教师）
- 课程级权限隔离已实测：admin 全量；督导只访问自己负责的课程；教师只访问分配给自己的课程；跨课程访问返回 403

### 2.3 课程
- `POST /api/v1/courses`：admin/督导可建课，校验 teacher_id 必须指向激活的教师账号；督导只能把自己设为督导人
- `GET /api/v1/courses`（按角色过滤）、`GET /api/v1/courses/{id}`

### 2.4 录音上传（隐私设计完整）
- `POST /api/v1/courses/{id}/recordings`，multipart 表单字段：`file`、`recorded_at`（**必须带时区**）、`consent_confirmed`（授权确认，必须为 true）、`consent_version`（可选）
- 仅接受 WAV/MP3/M4A；扩展名 + `ffprobe` 真实容器/音频流双重校验（需本机装 FFmpeg，否则上传返回 503）
- 大小双层限制：ASGI 中间件（解析前拦截，返回 `code:41300`）+ 端点内 500MB 上限
- 文件写入私有目录（POSIX 0700/0600），临时文件校验通过后原子改名
- 成功后自动创建 `Recording` + `ProcessingTask(QUEUED)`

### 2.5 AI Worker 内部协议（"接口预留"的核心形态）
后端**不运行任何 AI 模型**，由 AI 同学的独立进程轮询接入（协议文档：[ai-worker-integration.md](ai-worker-integration.md)）：
- `POST /internal/tasks/claim`：领取任务（`X-Service-Token` 服务令牌），返回一次性 `claim_token`、`audio_url`、租约 300 秒、尝试次数；无任务返回 `data:null`
- `GET /internal/tasks/{id}/audio`：凭 claim token 下载原始音频
- `POST /internal/tasks/{id}/lease`：续租
- `POST /internal/tasks/{id}/result`：回传结果，契约即 [schemas/business.py](../app/schemas/business.py) 的 `EvaluationResultInput`（详见 §4）；重复提交幂等，不同结果 409
- `POST /internal/tasks/{id}/failure`：失败重排队，最多 3 次后 `FAILED`；进程崩溃靠租约过期自动回收
- 并发安全靠 SQL 条件 UPDATE（两个 worker 不可能同时领到同一任务），已实测

### 2.6 评价、督导与历史对比
- `GET /recordings/{id}/status`：轮询 `QUEUED/PROCESSING/SUCCEEDED/FAILED`（前端唯一的处理进度信息来源）
- `GET /recordings/{id}/evaluation`、`GET /evaluations/{id}`：单次评价详情
- `GET /courses/{id}/evaluations`：分页历史（`page/page_size/total`，按录制时间倒序）
- `GET /courses/{id}/comparison`：最近两次课堂的总分与 BOPPPS 六维差值（`delta` 结构）
- `POST /evaluations/{id}/reviews`：督导评语（教师 403）
- `POST /evaluations/{id}/calibrations`：督导人工校准总分/分维分数，读取时取最新校准值覆盖模型分
- 规则建议：AI 未提交建议时，按问题 + 低于 60 分的维度生成最多 3 条模板建议（`source:"rule"`）
- 隐私脱敏：手机号/邮箱/身份证号正则遮蔽，覆盖转写、证据、问题、评语；AI 原始结果（`raw_result`）只存库、不对外返回

### 2.7 数据库
- 10 张表：users、courses、recordings、processing_tasks、evaluations、transcript_segments、dimension_scores、improvement_suggestions、evaluation_reviews、score_calibrations
- Alembic 迁移 1 个（`10441b2742d3`）；默认 SQLite，可换 MySQL/PostgreSQL

## 3. 仍为抽象/预留的部分

| 位置 | 状态 | 说明 |
| --- | --- | --- |
| [app/ai/interfaces/](../app/ai/interfaces/) | 抽象接口 | ASR / 说话人 / BOPPPS / 建议生成仅 ABC 契约，无实现、无模型调用 |
| [app/tasks/](../app/tasks/) | 空模块 | 耗时任务编排由外部 worker 轮询完成，无 Celery/Redis |
| [app/storage/base.py](../app/storage/base.py) | 抽象接口 | `StorageInterface` 未接入业务；实际存储直接用了本地文件实现 |
| [app/repositories/base.py](../app/repositories/base.py) | 未使用 | 泛型 `BaseRepository` 已定义，但 endpoints 直接操作 Session |
| JWT | 简化 | 无 refresh token，30 分钟过期后只能重新登录 |
| 实时推送 | 无 | 无 WebSocket/SSE，前端只能轮询 status |
| 编辑接口 | 无 | 课程/录音无 PATCH；用户列表无分页 |

## 4. 前端需要对齐的关键契约

### 4.1 六维固定 key（mode=boppps 时必须齐全，0-100 分）
`bridge_in`（导入）、`objectives`（目标）、`pre_assessment`（前测）、`participatory_learning`（参与式学习）、`post_assessment`（后测）、`summary`（总结）

### 4.2 评价详情 JSON 形状（脱敏后返回）
- `overall_score`（生效总分，校准后可能 ≠ 模型分）与 `model_overall_score`（AI 原始分）**同时存在**
- `dimension_scores`：生效六维；`segments`：`{start_seconds, end_seconds, text, speaker_id, role}`，role ∈ `teacher|student|unknown`
- `problems`：字符串数组；`suggestions`：`{text, source}`，source ∈ `ai|rule`
- `reviews`、`calibrations`：督导评语与校准历史数组

### 4.3 上传表单（前端必须照此实现）
`file` + `recorded_at`（ISO8601 带时区，如 `2026-10-01T09:00:00Z`）+ `consent_confirmed=true` + 可选 `consent_version`；成功返回 `{recording_id, task_id, status:"QUEUED"}`

### 4.4 前端联调策略建议
1. 按 `schemas/business.py` 把 TypeScript 类型对齐（需要的话我可以直接生成）
2. **写一个假 AI worker 脚本**：按 internal 协议轮询 claim → 下载音频 → 回传假结果。协议文档给了完整样例，几十行 Python 即可，前端就能端到端跑通"上传→处理→评价→校准→对比"全流程，不再依赖 mock
3. 状态轮询间隔建议 5-10 秒；AI 处理单次租约 300 秒（可续租），最长等待约 15 分钟（3 次尝试）

## 5. 问题与风险清单（建议反馈给后端同学）

1. **文档与实现不一致**：README 声明分层为 API→Service→Repository→Database，但实际 endpoints 直接操作 Session，`repositories/base.py` 与 `services/recordings.py` 是事实上的业务层。功能不受影响，属实现简化，建议要么接上 Repository 要么更新文档声明。
2. **async 端点内的同步阻塞**：`upload_recording` 是 async 函数，内部做同步文件 IO（分块写盘、ffprobe 子进程）和同步 DB 提交，单 worker 高并发上传时会阻塞事件循环。课程项目规模可接受，但值得知悉。
3. **ffprobe 外部依赖**：后端和任何部署环境都需要安装 FFmpeg，否则所有上传返回 503；Windows 本机开发环境需自装。
4. **无 refresh token**：前端 30 分钟后必然掉登录，需要产品层面接受"重新登录"或后端补刷新机制。
5. **上传无进度反馈**：multipart 一次性提交，前端拿不到上传进度百分比（只能显示"上传中"），需要进度条的话得改协议（如分片上传）。
6. **bcrypt/passlib 兼容性**：passlib 1.7.4 已停维护，与 bcrypt 5.x 不兼容（实测崩溃）。requirements 已约束 `<5.0`，但建议在 README 写明"不要手动升级 bcrypt 到 5.x"。
7. **Windows 文件权限**：POSIX 0700/0600 在 Windows 不生效（测试跳过），README 已注明需 NTFS ACL，部署时注意。

## 6. 测试覆盖质量（正面评价）

`tests/test_teaching_workflow.py`（411 行）端到端覆盖了：完整角色权限矩阵、上传边界（无授权 422 / 超大 413 / 假音频 415 / 伪造扩展名）、worker 协议全流程、结果幂等与 409、失败重试 3 次、脱敏（手机号/邮箱/身份证不出现在响应）、校准生效、历史与对比 delta、级联删除与 commit 失败时文件保护。模拟 Worker 仅证明契约正确，不证明 AI 准确率（README 已有同样声明）。
