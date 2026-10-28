# science Bot 当前交接入口

G2.4更新：[本轮交付](RUT_Science/delivery/g2_4_update/README_本轮交付.md) 已完成研究层DOE协议、统一验收/评分和待专家校准任务库。49项新增研究测试通过，整体125项；84/42/42案例、42条待审、0真人专家标签。协议审核不授权真实执行，未训练新策略。

更新日期：**2026-10-27**。

[阶段总结](阶段性总结2_2026-10-27.md) 是本次完整交接：覆盖评测原型、Darcy、LangGraph、数值策略训练、工作区整理、通用化 G1/G2/G2.1，以及 G2.2/G2.3 策略研究。

当前应用仍由 `science-bot.cmd` 启动，通用访谈默认使用规则。已实现项目问答、受限 CSV 设计与执行、持久访谈、确认与恢复。CViT 真实训练、通用领域插件和学习策略上线尚未交付。

G2.2、G2.3 已合并到 [统一研究模块](RUT_Science/research/strategy_learning/README.md)，原两个独立测试文件夹已移除。两轮保留独立的冻结协议、任务、源码、模型、轨迹及负结果，共享研究入口、当前完整性检查和结果索引。它们不注册为应用真实工具，不加载到线上访谈。

本次检查：两轮研究 76 项测试通过；冻结制品与迁移前一致；应用核心代码、数据、模型、提示词、论文资料、配置和启动入口不变。历史“原项目未变化”清单仅证明当轮隔离实验，当前合并使用新的哈希验收，见 [维护记录](maintenance/consolidation_2026-10-27/README.md)。

G2.4已提供一致的严格评分与开发选模接口；下一步取得真正的专家审阅、校准规则并建立独立案例与跨任务验证。暂不继续堆叠 PPO 预算，也不连接真实 CViT 工具；具体验收条件见阶段总结。

历史与使用资料：

- [2026-10-21 交接快照](RUT_Science/docs/Science_Bot_项目交接_2026-10-21.md)
- [G1 通用入口](RUT_Science/docs/Science_Bot_G1_通用入口_zh.md)、[G2 表格实验](RUT_Science/docs/Science_Bot_G2_表格与实验设计_zh.md)、[G2.1 设计访谈](RUT_Science/docs/Science_Bot_G2_1_设计访谈与学习环境_zh.md)
- [原数值RL研究结果](RUT_Science/delivery/实际交付与研究结果.md)
- [G2.2 当前研究说明](RUT_Science/research/strategy_learning/studies/g2_2/README_本轮交付.md)、[G2.3 当前研究说明](RUT_Science/research/strategy_learning/studies/g2_3/README_本轮交付.md)

旧报告是当时的交付证据，不作为当前完成状态清单。模型输出展示、工作区绑定和旧会话兼容继续沿用既有实现。
