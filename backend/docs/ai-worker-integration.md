# AI 处理进程联调约定

> 本文保留v1契约示例。现已增加v2契约：允许“依据不足”和空分数，支持结构化证据与评价标准版本。新Worker请参见 [v2接入说明](ai-worker-v2.md)。

后端不调用或实现 ASR、说话人识别、BOPPPS 评分模型。AI 同学运行独立处理进程，通过 `AI_SERVICE_TOKEN` 调用内部 API。所有成功响应采用 `code/message/data` 包装；失败响应的 HTTP 状态码和 `message` 描述原因。

## 认证和领取任务

内部接口使用 `X-Service-Token`。进程通过轮询领取一个待处理任务：

```http
POST /api/v1/internal/tasks/claim
X-Service-Token: <AI_SERVICE_TOKEN>
Content-Type: application/json

{"worker_id":"asr-worker-01"}
```

有任务时，响应 `data` 包含 `task_id`、`recording_id`、`attempt`、`lease_expires_at`、`audio_url` 和一次性 `claim_token`。没有任务时 `data` 为 `null`。数据库条件更新确保两个进程不会同时成功领取同一租约；领取令牌也用于拒绝旧租约处理进程的过期回传。

领取成功示例：

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "task_id": "f3a9cc6a-827d-47ec-b532-224f29edab02",
    "recording_id": "9f9e4e46-f6f7-41c0-bd4b-1c73ca74a70d",
    "worker_id": "asr-worker-01",
    "claim_token": "<one-time-claim-token>",
    "attempt": 1,
    "lease_expires_at": "2026-10-17T10:05:00Z",
    "audio_url": "/api/v1/internal/tasks/f3a9cc6a-827d-47ec-b532-224f29edab02/audio"
  }
}
```

领取后使用两个头下载原始录音：

```http
GET /api/v1/internal/tasks/{task_id}/audio
X-Service-Token: <AI_SERVICE_TOKEN>
X-Task-Claim-Token: <claim_token>
```

处理时间较长时，处理进程应在租约过期前续租：

```http
POST /api/v1/internal/tasks/{task_id}/lease
X-Service-Token: <AI_SERVICE_TOKEN>
X-Task-Claim-Token: <claim_token>
```

租约时长由 `TASK_LEASE_SECONDS` 设置，默认 300 秒。默认最多尝试 3 次；失败后端会立即重新排队，达到上限后进入 `FAILED`。进程崩溃且未回传时，租约过期后任务可被其他进程领取。

## 成功结果

使用以下接口回传。结果必须是 `version: 1`。`mode: "basic"` 可不提交六维分数；`mode: "boppps"` 必须完整提供六项 0–100 分数。时间单位为秒，发言角色只能为 `teacher`、`student` 或 `unknown`。

```http
POST /api/v1/internal/tasks/{task_id}/result
X-Service-Token: <AI_SERVICE_TOKEN>
X-Task-Claim-Token: <claim_token>
Content-Type: application/json
```

```json
{
  "version": 1,
  "mode": "boppps",
  "transcript": "教师：今天我们学习……",
  "segments": [
    {
      "start_seconds": 0.0,
      "end_seconds": 4.2,
      "text": "今天我们学习……",
      "speaker_id": "speaker_1",
      "role": "teacher"
    }
  ],
  "overall_score": 82,
  "overall_evidence": "目标清楚，学生互动充分。",
  "problems": ["后测环节覆盖不够充分"],
  "dimension_scores": {
    "bridge_in": 80,
    "objectives": 90,
    "pre_assessment": 75,
    "participatory_learning": 85,
    "post_assessment": 65,
    "summary": 80
  },
  "suggestions": [
    {"text": "增加覆盖不同难度目标的后测题目。"}
  ]
}
```

建议也可以是纯字符串数组。首次提交成功后任务状态变为 `SUCCEEDED`。同一结果重复回传是幂等的；不同内容不能覆盖既有评价，接口返回 `409`。数据库保存原始模型结果；教师和督导使用的标准评价接口会对常见手机号、邮箱和身份证号进行基础遮蔽，但这类规则不能识别所有个人信息。

成功回传响应示例：

```json
{"code":0,"message":"success","data":{"evaluation_id":17,"idempotent":false}}
```

## 失败结果

```http
POST /api/v1/internal/tasks/{task_id}/failure
X-Service-Token: <AI_SERVICE_TOKEN>
X-Task-Claim-Token: <claim_token>
Content-Type: application/json

{"reason":"transcription process exited with code 1"}
```

`GET /api/v1/recordings/{recording_id}/status` 面向有课程权限的前端，返回 `QUEUED`、`PROCESSING`、`SUCCEEDED` 或 `FAILED`。失败原因只在最终 `FAILED` 时展示，并经过基础隐私遮蔽。

## 联调顺序

1. 教师用 `POST /api/v1/courses/{course_id}/recordings` 上传音频，表单字段为 `file`、`recorded_at`、`consent_confirmed=true` 和可选 `consent_version`。
2. Worker 轮询 `POST /api/v1/internal/tasks/claim`，使用租约令牌下载音频。
3. Worker 回传成功结果，或回传失败原因等待重试。
4. 前端轮询状态接口，随后调用 `GET /api/v1/recordings/{recording_id}/evaluation` 展示结果。

Swagger UI 和生成的完整 OpenAPI 文档分别位于 `/docs`、`/openapi.json`。
