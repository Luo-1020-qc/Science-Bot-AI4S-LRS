# G2.2 / G2.3 研究合并记录

日期：2026-10-27。授权范围：用户要求检查并合拢两轮研究、移除两个旧测试文件夹、保持项目一致性并编写完整阶段总结。

当前模块为 [RUT_Science/research/strategy_learning](../../RUT_Science/research/strategy_learning/README.md)。原 `G2_2_Test_Workspace` 与 `G2_3_Test_Workspace` 的内容已迁入 `studies/g2_2`、`studies/g2_3`，旧根目录移除。研究过程继续禁止真实工具、模型API和GPU作业，不推广研究策略。

| 检查 | 结果 / 证据 |
|---|---|
| 原件迁移 | G2.2共70文件、30,574,765字节；G2.3共447文件、176,804,127字节；首次复制逐字节哈希一致 |
| 冻结制品 | 原任务、权重、轨迹、训练/奖励/评测/选模源码和结果保持哈希一致 |
| 必要适配 | 入口、项目根定位、G2.3前轮定位和路径测试、当前说明；清单与原文件分别保留 |
| 研究复测 | G2.2 39项、G2.3 37项通过；各轮 `evidence/current_tests.log` |
| 应用保护 | 核心运行源码、数据、模型、提示词、论文资料、密钥配置和两个启动文件哈希不变 |
| 文档 | 当前README、交接、交付、工作区与方案导航统一，历史快照保留 |
| 当前验收 | [verification.json](verification.json)、[迁移审计](migration_audit.json)、每轮 `evidence/current_verification.json` |

关键记录：

- [migration.json](migration.json)：迁移前517个研究文件的大小与SHA-256，原/新路径和应用保护清单；只记录配置哈希，不记录密钥内容。
- [migration_audit.json](migration_audit.json)：原研究内容、应用保护清单和旧目录状态。删除前另核对源目录仍与基线一致。
- 各study的 `relocation.json`：历史根路径和当前身份。
- 各study的 `evidence/relocation_adaptations.json`：必要修改和原/新哈希；`evidence/pre_consolidation/`保留原版。
- [documents_before](documents_before/)：当前导航更新前的文档备份。
- [阶段总结](../../阶段性总结2_2026-10-27.md)：项目全部阶段、架构、结果、限制和后续验收。

旧 `protected_before/after`、`verification.json` 和模型记录中的绝对路径继续作为原隔离实验的历史证据，不改写为新实验。当前检查不冒用旧“整个项目未变化”结论，也没有重跑历史真实实验。

维护脚本职责：`consolidate.py copy`仅进行首次复制，已有清单时拒绝覆盖；`audit`检查迁移及应用完整性。`finalize.py prepare`在旧目录删除前保存显式适配清单与原版；`check`检查当前文档链接、Python语法及研究验收。删除由PowerShell在验证目标是项目根下两个指定目录后单独执行，脚本不递归删除其他路径。

复核当前交付（在项目根目录）：

```powershell
& '.\RUT_Science\.venv\Scripts\python.exe' -B 'RUT_Science/scripts/science_bot_research.py' test
& '.\RUT_Science\.venv\Scripts\python.exe' -B 'RUT_Science/scripts/science_bot_research.py' verify
& '.\RUT_Science\.venv\Scripts\python.exe' -B 'maintenance/consolidation_2026-10-27/consolidate.py' audit
& '.\RUT_Science\.venv\Scripts\python.exe' -B 'maintenance/consolidation_2026-10-27/finalize.py' check
```

这是制品完整性与隔离研究验收，不是新增真实科研基准，也不主张学习策略优于规则。

完整性检查还发现历史单元测试会重写 `test_outputs/checkpoint_roundtrip.pt`。迁移时恢复了历史原件，并将当前checkpoint与审阅测试输出改写到 `current_test_outputs/`，随后重跑76项测试。测试逻辑和冻结训练协议保持原样。
