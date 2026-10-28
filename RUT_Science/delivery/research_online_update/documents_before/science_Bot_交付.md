# science Bot 运行与交付入口

当前新增交付：[G2.4 DOE协议与统一验收](RUT_Science/delivery/g2_4_update/README_本轮交付.md)。使用同一研究脚本的 `--study g2_4`，默认all现覆盖三轮125项测试。专家校准待审，线上入口保持原状。

更新日期：2026-10-27。完整状态见 [阶段总结](阶段性总结2_2026-10-27.md)。交付采用现有目录，不新增压缩包。

在本目录打开 PowerShell，沿用原入口：

```powershell
.\science-bot.cmd
.\science-bot.cmd -Backend offline
.\science-bot.cmd -Workspace "D:\my-project"
```

通用模式默认使用规则访谈；离线启动不自动启用研究 PPO。研究里的 BC/PPO 模型没有推广到应用。

[G2.2 / G2.3 研究入口](RUT_Science/research/strategy_learning/README.md)：

```powershell
& '.\RUT_Science\.venv\Scripts\python.exe' -B 'RUT_Science/scripts/science_bot_research.py' test
& '.\RUT_Science\.venv\Scripts\python.exe' -B 'RUT_Science/scripts/science_bot_research.py' verify
```

上面仅检查合成环境、模拟工具和制品完整性，不调用真实工具或训练 CViT。当前合并验收为 39＋37 项测试通过，见 [本次维护记录](maintenance/consolidation_2026-10-27/README.md)。

应用使用说明：[工作区](RUT_Science/docs/Science_Bot_Workspace_zh.md)、[G2](RUT_Science/docs/Science_Bot_G2_表格与实验设计_zh.md)、[G2.1](RUT_Science/docs/Science_Bot_G2_1_设计访谈与学习环境_zh.md)。历史完整应用回归记录在 [G2.1 交付](RUT_Science/delivery/g2_1_update/README_本轮交付.md)；本次没有重跑其中的真实实验或模型请求。
