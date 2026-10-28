# science Bot 交付入口

项目实现：相邻 `RUT_Science/rut_science/science_bot/`。

新增 [通用项目工作区](RUT_Science/docs/Science_Bot_Workspace_zh.md)：启动时使用 `-Workspace "D:\my-project"`，进入后用 `/workspace`、`/files` 和 `/read` 查看项目。

```powershell
.\science-bot.cmd
# 离线模式仍使用实际训练的本地 RL 权重
.\science-bot.cmd -Backend offline
```

运行说明、训练与复现、接口、原始结果、限制和逐项验收见：

- [交付说明](RUT_Science/delivery/README_运行与复现.md)
- [验收结果](RUT_Science/delivery/verification.json)
- [研究评测](RUT_Science/delivery/evaluation/summary.json)
- [实际交付与研究结论](RUT_Science/delivery/实际交付与研究结果.md)
- [终端预览](RUT_Science/delivery/science_bot_terminal.svg)

原规划保留为研究协议；本文件及机器可读验收记录描述实际交付范围，不将计划中的目标写成已有实验结论。

本轮产品验收通过，139 项测试通过；正式训练 280,000 个 PPO transitions。研究结论为负结果：BC＋PPO 与强规则在小规模留出样本中成功率持平，但计算消耗更高。从零 PPO 五种子平均成功率约 90.3%。部署权重只按开发集选择，未按测试结果更换。
