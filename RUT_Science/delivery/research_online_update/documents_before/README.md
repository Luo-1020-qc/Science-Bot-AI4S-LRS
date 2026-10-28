# science Bot 项目工作区

**G2.4已交付（2026-10-27）**：[DOE协议与统一验收](RUT_Science/delivery/g2_4_update/README_本轮交付.md) 已纳入研究入口，覆盖三种有界DOE设计、来源校验、功效、设计步骤与待审任务库。G2.4的49项测试通过，三轮研究合计125项；真人专家标签仍为0，线上访谈与真实工具范围不变。

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
│       ├── studies/g2_4/                  # DOE协议、验收、专家待审与封存任务
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
