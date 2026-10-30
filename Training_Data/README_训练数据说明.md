# 训练数据入口

当前主线是科研澄清Harness：完整回合离线基线与设计交付已完成，下一步做人工校准，再审核主线决策状态、训练一个问题排序入口。计划见[规划指南](../docs/HARNESS_PLANNING.md#下一阶段只训练harness)，结果见[主线报告](../docs/evaluation/mainline_2026-10-30/REPORT.md)。当前不开展LLM微调或扩展旧PPO。

| 资料 | 用途 |
|---|---|
| [科研对话课程](scientific_dialogue_v1/README.md) | ClariQ/QASPER候选、负结果、来源、65份待标注任务及人工导入 |
| [专家交接](RL训练数据_专家交接文档.md) | v2任务、决策标注、DOE审阅、导入与预检 |
| [v2协议](v2/README_可训练数据集.md) | 32维/23动作工具环境、奖励和PPO数据边界 |
| [Darcy示例](v2/examples/darcy_full_example.json)、[CViT示例](v2/examples/cvit_full_example.json) | 固定离线工具流程 |
| [组员标注复核](expert_batches_inbox_2026-10-30/review/REPORT.md) | 31条工具动作候选的问题与待修订项 |
| [示例批次](v2/sample_batch_001/README.md)、[50场景批次](v2/synthetic_batch_050/README.md) | 原合成任务、训练过程与复现 |
| [正式PPO报告](v2/synthetic_batch_050/formal_2026_10_29/README_训练结果.md) | 8000步负结果：PPO 38/50，规则和BC 50/50 |

公开追问/证据候选、科研多轮对话和v2工具编排分别管理，不混用动作、奖励或来源分区。场景壳不是已审核对话，用户应答不是专家标签，参考轨迹也不能补造行为概率作为PPO采样。

`current_dataset.json`指定当前v2位置。日常完整性检查见[复现说明](../docs/REPRODUCIBILITY.md)，专项命令按各数据/实验说明运行；输出使用新目录，保留原始数据、参数与历史结果。
