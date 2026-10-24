# 爱教学智能教学管理平台

课堂录音上传 → OSS 临时存储 → 阿里云异步转写 → BOPPPS 评价与建议 → 督导校准与历史对比。

## 代码结构

- `backend/`：FastAPI 后端、数据库迁移、权限、任务队列和接口测试。
- `frontend/`：Vue 3 页面、图表和前端测试。
- `iteaching_ai/`：音频转写、AI 评价、建议、对比及任务 Worker。
- `tests/`：AI 模块测试；`examples/`：接口示例。
- `docs/AI_MODULE.md`：AI 独立接口说明。
- `OSS_SETUP.md`：OSS 配置；`EVALUATION_FRAMEWORK.md`：评价框架。

## 首次安装（在仓库根目录运行）

需要 Python 3.10+、Node.js/npm、FFmpeg（ffmpeg 和 ffprobe 加入 PATH）。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -r backend/requirements.txt -r backend/requirements-dev.txt
Copy-Item .env.example .env
Copy-Item backend/.env.example backend/.env
cd frontend
npm ci
cd ..
```

只在首次安装且没有本地配置时复制模板。填写根目录 `.env` 中的百炼、OSS 配置；填写 `backend/.env` 中的数据库、管理员和安全配置。两处 `AI_SERVICE_TOKEN` 必须一致，使用自生成的随机密钥。真实 `.env` 不提交。

## 启动

分别打开三个 PowerShell 窗口，在仓库根目录执行：

```powershell
.\start-backend.ps1
# 第二个窗口
.\start-frontend.ps1
# 第三个窗口
.\start-worker.ps1
```

网页 http://localhost:5173 ，健康检查 http://127.0.0.1:8000/api/v1/health 。OSS 模式无需内网穿透。可运行 `.\check-ready.ps1` 检查依赖和配置。

Python 修改后需重启对应后端或 Worker；不要重复启动占用同一端口的后端。

## 测试

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
cd backend
..\.venv\Scripts\python.exe -m pytest
cd ../frontend
npm test
npm run build
```

测试使用模拟 AI；真实上传后的 Worker 会使用实际云服务。

## 上传范围

提交此目录下的源代码、测试、迁移、依赖锁文件和配置模板。不要上传 `.env`、录音、数据库、`runtime`、`outputs`、虚拟环境、`node_modules` 和构建产物。不要通过网页拖拽整个运行目录绕过 `.gitignore`。

本机代码、AI 配置与任务记录已统一到此仓库。启动脚本优先使用仓库内 `.venv`，也可复用上一级已有 `.venv`；该虚拟环境不要直接移动。上一级启动脚本仅作为兼容入口。其他机器首次运行按上面的安装步骤配置。
