# RUT-Science / science Bot

**研究接口上线更新**：G2.2/G2.3/G2.4已接入现有终端与HTTP消息接口，输入 `/research` 查看；`/doe demo`、显式DOE协议验收与冻结策略开发模拟可用。[使用说明](docs/Science_Bot_研究接口上线_zh.md)。下面未接入时的阶段说明保留历史范围。

**G2.4研究更新**：[DOE协议与统一验收](docs/Science_Bot_G2_4_DOE协议与统一验收_zh.md) 已交付三种有界设计与42条专家待审记录。没有新增线上DOE工具或新策略训练；研究测试现为39＋37＋49＝125项。

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
