"""Update current navigation; historical reports and frozen research are retained."""
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[2]
HUB = "RUT_Science/research/strategy_learning"
DOCUMENTS = {
"README.md": r'''# science Bot 项目工作区

截至 **2026-10-27**，本目录是 science Bot 的统一项目根目录。G1、G2、G2.1 已进入应用；G2.2、G2.3 的任务库、策略训练、CViT 模拟、审计和负结果已统一归档到研究模块。两个原测试工作区已合并，不再作为入口。

- [完整阶段总结：历次工作、架构、结果与下一步](阶段性总结2_2026-10-27.md)
- [交接入口](science_Bot_交接.md) · [运行与交付入口](science_Bot_交付.md)
- [G2.2 / G2.3 统一研究入口](RUT_Science/research/strategy_learning/README.md)

```text
LangGraph_RL_Agent/
├── science-bot.cmd / Start-ScienceBot.ps1  # 原应用入口
├── API_key_Agent.json                     # 本地模型配置，勿提交或打包
├── Reference_Paper/                       # 论文与方法笔记
├── RUT_Science/
│   ├── rut_science/                       # 应用、工具、评测及原数值策略
│   ├── data/ · models/ · prompts/         # 应用数据、模型及提示词
│   ├── tests/ · scripts/ · docs/          # 测试、脚本及说明
│   ├── delivery/ · outputs/               # 历次交付与运行证据
│   └── research/strategy_learning/
│       ├── run.py · audit.py · README.md  # 研究统一入口和完整性检查
│       ├── studies/g2_2/                  # 标注、线性BC及冻结基准
│       ├── studies/g2_3/                  # CPU策略PPO、CViT模拟与修订实验
│       └── integration_results/           # 当前合并验收
└── maintenance/
    ├── organization_2026-10-21/           # 早期工作区与ZIP整理记录
    └── consolidation_2026-10-27/          # 本次迁移清单、原文档及哈希核对
```

在本目录的 PowerShell 中启动应用：

```powershell
.\science-bot.cmd
.\science-bot.cmd -Backend offline
.\science-bot.cmd -Workspace "D:\my-project"
```

默认 `general_v1` 不自动创建 Darcy 实验。它支持问答、显式项目文件分析、受限表格实验设计和多轮访谈；绑定项目须已存在。`-Backend offline` 使用离线规则，不表示通用访谈已经启用 PPO。旧数值引擎仍作为显式场景适配器保留。

研究检查单独运行，不接入真实工具或线上策略。在本目录执行：

```powershell
& '.\RUT_Science\.venv\Scripts\python.exe' -B 'RUT_Science/scripts/science_bot_research.py' list
& '.\RUT_Science\.venv\Scripts\python.exe' -B 'RUT_Science/scripts/science_bot_research.py' test
& '.\RUT_Science\.venv\Scripts\python.exe' -B 'RUT_Science/scripts/science_bot_research.py' verify
```

本次迁移复测 G2.2 **39** 项、G2.3 **37** 项，共 **76 项通过**。冻结训练源码、模型、任务集和原始评测保留；只适配目录、入口、当前校验及说明。没有新增模型 API、真实工具或 GPU 作业，没有重新训练或推广策略，没有新增 ZIP。迁移详情见 [维护记录](maintenance/consolidation_2026-10-27/README.md)。

当前学习结果尚不支持替换规则：G2.2 BC 20.83% 对规则 100%；G2.3 首轮经公开证据审计后，BC / BC＋PPO / 从零PPO 为 11.81% / 6.25% / 0%。修订实验也未显示 PPO 优势。上述为各自合成任务集上的指标，不能外推为真实科研表现。

使用说明：[工作区设置](RUT_Science/docs/Science_Bot_Workspace_zh.md)、[G1](RUT_Science/docs/Science_Bot_G1_通用入口_zh.md)、[G2](RUT_Science/docs/Science_Bot_G2_表格与实验设计_zh.md)、[G2.1](RUT_Science/docs/Science_Bot_G2_1_设计访谈与学习环境_zh.md)、[模型输出](RUT_Science/docs/Science_Bot_Model_Output_zh.md)。历史报告中的旧日期、旧路径和“当时未训练PPO”保留其原有时间范围，以本页和阶段总结描述当前状态。

本地 `.venv` 依赖本机 Python 3.12；换机器须按项目依赖重建。密钥只由本地配置读取，不复制到研究模块。
''',
"science_Bot_交接.md": r'''# science Bot 当前交接入口

更新日期：**2026-10-27**。

[阶段总结](阶段性总结2_2026-10-27.md) 是本次完整交接：覆盖评测原型、Darcy、LangGraph、数值策略训练、工作区整理、通用化 G1/G2/G2.1，以及 G2.2/G2.3 策略研究。

当前应用仍由 `science-bot.cmd` 启动，通用访谈默认使用规则。已实现项目问答、受限 CSV 设计与执行、持久访谈、确认与恢复。CViT 真实训练、通用领域插件和学习策略上线尚未交付。

G2.2、G2.3 已合并到 [统一研究模块](RUT_Science/research/strategy_learning/README.md)，原两个独立测试文件夹已移除。两轮保留独立的冻结协议、任务、源码、模型、轨迹及负结果，共享研究入口、当前完整性检查和结果索引。它们不注册为应用真实工具，不加载到线上访谈。

本次检查：两轮研究 76 项测试通过；冻结制品与迁移前一致；应用核心代码、数据、模型、提示词、论文资料、配置和启动入口不变。历史“原项目未变化”清单仅证明当轮隔离实验，当前合并使用新的哈希验收，见 [维护记录](maintenance/consolidation_2026-10-27/README.md)。

建议下一步先统一严格评分与开发选模，再取得真正的专家审阅、建立新盲测与跨任务验证。暂不继续堆叠 PPO 预算，也不连接真实 CViT 工具；具体验收条件见阶段总结。

历史与使用资料：

- [2026-10-21 交接快照](RUT_Science/docs/Science_Bot_项目交接_2026-10-21.md)
- [G1 通用入口](RUT_Science/docs/Science_Bot_G1_通用入口_zh.md)、[G2 表格实验](RUT_Science/docs/Science_Bot_G2_表格与实验设计_zh.md)、[G2.1 设计访谈](RUT_Science/docs/Science_Bot_G2_1_设计访谈与学习环境_zh.md)
- [原数值RL研究结果](RUT_Science/delivery/实际交付与研究结果.md)
- [G2.2 当前研究说明](RUT_Science/research/strategy_learning/studies/g2_2/README_本轮交付.md)、[G2.3 当前研究说明](RUT_Science/research/strategy_learning/studies/g2_3/README_本轮交付.md)

旧报告是当时的交付证据，不作为当前完成状态清单。模型输出展示、工作区绑定和旧会话兼容继续沿用既有实现。
''',
"science_Bot_交付.md": r'''# science Bot 运行与交付入口

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
''',
"RUT_Science/README.md": r'''# RUT-Science / science Bot

当前说明更新于 **2026-10-27**。项目统一根目录是上一级 `LangGraph_RL_Agent`，当前完整状态见 [阶段总结](../阶段性总结2_2026-10-27.md) 和 [项目入口](../README.md)。

本工程从 RUT 思路出发，建立可执行科研 Agent 评测，随后加入 LangGraph 编排、Darcy 数值工作流、预算约束策略研究，并发展为支持多轮实验设计的通用入口。这是本地扩展研究，不是官方 RUT 复现。

当前应用具备：

- `general_v1` 意图路由、显式项目文件问答与原生工具调用适配。
- 三类受限表格实验：独立两组 Welch、配对 t、固定划分的 mean/OLS 预测比较。
- 多轮访谈、来源与冲突记录、设计草案、宿主校验、确认执行和跨进程恢复。
- 通过适配器保留 generated / Darcy 数值引擎、原固定行动 BC/PPO 研究及历史评测。

G2.2/G2.3 位于 [research/strategy_learning](research/strategy_learning/README.md)，包含合成任务库、审阅管道、决策 BC/PPO、CViT 模拟和评分审计。研究尚未显示学习策略优于规则；默认通用策略仍为规则。这里训练的是小型决策网络，不是大模型或 CViT。

从上一级项目目录启动：

```powershell
.\science-bot.cmd -Backend offline
.\science-bot.cmd -Workspace "D:\my-project"
```

在本 `RUT_Science` 目录可直接运行：

```powershell
& '.\.venv\Scripts\python.exe' -B -m rut_science science --backend offline
& '.\.venv\Scripts\python.exe' -B scripts/science_bot_research.py list
& '.\.venv\Scripts\python.exe' -B scripts/science_bot_research.py test
& '.\.venv\Scripts\python.exe' -B scripts/science_bot_research.py verify
```

已有虚拟环境基于 Python 3.12。完整应用依赖 LangGraph 及数值扩展，G2.3 研究还使用 NumPy/PyTorch；“离线核心只需标准库”仅适用于早期评测原型。换机器请按 [pyproject.toml](pyproject.toml) 和锁定依赖重建环境，不复制本机虚拟环境。

模型配置默认读取上一级 `LangGraph_RL_Agent/API_key_Agent.json`，不从研究目录复制密钥。工作区通过 `-Workspace` 绑定，状态位置及读取边界见 [工作区文档](docs/Science_Bot_Workspace_zh.md)。真实 API 和现有数值工具在此前交付中已验证，本次研究合并没有调用它们。

资料索引：

- 当前：[G1](docs/Science_Bot_G1_通用入口_zh.md)、[G2](docs/Science_Bot_G2_表格与实验设计_zh.md)、[G2.1](docs/Science_Bot_G2_1_设计访谈与学习环境_zh.md)、[模型输出](docs/Science_Bot_Model_Output_zh.md)。
- 历史方法：[方法核对](docs/Method_Review_zh.md)、[来源映射](docs/source_mapping.md)、[真实API评测](docs/Live_API_Results_2026-10-13_zh.md)、[Darcy](docs/ResearchSpec_Darcy_Workflow_zh.md)、[结构化规划](docs/Structured_Planning_Agent_zh.md)。
- 研究：[数值RL v1](delivery/实际交付与研究结果.md)、[G2.2/G2.3 统一研究](research/strategy_learning/README.md)。
- 证据：`delivery/` 保留历次交付，`outputs/` 保留历史运行，当前迁移记录在 [maintenance](../maintenance/consolidation_2026-10-27/README.md)。

早期离线405回合和真实模型144回合属于原任务协议；各阶段样本和成功率不能混成同一基准。历史报告中的路径、时间和当时状态继续原样保存。
''',
HUB+"/README.md": r'''# science Bot 策略学习研究

2026-10-27 将 G2.2、G2.3 合并到本模块。研究纳入同一项目管理、入口和完整性检查；各轮冻结任务、评分、源码和模型保持独立，便于复现并保留负结果。线上 Agent 没有加载这些策略。

| 研究 | 当前目录 | 任务 / 主要内容 | 已知结论 |
|---|---|---|---|
| [G2.2](studies/g2_2/README_本轮交付.md) | `studies/g2_2/` | 192/64/96；公开状态、标注管道、线性BC | BC 20.83%，规则100%，未达到替换要求 |
| [G2.3](studies/g2_3/README_本轮交付.md) | `studies/g2_3/` | 240/90/96；决策BC/PPO、CViT模拟、评分审计 | 严格审计BC11.81%、BC＋PPO6.25%、从零PPO0% |
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
''',
HUB+"/studies/g2_2/README_本轮交付.md": r'''# G2.2 研究：决策环境、标注管道与BC

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
''',
HUB+"/studies/g2_3/README_本轮交付.md": r'''# G2.3 研究：策略PPO与CViT模拟

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
''',
}


