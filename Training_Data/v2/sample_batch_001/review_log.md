# 批次审阅与未决事项

## 自动检查

任务作者／兼容性审阅者：`automated_synthetic_fixture_author_NOT_A_HUMAN_EXPERT`。当前approved状态只指允许作为合成程序夹具加载，并非真人科学审批；审阅时间记录在每个任务中。

已检查闭合Schema、唯一task_id、训练分区与共享来源登记、工具参数、参考闭环、公开证据停止、实际on-policy行为概率／critic值及参数更新。验收详情见verification.json。

## 仍待人类专家处理

| 对象 | 待审事项 | 当前状态 |
|---|---|---|
| Darcy方案 | 现实数据独立性、区组结构、sigma与效应依据 | pending human review |
| CViT方案 | 预算公平性、区组／训练运行层级、交互及结论范围 | pending human review |
| 合理停止 | 现实可行替代行动，以及当前环境的停止奖励是否恰当 | pending human review |
| 3条新状态标注 | 多个合理动作、拒绝动作及理由 | pending human review；需先注册批次队列 |

没有真实专家分歧裁决记录；不能把尚未审阅解释为一致同意。专家修订需形成新版本化ID，并明确哪些依据得到了外部验证。
