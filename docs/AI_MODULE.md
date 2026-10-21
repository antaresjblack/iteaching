# 爱教学 AI 模块

独立 Python 3.10+ 服务。提供阿里云音频转写、教学评价、改进建议及历史评价对比。语音功能使用DashScope SDK；登录、数据库和前端由其他模块负责。完整接入步骤见 QUICKSTART.md。

## 启动与验证

```powershell
python -m unittest discover -s tests -v
python -m iteaching_ai.server
```

默认监听 `127.0.0.1:8010`。未配置模型时，显式返回 `demo=true` 的演示结果：不生成教学得分，不可作为真实教学质量结论。

真实模型模式需设置环境变量（切勿提交密钥）：

```powershell
$env:ITEACHING_MODE = 'live'
$env:ITEACHING_MODEL_URL = 'https://你的服务地址/v1/chat/completions'
$env:ITEACHING_MODEL = '你的模型名'
$env:ITEACHING_API_KEY = '你的密钥'
python -m iteaching_ai.server
```

适配接受 Chat Completions 风格请求的服务；并不保证所有提供商支持。默认调用超时60秒，遇到429/5xx最多重试一次。真实服务未配置、调用失败或返回不合法时返回错误，绝不回退成演示评价。真实模式会把提交的文本和教学目标发送到所配置服务，使用前须确认数据授权。

## 接口

- `GET /health`：健康状态与运行模式。
- `POST /api/ai/evaluations`：课堂分析评价。
- `POST /api/ai/suggestions`：依据已有评价生成改进建议。
- `POST /api/ai/comparisons`：比较同一课程的历史评价。

成功返回 `{"data": ...}`；参数错误400，模型错误502，请求体超过1MB返回413。服务仅面向本地联调，部署时由后端负责鉴权、限流、任务队列、持久化与访问控制；跨域由网关统一配置。API是同步的，耗时分析建议由后端任务队列调用。

### 课堂评价输入

```json
{
  "course_id": "course-001",
  "lesson_id": "lesson-001",
  "taught_at": "2026-10-17",
  "teaching_goals": "理解二分查找的条件与过程",
  "segments": [
    {"id": "s1", "start_seconds": 0, "end_seconds": 20, "text": "今天学习二分查找，目标是理解有序数组的查找过程。"},
    {"id": "s2", "start_seconds": 20, "end_seconds": 40, "text": "请同学们讨论如何缩小查找区间。"}
  ]
}
```

输出包含 `evaluation_id`、课程/课次/日期、`rubric_version`、`demo`、`summary`、`indicators`。六个BOPPPS指标为 `bridge_in/objectives/pre_assessment/participatory_learning/post_assessment/summary`，每项包含 `status`、0—100分或null、`reason` 和 `evidence`。证据为 `{segment_id, quote}`，引文必须逐字存在于对应片段；无证据只能返回 `insufficient_evidence`，其分数为null。系统验证结构和引文存在性，语义合理性仍需人工复核。指标是项目初始配置，不是权威认证标准。

### 建议输入

```json
{"evaluation": "替换为完整评价对象"}
```

真实模式由模型输出每条建议的 `indicator_id/problem/action/priority/verification`。只接受有证据支持的已评价指标。证据不足项单独放入 `evidence_gaps`，作为补充资料提醒，不当作教学缺陷。输出保留 `evaluation_id` 和 `demo`。

### 历史对比输入

```json
{"evaluations": ["完整评价对象1", "完整评价对象2"]}
```

传入2—20个评价；同课程、同指标版本、同运行模式、不同课次，按授课日期排序（同一天按课次ID排序）。返回逐项时间序列、首末差值、`improved/declined/stable/not_comparable`、持续薄弱项及确定性分析摘要。不补零，不将缺失分数当作退步，不把分数上升解释为某项措施的因果效果。仅首末均有得分才计算差值。持续薄弱定义为最近两次均有得分且低于60分，是可调整的项目规则。历史对比以确定性逻辑实现，减少模型算数误差。

## 后端集成

可直接 `from iteaching_ai.service import AIService` 并调用 `evaluate(payload)`、`suggest(payload)`、`compare(payload)`，也可通过HTTP调用。后端负责传入可信的课堂资料和已保存评价；本模块不将客户端提交的评价视为已认证记录。模型适配器通过 `AIService(provider=...)` 注入，约定 `generate(task, payload)` 返回字典。内置 `AliyunASR` 提供 `transcribe_file(path)`、`submit(payload)` 和 `fetch(payload)`，输出上述片段结构。

限制：单次最多5000片段、合计50000字符，超限明确拒绝，避免静默截断；自动分块、跨块总结留作后续扩展。未实施教师身份识别或学生行为推断。当前服务不保存数据，也不记录课堂文本或密钥。