if __name__ == "__main__":
    for relative, content in DOCUMENTS.items():
        path = ROOT/relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    notes = {
        "RUT_Science/docs/Science_Bot_Workspace_zh.md": "2026-10-27 当前状态：G2.2/G2.3 已合并至 [统一研究模块](../research/strategy_learning/README.md)。该模块不作为对话工作区注册工具，也不改变 `-Workspace`、`.sciencebot/workspace.json` 或默认规则策略。当前完整能力与限制见 [阶段总结](../../阶段性总结2_2026-10-27.md)。下文保留工作区用法。",
        "RUT_Science/docs/Science_Bot_General_改造方案_zh.md": "2026-10-27 当前状态：G1/G2/G2.1 已实现；G2.2/G2.3 已完成隔离策略研究并 [统一归档](../research/strategy_learning/README.md)，小型决策PPO已实际训练但未上线，未显示优于规则。G3真实CViT工具与G4完整跨领域接入仍未实现。下文为2026-10-21原方案快照，不能把当时的‘尚未实现’当成当前状态。完整进展见 [阶段总结](../../阶段性总结2_2026-10-27.md)。",
        "RUT_Science/docs/Science_Bot_项目交接_2026-10-21.md": "2026-10-27 交接补充：当前入口见 [最新交接](../../science_Bot_交接.md) 与 [阶段总结](../../阶段性总结2_2026-10-27.md)。G1/G2/G2.1已进入应用，G2.2/G2.3研究已 [合并](../research/strategy_learning/README.md)，真实CViT工具仍未接入，通用访谈继续默认规则。本文是2026-10-21历史快照，保留当时路径、统计和待办。",
    }
    for relative, note in notes.items():
        path = ROOT/relative
        before = path.read_text(encoding="utf-8")
        if note in before:
            continue
        backup = Path(__file__).resolve().parent/"documents_before"/relative
        if not backup.exists():
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, backup)
        title, rest = before.split("\n", 1)
        path.write_text(title+"\n\n> "+note+"\n"+rest, encoding="utf-8")
    print("Updated current documentation and retained historical snapshots")
