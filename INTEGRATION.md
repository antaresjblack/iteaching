# 后端与AI模块联调说明

已拉取分支：`back_ended`，基线提交 `2f49f14cb727775ab796102098d87886b3e596ea`。

## 本地结构

```text
课程/
  iteaching_ai/          # 已有AI功能 + 新增worker.py
  .env                  # 阿里云密钥及Worker配置（不要提交）
  backend/              # GitHub仓库检出目录
    backend/            # FastAPI实际项目目录
      app/
      alembic/
      .env              # 后端配置，与外层.env是两个文件
```

## 对接方式

教师上传音频到后端 → 后端建任务 → Worker领取 → 带服务令牌和领取令牌下载私有音频 → FFmpeg转单声道16kHz PCM WAV → 阿里云转写 → 千问评价和建议 → Worker提交v2结果 → 后端存储及前端查询。

后端不需要主动调用原先8010端口的AI服务。Worker直接复用AIService和AliyunASR。原有独立HTTP/CLI接口仍保留，便于单独调试。

后端私有音频URL不提供给阿里云，也不向阿里云传递后端服务令牌。Worker下载后使用SDK上传音频流。轮询任务的间隔为5秒，处理中按租约剩余时间定期续租（不超过30秒间隔）。续租失效后不再回传旧任务结果。结果回传遇到网络/服务端错误最多重试三次，内容保持一致，利用后端幂等性避免重复评价写入。

## 已调整的接口与数据

1. 领取任务增加course_id、recorded_at、duration_seconds、original_filename，避免AI伪造课程和课次时间。
2. 新增结果version=2，保留version=1旧客户端兼容。v2要求rubric_version及六个详细indicators；每项包含status、score、reason和逐字证据。证据segment_id按提交segments顺序编号s1、s2等。
3. 依据不足项score=null，六维字典保留对应键；总分只有六项全部有依据时才计算等权平均（保留两位小数），否则null。这是课程项目实现规则，不是BOPPPS官方计分标准。
4. 数据库总分、维度得分允许null，新增Alembic迁移；不修改旧迁移、不用0填充。已有空分数时拒绝直接降级，避免数据损失。
5. 评价展示增加rubric_version、indicators和model_dimension_scores。indicators为原模型判断，dimension_scores/overall_score仍是人工校准后的有效分数。前端应区分模型证据与人工校准。
6. 最近两次课堂对比保留督导校准，空值不相减，不同rubric_version或mode不计算变化。
7. 修复原有建议字符串数组的输入兼容校验。

## 配置与启动

需要Python 3.11+，并安装FFmpeg工具集，使 `ffmpeg -version`、`ffprobe -version` 均可运行。当前机器检查时PATH中未找到两者。后端上传需要ffprobe，Worker转换需要ffmpeg。安装后重开终端。

在课程目录的.env中保留原来的阿里云配置，并添加：

```dotenv
AI_BACKEND_URL=http://127.0.0.1:8000
AI_SERVICE_TOKEN=自行设置的至少32位随机字符串
AI_WORKER_ID=aliyun-worker-01
```

在 `课程/backend/.env` 中按该目录的.env.example配置数据库、管理员密码、JWT密钥，并填写完全相同的AI_SERVICE_TOKEN。API Key和AI_SERVICE_TOKEN是两种不同凭据。不要把后端JWT密钥或登录密码写进Worker配置。

可在课程目录创建一个共享开发虚拟环境：

```powershell
cd D:\desktop_programming\iteaching\课程
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -r backend/requirements-dev.txt
```

终端1启动后端（先自行填写后端.env）：

```powershell
cd D:\desktop_programming\iteaching\课程\backend
..\..\.venv\Scripts\python.exe -m alembic upgrade head
..\..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

终端2启动Worker（真实模型调用可能计费）：

```powershell
cd D:\desktop_programming\iteaching\课程
.\.venv\Scripts\python.exe -m iteaching_ai.worker --once
# 正式轮询：去掉--once
```

后端Swagger为http://127.0.0.1:8000/docs。先登录、创建教师和课程，再上传有授权的短音频并观察状态及评价。Worker访问本机后端不走系统代理；52569只在拉取/安装命令中使用，没有改全局Git代理配置。

## 测试与限制

- 后端测试：在backend执行 `..\..\.venv\Scripts\python.exe -m pytest`。
- AI测试：在课程目录执行 `.\.venv\Scripts\python.exe -m unittest discover -s tests -v`。
- 新增跨项目测试使用真实FastAPI路由和SQLite，模拟转写/模型/音频转换；涵盖领取、下载、结果入库、空分数、证据、幂等回传、人工校准和历史比较。
- 集成测试自动寻找上级iteaching_ai目录；独立克隆后端、未提供AI包时该测试文件会明确跳过。
- 不假设说话人身份，暂时统一role=unknown；需要教师/学生识别时需另做说话人标注和效果验证。
- 后端目前没有教学目标/教案存储字段，因此Worker只依据课堂文本评价，不凭空填入教学目标。后续可在课程/录音模型与claim响应中增加对应字段。
- 后端已有最近两次课堂对比；原AI模块多课次对比仍可独立调用，尚未新增面向前端的多课次趋势接口。
- 前端须将null显示为“依据不足”，不能调用toFixed或以0代替；不同评价标准不可比时显示提示。
- Worker转换超时180秒、本地转写限制200MB PCM WAV、文本限制50000字符；超限会失败并按后端重试策略处理，未实现自动分块。
- 真实云端权限、费用、课堂转写准确性和长录音稳定性尚需填写密钥后实测。本次不会自动执行付费任务，也不会启动常驻Worker。
