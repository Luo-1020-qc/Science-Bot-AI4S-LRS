# science Bot 策略学习研究

**G2.4已加入统一研究入口**：[DOE协议、统一验收与待专家校准任务库](studies/g2_4/README_本轮交付.md)。新增49项测试，三轮合计125项；当前真人专家标签0。

2026-10-27 将 G2.2、G2.3 合并到本模块。研究纳入同一项目管理、入口和完整性检查；各轮冻结任务、评分、源码和模型保持独立，便于复现并保留负结果。线上 Agent 没有加载这些策略。

| 研究 | 当前目录 | 任务 / 主要内容 | 已知结论 |
|---|---|---|---|
| [G2.2](studies/g2_2/README_本轮交付.md) | `studies/g2_2/` | 192/64/96；公开状态、标注管道、线性BC | BC 20.83%，规则100%，未达到替换要求 |
| [G2.3](studies/g2_3/README_本轮交付.md) | `studies/g2_3/` | 240/90/96；决策BC/PPO、CViT模拟、评分审计 | 严格审计BC11.81%、BC＋PPO6.25%、从零PPO0% |
| [G2.4](studies/g2_4/README_本轮交付.md) | `studies/g2_4/` | 84/42/42；DOE编译、统一评分、42条待审 | 开发42/42符合脚本预期，尚未专家校准，无新策略训练 |
| G2.3 修订试验 | `studies/g2_3/experiments/feedback_v2/` | 新48项最终任务；状态聚合、公开证据奖励、KL | 聚合基线60.42%，加PPO43.06%，规则100% |

斜线数字依次为训练/开发/最终任务数。修订试验不是首轮固定比较的替代，也不能与首轮不同测试集的百分比直接比较。规则与任务模板共享设计假设，100%不代表真实科研泛化能力。真人专家标签仍为0，待审队列不是专家标注。

## 统一使用

以下命令均在 **`LangGraph_RL_Agent` 项目根目录**运行：

```powershell
& '.\RUT_Science\.venv\Scripts\python.exe' -B 'RUT_Science/scripts/science_bot_research.py' list
& '.\RUT_Science\.venv\Scripts\python.exe' -B 'RUT_Science/scripts/science_bot_research.py' test
& '.\RUT_Science\.venv\Scripts\python.exe' -B 'RUT_Science/scripts/science_bot_research.py' verify
& '.\RUT_Science\.venv\Scripts\python.exe' -B 'RUT_Science/scripts/science_bot_research.py' status
# 只检查其中一轮
& '.\RUT_Science\.venv\Scripts\python.exe' -B 'RUT_Science/scripts/science_bot_research.py' verify --study g2_3
```

统一入口只暴露 `list/test/verify/status/demo`，不触发正式重训。每轮使用独立子进程，避免两套历史 `lab` 同名包混用；研究中的写入边界和导入限制继续生效。`demo` 是内存模拟演示，可能更新该轮演示输出，不产生真实实验结果。

若需研究旧训练脚本，在对应 study 目录查阅 `run.py --help` 与原交付说明；不要将冻结目录直接用于下一轮调参。新实验应另设版本、任务封存和选模记录。原 `snapshot/copy-fixtures/bootstrap` 不能覆盖迁移前基线。

## 结果与证据位置

| 内容 | G2.2 | G2.3 |
|---|---|---|
| 冻结身份 | `evidence/freeze.json` | `evidence/selection_freeze.json` |
| 首轮结果 | `evidence/benchmark.json` | `evidence/final_evaluation.json` |
| 后续审计 | `evidence/execution_denominators.json` | `evidence/scoring_audit.json`、`evidence/replay_manifest.json` |
| 策略与轨迹 | `models/`、`evidence/` | `models/`、`evidence/`、`experiments/feedback_v2/` |
| 当前复测 | `evidence/current_tests.log` | `evidence/current_tests.log` |
| 当前完整性 | `evidence/current_verification.json` | `evidence/current_verification.json` |

本次 39＋37 项研究测试通过。`relocation.json` 记录旧/新身份；`evidence/relocation_adaptations.json` 列出为迁移修改的入口、边界定位、说明和路径测试。被修改文件的原版在 `evidence/pre_consolidation/`；训练/奖励/选模/评测源码、任务集、模型及原始结果未改动。

当前测试写入 `current_test_outputs/`，保留原 `test_outputs/` 作为历史制品，避免重跑覆盖历史checkpoint或审阅夹具。

旧 `evidence/verification.json` 和保护清单证明当轮隔离执行时原工作区未被改动；其中绝对路径作为历史证据保留，不能用来断言本次合并后整个项目布局不变。当前迁移采用 [迁移清单及审计](../../../maintenance/consolidation_2026-10-27/README.md) 和各 study 当前校验。完整项目阶段总结见 [阶段性总结](../../../阶段性总结2_2026-10-27.md)。

## 边界与后续

保留此前要求：不连接真实工具、不调用模型API、不导入真实 CViT 训练代码、不启动GPU、不把模拟指标当成真实精度，不修改线上访谈策略。本次只验证和整合，没有新增正式训练 transitions。

下一步优先统一公开证据评分、开发选模及执行完成指标；补齐真实专家审阅和独立任务，再进行新版本训练。G3 真实领域工具接入与策略研究是不同交付，须另行定义范围。
