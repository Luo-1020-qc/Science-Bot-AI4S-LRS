# 研究、策略与数据导航

本页区分在线应用、研究推理与训练数据，不将三者视为同一部署版本。

## 应用与研究接口

- 应用：[原终端入口](../science-bot.cmd)，LangGraph图位于`RUT_Science/rut_science/science_bot/general/graph.py`。
- 在线研究用法：[复现与演示说明](REPRODUCIBILITY.md)。`/research`、`/doe`运行本地受限研究请求。
- 历史工作与负结果：[合并阶段进展](PROGRESS.md)、[研究总览](../RUT_Science/research/strategy_learning/README.md)。
- 当前访谈默认规则。通过`/research simulate ... --policy ...`显式选择冻结研究策略，不代表默认对话已切换策略。

## 权重如何保留

G2.2／G2.3策略参数与其冻结研究文件一起保存在`RUT_Science/research/strategy_learning/studies/`。v2 PPO链路检查的更新参数位于[updated_policy.json](../Training_Data_Darcy_CViT/v2/ppo_smoke/updated_policy.json)，其初始策略、rollout与核验也在同目录。

权重与架构、特征顺序、动作映射、mask、工具版本一起加载。更换DeepSeek key不会修改这些文件。64步更新只是机械检查，不是已验证有效的比赛默认策略。

## 工具库与训练数据

- [详细工具库](../Research_Tool_Library/README_详细工具库.md)：45项契约、20项离线实现，包含方案修订、独立复核、冻结和模拟闭环。
- [数据总入口](../Training_Data_Darcy_CViT/README_训练数据说明.md)：只维护当前v2，弃用v1及根目录重复兼容树已清除。
- [专家交接文档](../Training_Data_Darcy_CViT/RL训练数据_专家交接文档.md)：任务、标注、DOE科学审阅和验收要求。
- [数据与RL协议](../Training_Data_Darcy_CViT/v2/README_可训练数据集.md)：静态示范不直接成为PPO数据；环境产生新on-policy采样。

详细工具库的20个离线实现已进入在线ToolRegistry，与训练宿主共用调用入口，见[工具接入说明](TOOL_LIBRARY.md)。v2候选策略和权重仍保留研究身份，没有自动成为在线默认策略；本轮未重训或执行真实科学任务。

## 下一阶段

先由专家扩充独立来源与机制组合、审阅合理替代动作和争议，再完成环境预检、训练适配器的观察／mask／奖励版本、正式训练与独立评测。工具注册和实际调用已经接入，下一步策略加载与效果验收仍需独立研究证据。
