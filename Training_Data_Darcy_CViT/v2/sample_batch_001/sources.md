# 来源、划分和数据血缘

本批由自动化助手编写，基于v2的task_for模板及既有离线工具环境；不是外部专家提供的真实研究数据库。

3个任务均沿用`synthetic_darcy_source_A`和`synthetic_darcy_family_source_A`，只属于train。CViT与Darcy共享该合成模板祖先，未通过重命名伪装成独立科学来源。原开发来源B、公开评价来源C不进入本批采样。

`mock://source_A/train`、`mock://source_A/validation`、`mock://source_A/test`仅是科学数据内部划分的声明，不指向已经存在的真实数组，也不能证明实际划分独立性。真实专家扩充时必须替换为可核对的来源版本与划分依据，并重新审阅。

所有示例均公开。独立科学来源新增数0，盲测新增数0，真人专家标签0。不得把这3个变体当成新的独立评测样本报告泛化结果。

行为策略的概率和值只来自实际CPU策略采样。脚本参考与PPO rollout分开；工具反馈和制品写入v2/tool_runtime/sessions中的独立会话，不触碰其他科学工作区。
