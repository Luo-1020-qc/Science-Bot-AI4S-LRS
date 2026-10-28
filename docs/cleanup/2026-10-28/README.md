# 工作区清理与保留证明

用户授权：清理整个LangGraph_RL_Agent；将无关历史工作移到CityU_Hackathon_AI4S其他位置；清除重复交付和弃用v1；保留Harness架构与训练权重；合并关联Markdown。

## 实际处理

- 历史运行输出、旧delivery、迁移维护目录、旧交付验证／打包脚本、阶段文档及过期文档快照移到同级`ScienceBot_Archive_2026-10-28`。
- 删除训练数据目录中的弃用v1及根目录重复兼容树，以及只用于建立v1快照的旧脚本与索引。保留当前v2基础集、示例批次、展开注释版和专家文档。
- 旧delivery中的policy_checkpoint完整移到`RUT_Science/models/retained_delivery_checkpoint`；其他现存权重不删除、不改写。
- 当前仍被代码加载的`models/planner/v1`、`data/darcy_cpu_v1`和general_v1不属于弃用版本。固定研究的reference_copy被回归测试／来源检查使用，保留为依赖，不作为重复交付入口。
- 合并根规划、交接、交付和阶段总结到[PROGRESS](../../PROGRESS.md)；工作区、G1／G2／访谈和研究接口说明合并到[USAGE](../../USAGE.md)；API／动作／权重说明合并到[ARCHITECTURE](../../ARCHITECTURE.md)。专家交接只保留一份主文档。
- 旧迁移审计依赖已移出的delivery和v1副本；当前审计改为相对路径的protected_current清单。未改写原研究冻结源文件、奖励、选择规则或模型参数。
- 研究上线交付中独有的26项会话／worker测试与3项HTTP测试归入`RUT_Science/tests`，复用现有HTTP辅助类，避免把有效Harness回归测试随旧交付一并弃用。

本次未发现需要单独删除的“外部科研工程源码”；当前数值与Darcy模块仍被Harness调用，因此保留。移出的是历史科研运行、打包／验证脚本和交付备份，不以文件名中含Darcy、v1就一律删除。

## 记录

| 文件 | 用途 |
|---|---|
| [plan.json](plan.json) | 清理前明确列出的移动／删除目标及理由 |
| [inventory_before.json](inventory_before.json) | 清理前文件大小和SHA-256；不含密钥内容 |
| [protected_before.json](protected_before.json) | 原架构／权重及清理后去向 |
| [protected_current.json](protected_current.json) | 主仓库保留制品的便携相对路径哈希 |
| [preservation.json](preservation.json) | 1781项保护核验结果，含1642项权重相关材料 |
| [verification.json](verification.json) | 清理后的测试、链接和可运行性验收摘要 |

原44项移动、22项弃用删除来自主计划；另将重复的短版专家手册移到归档merged_documents，操作均限定已核验的项目／同级归档范围。历史文件不被误标成当前源码。

清理只作用于工作树，不重写Git历史，也不擅自提交或推送。API_key_Agent.json与虚拟环境保留，本轮不调用真实模型、不运行科学训练、不提升默认策略。
