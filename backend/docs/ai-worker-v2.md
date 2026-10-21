# AI Worker v2契约

新增结果 `version: 2`，原有v1输入继续兼容。身份认证、任务租约及幂等回传沿用ai-worker-integration.md。

claim增加course_id、recorded_at、duration_seconds和original_filename。Worker必须使用后端元数据，不自行生成课程和日期。后端尚未提供教学目标/教案字段，文本分析不得据此推测材料内容。

v2结果必须包含：

- `rubric_version`：非空评价标准版本。
- `indicators`：六项不重复的BOPPPS指标；每项包括id、status、score、reason、evidence。
- `status`为evaluated时，score为0—100，evidence非空；insufficient_evidence时score=null且evidence=[]。
- `evidence`中的segment_id按提交segments数组顺序编号s1、s2等，quote必须逐字存在于对应文本。
- `dimension_scores`与六项指标分数完全一致，允许null。
- `overall_score`只在六项都有分数时计算等权平均并保留两位小数，否则null。该规则为项目约定。
- 原有transcript、segments、overall_evidence、problems、suggestions仍适用。未识别说话人时role=unknown。

新增数据库迁移 `2a10_ai_nullable_scores`，运行 `alembic upgrade head`。总分/维度分数允许空值；旧数据不补零、不删记录。数据库存在空值时禁止降回旧契约。

展示接口返回的indicators及model_dimension_scores为模型原始判断（证据文本经过基础遮蔽）；overall_score及dimension_scores仍是督导校准后的有效分数。前端必须区分两者，null显示“依据不足”。最近两次对比基于有效分数，版本或模式不同不可比，单项缺失的差值为null。

本次跨项目Worker位于仓库旁的 `课程/iteaching_ai/worker.py`，完整部署步骤见课程目录INTEGRATION.md。测试 `tests/test_ai_worker_v2.py` 会寻找上级AI包；独立后端检出未提供该包时会明确跳过。其他后端测试不受影响。
