# 阿里云接入：从音频到评价

## 1. 安装与填写密钥

在项目目录打开PowerShell：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
# 只有.env不存在时才复制，避免覆盖已填写的密钥
if (!(Test-Path .env)) { Copy-Item .env.example .env }
notepad .env
```

只需将 `DASHSCOPE_API_KEY=your-api-key` 的值替换为你的百炼API Key。默认北京地域，必须与密钥地域相符。其他地域须同时调整文本、HTTP语音、WebSocket语音地址及可用模型。环境变量优先于.env；改变.env后重启进程。

```powershell
.\.venv\Scripts\python.exe -m iteaching_ai.cli check
```

check只检查配置与依赖，不调用API，也不验证余额、权限或密钥有效性。

## 2. 本地录音转写（无需OSS）

准备单声道、16位PCM WAV文件。建议先使用1—3分钟经授权的音频：

```powershell
.\.venv\Scripts\python.exe -m iteaching_ai.cli transcribe "D:\你的录音\课堂.wav" --output outputs/transcript.json
```

采用官方 `paraformer-realtime-v2` 的本地文件非流式调用。会将音频发送到阿里云并产生相应费用；不是本地离线识别。长录音同步处理可能等待较久，正式长课堂推荐下一节异步接口。本模块仅接受200MB以内PCM WAV；不自动转换音频。若已安装ffmpeg，可转换：

```powershell
ffmpeg -i input.mp3 -ac 1 -ar 16000 -c:a pcm_s16le output.wav
```

## 3. URL异步转写（适合后端接入）

后端提供阿里云可访问的音频链接，可使用有足够有效期的OSS签名URL，无需把文件设为永久公开。

```powershell
.\.venv\Scripts\python.exe -m iteaching_ai.cli submit "https://你的音频链接"
.\.venv\Scripts\python.exe -m iteaching_ai.cli query "上一步返回的task_id"
```

状态PENDING/RUNNING时等待5—10秒再查询，勿重复submit。SUCCEEDED才会返回segments；FAILED/CANCELED/UNKNOWN时检查云端任务。查询结果默认保存到outputs/transcript.json。官方任务结果链接有有效期，完成后及时保存。查询由调用方控制，没有无限后台轮询。

## 4. 生成评价及建议

修改 `examples/lesson.json` 中课程ID、课次ID、授课日期和教学目标，再执行：

```powershell
.\.venv\Scripts\python.exe -m iteaching_ai.cli analyze outputs/transcript.json --metadata examples/lesson.json --output-dir outputs/lesson-001
```

输出evaluation.json及suggestions.json。先保存评价，再调用建议模型，建议失败不会丢失评价。课堂最多5000片段、50000文本字符，超限明确拒绝，不静默截断；自动长文本分块留作后续扩展。语音噪声与误转写会影响评价，应先人工校正transcript.json的segments文本。

## 5. 历史对比

另一次课堂使用不同lesson_id和实际授课日期生成结果，再执行：

```powershell
.\.venv\Scripts\python.exe -m iteaching_ai.cli compare outputs/lesson-001/evaluation.json outputs/lesson-002/evaluation.json
```

对比使用确定性计算，不额外消耗模型Token。课程与指标版本必须一致。输出指标序列、首末变化及最近两次持续低于60分的指标。

## 6. HTTP接口

```powershell
.\.venv\Scripts\python.exe -m iteaching_ai.server
```

| 路径 | 方法 | 请求 |
|---|---|---|
| /health | GET | 无 |
| /api/ai/transcriptions | POST | `{"audio_url":"https://..."}` |
| /api/ai/transcriptions/query | POST | `{"task_id":"..."}` |
| /api/ai/evaluations | POST | lesson.json内容加segments |
| /api/ai/suggestions | POST | `{"evaluation":完整评价对象}` |
| /api/ai/comparisons | POST | `{"evaluations":[评价1,评价2]}` |

成功响应为 `{"data":结果}`。HTTP不会读取调用者给出的任意本地文件路径；本地转写仅供可信Python调用或命令行。后端仍负责用户鉴权、上传存储和任务归属。音频接口始终调用真实云服务，即使文本评价处于demo模式也不伪造转写。

## 7. 测试与已知限制

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

测试使用模拟云端返回及本地HTTP请求，不发送真实录音、不调用付费API。真实密钥、模型权限、识别质量和完整云端链路须配置后联调确认。ASR不能判断说话人一定是教师；评价不能用于直接认定学生参与度或教学因果效果。所有结果仍需人工复核。

常见故障：401检查密钥；403检查模型权限及地域；429检查额度与并发；结果无时间戳、模型引用不存在的原文会明确报错。请勿把.env、课堂音频或outputs提交到代码仓库。

## 官方协议依据

- [录音文件转写SDK](https://help.aliyun.com/zh/model-studio/paraformer-recorded-speech-recognition-python-sdk)
- [本地文件语音识别SDK](https://help.aliyun.com/zh/model-studio/paraformer-real-time-speech-recognition-python-sdk)
- [千问兼容接口](https://help.aliyun.com/zh/model-studio/qwen-api-via-openai-chat-completions)
