# G2.2 研究：决策环境、标注管道与BC

原交付日期：2026-10-26；合并更新：2026-10-27。当前目录为 `RUT_Science/research/strategy_learning/studies/g2_2/`，与 G2.3 共用 [研究入口](../../README.md)。旧独立目录不再使用。

完整原交付说明（含设计、统计口径、标注命令及失败分析）保存在 [迁移前说明](evidence/pre_consolidation/README_本轮交付.md)。其中旧运行路径仅描述当时目录，当前命令以研究入口为准。

- 合成任务：192训练、64开发、96最终留出；16类基础情形、8种留出组合。
- 公开观察与安全mask：错误方法、重复询问、过早停止仍可被选；权限和版本确认由宿主强制执行。
- 标注：72条训练决策待审，导入核对上下文哈希、身份、合法动作和审阅来源。真人专家标签0。
- 三个BC种子21/37/59，每个使用1133条脚本参考决策；不是LLM微调。
- 冻结结果：规则100%；顺序槽位消融25%；合法随机17.71%；三个BC均20.83%。BC不适合替换规则。
- 模拟执行无真实计算，`metric=null`。当前迁移复测39项通过。

在项目根目录运行：

```powershell
& '.\RUT_Science\.venv\Scripts\python.exe' -B 'RUT_Science/scripts/science_bot_research.py' test --study g2_2
& '.\RUT_Science\.venv\Scripts\python.exe' -B 'RUT_Science/scripts/science_bot_research.py' verify --study g2_2
```

本轮制品保留：`bank/`、`models/`、`review/`、`fixtures/`、`lab/`、`tests/` 和 `evidence/`。原评分、任务与权重未重写；新增 `current_tests.log/current_verification.json` 区分当前复测与历史验收。历史37,190文件保护清单仅描述原隔离实验，不作为本次迁移后布局证明。
