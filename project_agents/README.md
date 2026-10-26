# 快速使用

在 PowerShell 中进入仓库：`cd D:\desktop_programming\iteaching\课程\backend`。

- 只评估代码：`.\project_agents\run-optimize.ps1`
- 只生成测试方案：`.\project_agents\run-test.ps1`
- 两者联合运行：`.\project_agents\run-demo.ps1`

默认检查评价对比模块。独立脚本可加 `-Files '文件1', '文件2' -Task '你的要求'` 来换目标；加 `-DryRun` 只检查输入，不调用模型。

结果在 `outputs/agents/` 最新文件夹。代码评估看 `01-optimization.md`，测试方案看 `02-test-plan.md`。测试智能体单独运行不依赖之前的优化报告。两者均不修改业务代码、不执行生成的测试。

---

# 项目开发辅助智能体（CrewAI）

两个本地运行的角色智能体：代码优化助手先检查实现，测试设计助手接收优化报告并检查已有测试。使用 CrewAI Agent / Task / Crew 顺序编排，模型通过 ReAct 自主选择只读工具。

## 安装与配置

在仓库根目录执行（Python 3.10–3.13）：

```powershell
python -m venv project_agents/.venv
.\project_agents\.venv\Scripts\python.exe -m pip install -r project_agents/requirements.txt
```

默认读取仓库根目录 `.env` 中已经配置的文本模型。可复制 `project_agents/.env.example` 到 `project_agents/.env`，通过 AGENTS_MODEL、AGENTS_MODEL_URL、AGENTS_API_KEY 独立指定模型。URL 为完整的 HTTPS Chat Completions 地址。无需购买 CrewAI 云平台。

## 使用

现有环境已准备时，可直接运行 ` .\project_agents\run-demo.ps1 `；加 `--dry-run` 只检查输入。

先执行免费输入检查：

```powershell
.\project_agents\.venv\Scripts\python.exe -m project_agents.runner --dry-run --task "检查评价对比缓存和异常处理，设计回归测试" --files backend/app/services/comparison_analysis.py backend/tests/test_comparison_analysis.py
```

删除 `--dry-run` 即开始实际调用模型，会消耗所配置服务的额度。无需重启教学平台。

每轮输出到 `outputs/agents/日期-编号/`：

- `01-optimization.md`：优化建议，不等于已确认缺陷。
- `02-test-plan.md`：待执行测试用例，不等于测试结果。
- `interaction.jsonl`：原始任务、模型交互及工具调用记录，敏感值遮蔽。
- `run.json`：运行状态、输入文件哈希、模型调用次数及实际返回的Token统计。
- `team-review.md`：团队填写采纳情况、理由和真实验证结果。

## 角色与边界

代码优化：关注重复代码、异常处理、维护成本及明显性能问题；必须给出文件行号、最小修改方案、风险和验证办法。

测试设计：结合现有测试与优化建议，设计正常、边界、异常和回归场景；输出可执行步骤与预期结果。

工具只有 `read_source`（指定文件快照，带行号）和 `read_selected_diff`（这些文件相对 HEAD 的差异）。最多8个文件、合计70000字符；禁止路径越界和敏感目录，禁止读取 `.env`、数据库、音频、依赖目录。源码中的文本视作资料而不是指令。

每个智能体最多4次推理迭代；底层两者共用最多8次HTTP调用预算（可用 `--max-calls` 调整至2–12）。每次最多输出2400 Token，超时90秒，禁用网络自动重试。Token数不是人民币费用，实际收费以模型服务商账单为准。

不提供写文件、执行命令、联网搜索或代理委派工具，不自动修改业务源码。只由运行器将报告写入被 Git 忽略的 outputs/。云追踪与遥测默认关闭。依赖环境与教学平台隔离。

## 校验工具边界

```powershell
.\project_agents\.venv\Scripts\python.exe -m unittest project_agents.test_safety project_agents.test_llm -v
```

团队审阅报告后，自行实施选定修改，并实际运行测试，将结果填入审查记录。不要把模型设计的用例记录成“执行通过”。

官方参考：https://docs.crewai.com/en/installation 、https://docs.crewai.com/en/concepts/tools

## 已完成的本机演示

2026-10-25 使用当前配置的 qwen-plus 完成真实协作运行。结果目录：`outputs/agents/20261025-004056-6be2a6/`。两份原始报告及 `03-review-notes.md` 请配合阅读：模型可能误判现有行为，运行成功不代表建议正确。

本轮6次调用、13530 Token；本次调试合计22701输入Token、8453输出Token、31154总Token（包括首次被截断的调用及两次完整运行）。实际费用以服务商账单为准。

依赖检查和5项本地测试通过；模型提出的业务测试尚未执行。`requirements-lock.txt` 保存本机 Windows/Python 3.13 的完整版本快照，其他平台优先使用 requirements.txt。

若出现回调不可序列化的警告，这是框架的断点恢复提示；本工具不提供断点恢复，报告保存不依赖该功能。失败后重新运行会创建新目录。
