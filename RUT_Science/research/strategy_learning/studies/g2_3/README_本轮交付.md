# G2.3 研究：策略PPO与CViT模拟

原实验配置日期：2026-10-26；合并更新：2026-10-27。当前目录为 `RUT_Science/research/strategy_learning/studies/g2_3/`，与 G2.2 共用 [研究入口](../../README.md)。旧独立目录不再使用。

完整原交付说明（含算法、预算、选模、评分错误、修订试验及限制）保存在 [迁移前说明](evidence/pre_consolidation/README_本轮交付.md)。其中旧运行路径仅描述当时目录，当前命令以研究入口为准。

- 训练小型CPU决策actor-critic，96×96共享编码、23,464参数；没有训练LLM或CViT。
- 首轮任务240训练、90开发、96最终；BC、BC＋PPO、从零PPO，各三个种子21/37/59。
- 首轮正式PPO122,880 transitions；修订试验另加36,864，共159,744。单元测试小批样本不混入预算。
- 首轮原成功率均值21.88% / 24.65% / 25.00%存在隐藏停止依据问题；冻结结果原样保留。
- 按公开证据审计，BC / BC＋PPO / 从零PPO为11.81% / 6.25% / 0%，规则100%。不将过早停止解释为效率提升。
- 独立 `experiments/feedback_v2/` 在新48项最终任务上，状态聚合基线60.42%，加反馈/KL-PPO43.06%，规则100%；没有PPO优势。
- `cvit_mock/` 只检查配置、预算、确认、作业对账、OOM和恢复协议；不读取真实数据或启动GPU，`metric=null`。
- 当前迁移复测37项通过。没有学习策略推广到现有Agent。

在项目根目录运行：

```powershell
& '.\RUT_Science\.venv\Scripts\python.exe' -B 'RUT_Science/scripts/science_bot_research.py' test --study g2_3
& '.\RUT_Science\.venv\Scripts\python.exe' -B 'RUT_Science/scripts/science_bot_research.py' verify --study g2_3
```

冻结源码、模型、任务封存、轨迹、原始评测、确定性重放及修订试验保持原样。当前完整性核对同时检查首轮与修订试验的身份。历史37,271文件保护清单保留原隔离验收范围，不等于当前项目未发生目录整合。
