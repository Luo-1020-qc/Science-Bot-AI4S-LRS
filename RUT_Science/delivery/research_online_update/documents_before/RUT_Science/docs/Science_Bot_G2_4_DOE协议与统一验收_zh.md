# G2.4：DOE协议与统一验收

日期：2026-10-27。实现位于 [统一研究模块 / G2.4](../research/strategy_learning/studies/g2_4/README_本轮交付.md)。本轮交付研究层的可运行协议与检查，不改变应用对话入口；线上G2/G2.1仍只有原先的三类表格工具。

G2.4将研究问题、因素、实验单位、随机化、重复、区组、主要对比、模型、功效、预算和验收步骤保存为闭合结构；用固定验收器判断候选，再把同一语义用于反馈、开发选模和后续最终评分。

第一版支持两处理完全随机设计、两处理随机完全区组设计和2×2全因子设计。假定固定效应、正态同方差误差；有区组时需声明处理与区组无交互。编译器生成随机计划和矩阵，检查可估计性、残差自由度、非中心t名义功效及成本。技术重复不增加实验单位数。

协议通过表示可以审阅。真实独立性、测量质量、模型假设与实际随机化保持未验证；所有后续执行步骤未执行，科学结论为空。封存测试没有用于本轮诊断。

已保存84/42/42个训练/开发/封存案例；49项测试通过，42个开发诊断符合脚本预期。42条专家待审记录仍未批准，不能称为专家校准完成。没有新BC/PPO训练、模型API、真实工具或GPU运行。

在项目根目录使用原研究入口：

```powershell
& '.\RUT_Science\.venv\Scripts\python.exe' -B 'RUT_Science/scripts/science_bot_research.py' test --study g2_4
& '.\RUT_Science\.venv\Scripts\python.exe' -B 'RUT_Science/scripts/science_bot_research.py' demo --study g2_4
& '.\RUT_Science\.venv\Scripts\python.exe' -B 'RUT_Science/scripts/science_bot_research.py' verify --study g2_4
```

完整命令、公式、审阅导入、方法来源和限制见研究说明；交付验收见 [delivery/g2_4_update](../delivery/g2_4_update/README_本轮交付.md)。下一阶段需要真人审阅和独立案例，然后才能评估BC、DAgger及PPO的真实增益。
