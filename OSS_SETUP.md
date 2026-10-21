# 自动 OSS 转写配置

自动流程：网页上传到本机后端 → Worker 下载该录音 → 上传私有 OSS 临时对象 → 提交阿里云转写 → 生成教学评价和建议 → 回写后端供网页查看。

## 首次配置

1. 打开 RAM 控制台 https://ram.console.aliyun.com/ ，创建专用用户 `iteaching-oss-worker`。
2. 在“权限策略”中创建自定义策略，选择 JSON 编辑方式，粘贴本目录 `oss-ram-policy.json` 的全部内容。策略仅允许本项目 Bucket 的 `iteaching-temp/` 目录执行 PutObject、GetObject、DeleteObject。
3. 给该 RAM 用户授予这个自定义策略。
4. 在该用户的 AccessKey 管理中创建 AccessKey，选择本地开发用途（若页面询问）。将 AccessKey ID 和 Secret 填到项目根目录 `.env` 的 `OSS_ACCESS_KEY_ID` 和 `OSS_ACCESS_KEY_SECRET`。不要粘贴到聊天或提交 Git。
5. 根目录 `.env` 中的 `AI_AUDIO_STORAGE=oss`、Bucket、地域、目录前缀已准备好。百炼的 DASHSCOPE_API_KEY 保持原值。
6. 在 OSS 控制台为 `iteaching-temp/` 配置生命周期规则：例如创建一天后过期删除，作为进程被强制关闭时的清理兜底。自动临时对象应使用未开启版本控制的 Bucket；开启版本控制时还需配置非当前版本过期规则。

私有权限保持不变，无需公共读。程序显式上传私有对象，不使用手工保存的 OSS URL。AccessKey 在云端配置完成前，Worker 会在领取任务前报缺少凭证，不消耗任务尝试次数。

## 启动

分别在三个 PowerShell 窗口进入项目目录，运行：

```
.\start-backend.ps1
.\start-frontend.ps1
.\start-worker.ps1
```

网页：http://localhost:5173 。OSS 模式不需要 cloudflared，也不用更新 AUDIO_PUBLIC_BASE_URL。

先做短录音验证权限和完整业务流程，再测试长录音。Worker 会产生 OSS 存储/流量和模型调用费用。

## 失败与清理

阶段、云端任务 ID、临时对象路径保存在 runtime/worker。失败后不会自动重提付费转写。正常退出任务时清理 OSS 临时副本，原始本地录音仍保留用于网页回放。清理失败会记录对象路径，需手动删除或由生命周期规则清理。强制终止进程无法保证运行清理代码。

已有失败任务不会自动复活。此前独立 OSS 对照测试的转写结果位于 outputs/oss-comparison/result.json，尚未自动导入网页。

当前教学分析仍有限制：最多5000段、50000字符；超过上限会明确失败，不会偷偷截断。临时文件链接有效期两小时，转写等待上限一小时。多个 Worker 主机须共享防重复提交状态目录；当前默认是同机部署。
