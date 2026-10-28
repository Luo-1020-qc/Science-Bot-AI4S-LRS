# science Bot 交接入口

交接日期：2026-10-21。

2026-10-22 G2.1 更新：已交付多轮设计访谈与可学习决策环境，加入字段来源、未知/冲突处理、设计选项、版本化验证反馈及专家待审轨迹。规则与BC基线均可运行，当前未显示BC优势，规则仍为默认；未训练PPO。见 [G2.1使用说明](RUT_Science/docs/Science_Bot_G2_1_设计访谈与学习环境_zh.md) 与[验收](RUT_Science/delivery/g2_1_update/README_本轮交付.md)。

2026-10-22 G2 更新：已接入 CSV 检查、ExperimentSpec、设计与数据校验、确认后的通用计划执行；支持两独立组、配对和 mean/OLS 预测三类任务，结果与划分可重算。见 [G2 使用说明](RUT_Science/docs/Science_Bot_G2_表格与实验设计_zh.md) 和[本轮交付](RUT_Science/delivery/g2_update/README_本轮交付.md)。CViT 训练仍属于后续 G3；保留现有入口，不新增 ZIP。

2026-10-22 更新：G1 通用入口、原生工具调用、项目文件问答和原科研引擎统一调度已接入。保持原入口，不新增 ZIP。[当前使用说明](RUT_Science/docs/Science_Bot_G1_通用入口_zh.md)，本轮验收位于 `RUT_Science/delivery/g1_update/`。

完整交接文档：[science Bot 项目交接](RUT_Science/docs/Science_Bot_项目交接_2026-10-21.md)。

文档包含当前实现、启动与恢复命令、DeepSeek 接入、科研状态与持久化、测试证据、RL 研究结论、能力边界，以及后续任务的实施位置和验收标准。

原首要待办已实现：终端展示实际模型返回、单独标明宿主校验状态，并通过 `/model-output [list|编号]` 回看历史。沿用原启动入口，不新增压缩包。使用和验收位置见 [模型输出说明](RUT_Science/docs/Science_Bot_Model_Output_zh.md)。原交接时的范围与限制保留在完整文档中。
