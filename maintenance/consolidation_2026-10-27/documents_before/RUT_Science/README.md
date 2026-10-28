# RUT-Science：可执行科研 Agent 评测最小闭环

**当前研究路线（2026-10-15）：** 直接使用 LangGraph，不依赖 OpenCode。固定 LLM 负责理解与候选生成，研究可训练 planner 的预算约束行动选择。已增加官方 Graph API 模式的真实工具执行 demo；尚未训练 RL 策略。见 [研究方向与实施方案](docs/LangGraph_RL_Research_Direction_zh.md)。

基于用户的 RUT-AgentEval 框架与苗宁等人的 RUT-Bench 论文思想重新实现。先建立可执行任务与独立评分，再将我们的规划器接入同一评测接口。**这是项目扩展原型；当前离线结果验证评测工程，不代表 LLM 性能或官方 RUT 复现。**

[方法核对与讨论](docs/Method_Review_zh.md) · [来源与字段映射](docs/source_mapping.md) · [重写的实施方案](../Markdown%20Document/Scientific_Agent_RL_Planning_Implementation_Plan.md)

**v0.5 P1/P2：** 已加入 PowerShell 科研对话入口、需求澄清、来源标注与规格确认；Darcy 支持双候选验证集选择、独立测试和有界原子故障恢复。启动：`& '.\.venv\Scripts\python.exe' -m rut_science chat --model deepseek-flash --recover`。见 [交互与恢复说明](docs/Research_Interaction_and_Recovery_zh.md) 和 [本次验收](docs/P1_P2_Delivery_2026-10-15_zh.md)。

**v0.4 结构化规划 Agent：** 已实现 LangGraph 阶段编排、`PlanSpec` 校验、节点依赖执行、持久状态、暂停恢复与未执行节点修订。PowerShell 启动：`& '.\.venv\Scripts\python.exe' -m rut_science plan run --backend api --model deepseek-flash`。完整命令、架构和边界见 [规划 Agent 使用说明](docs/Structured_Planning_Agent_zh.md)。

当前核查与后续优先级见 [2026-10-13 项目进展清单](docs/Project_Progress_2026-10-13_zh.md)。

**v0.3 新交付：** 精确工具参数枚举/边界、可信宿主确认的 `ResearchSpec` 与写入一致性检查，以及基于本地公开 Darcy MAT 数据的 CPU 科研工作流。53 项测试通过；规则控制器和 DeepSeek Flash 均实际完成 Darcy 训练、独立封存测试和报告，测试平均相对 L2 为 0.1250051181。实现、实例、证据与复跑命令见 [研究规格与 Darcy 工作流](docs/ResearchSpec_Darcy_Workflow_zh.md)。

**v0.3.1 配置更新：** 科研基准、Darcy、LangGraph Demo 与核验脚本统一默认读取项目级 `API_key_Agent.json`；58 项科研项目测试及 3 项 Demo 配置测试通过，真实 API 单请求确认通过。见 [配置迁移与检查记录](docs/API_Config_Unification_zh.md)。

v0.2 已支持本地凭据配置、真实模型调用、逐请求用量记录、全运行请求/token 准入上限及断点恢复。本轮接入条件与评分口径见 [真实模型评测协议](docs/Live_Evaluation_Protocol_2026-10-13.md)。

首轮真实评测已完成：单任务 9 个实例 + 三种策略的完整开发集合 135 个实例。结果、失败分析和下一步调整见 [真实 API 评测结果](docs/Live_API_Results_2026-10-13_zh.md)。

## 运行

Python 3.10+；离线核心仅使用标准库。无需安装 LangGraph、科学计算包或模型 SDK。

Darcy 扩展需要 NumPy/SciPy，可用 `pip install -e '.[darcy]'` 或 `pip install -r requirements-darcy.lock.txt`。从本项目目录运行 `python -m rut_science darcy prepare` 准备数据，再以 `darcy run` 执行、`darcy verify` 核验。源 MAT 默认位于 `../../MasterThesis_Project/train_data/Darcy_exp_data`；首次准备直接读取源文件，不下载或改写原实验数据。

在 PowerShell 中：

```powershell
Set-Location 'D:\Python Files\CityU_Project\CityU_Hackathon_AI4S\LangGraph_RL_Agent\RUT_Science'

# 本机已有可用 Python；首次为本项目建立独立虚拟环境。
& '..\..\.python\cpython-3.12.14-windows-x86_64-none\python.exe' -m venv .venv
& '.\.venv\Scripts\python.exe' -m unittest discover -s tests -v
& '.\.venv\Scripts\python.exe' -m rut_science validate --output outputs/validation_new
& '.\.venv\Scripts\python.exe' -m rut_science run --seeds 0 1 2 --output outputs/run_new
```

换机器时用已有 Python 建立 `.venv`；从项目根目录运行 `python -m rut_science` 即可。需要安装命令行入口时可选 `python -m pip install -e .`。输出目录须新建或为空，以保留旧实验结果。

## 这次已经做了什么

- 一个状态化 Scientific ML 环境：3 份合成数据、数据检查、固定三路划分、真实训练、一次封存测试和溯源报告。
- 5 个基础任务 × 7 种行为 = 35 个严格配对的两轮对话；另有 10 个无后续答案的澄清样本。
- Gold 轨迹重放、真实状态差异、参数和对象绑定、节点依赖、科学有效性检查。
- 每个 Agent/任务/行为/种子恢复初始状态；逐轮投递消息、步数与时间上限、保留失败尝试。
- 执行成功率、终态诊断、配对绝对 Gap、按根任务的 bootstrap 和 R1a/R1b/R2/R3/R4 归因。
- HTTP JSON 模型适配器；v0.1 使用模拟响应测试，v0.2 已完成 Kimi 单任务真实接口试验。

已验证的离线运行在 [outputs/demo_verified/report.md](outputs/demo_verified/report.md)。3 个控制器 × 3 个种子 × 45 个实例 = 405 次 episode，其中 315 次配对执行、90 次响应型测试。种子只标记重复运行；确定性控制器的重复不增加独立证据。

v0.1 的 30 项测试及工具状态校验记录见 [verification.json](outputs/demo_verified/verification.json)。v0.2 已通过 38 项自动测试，覆盖凭据兼容读取、预算、恢复、双语澄清与真实请求格式。

`rule_latest` 只解析最后一轮请求，`rule_context` 从完整用户历史恢复协议，`rule_dag` 加入显式静态依赖日程。它们都是工程控制器。前者在省略当前轮参数的变体失败是人为设计的机制检查，不是发现了新的模型排名；后两者相同的高成功率也不证明 DAG 带来增益。

## 如何评分

`execution_success = action_coverage AND logical_compliance AND state_verification`，并要求对话正常结束。

覆盖检查匹配工具、参数和来自真实工具结果的 ID；失败调用不覆盖 Gold 节点。逻辑检查保留前置错误、非法工具/参数和禁止动作，即使后续修复也不会抹去。状态检查核对预期 delta，并独立检查数据划分、拟合行、测试封存、数值重算和报告来源。

`state_only_success_extension` 用于诊断终态正确但轨迹失败的样本，不能替代主指标。响应型样本只计算 `interaction_success`，不会加入执行 SR 与 Gap。服务/API 异常单独计数并从评分分母排除；步数/时间耗尽属于执行失败。

`IH`、`TD`、货币成本当前为 `null`。前两者未运行独立 Judge，后者未配置价格；API token 数记录为用量。v0.2 的澄清 rubric 支持有限的中英文同义表达，仍需逐例语义复核。

## 输出与证据

```text
outputs/<run>/
  manifest.json              # 代码、数据、工具、提示哈希与运行配置
  validation.json            # Oracle / 环境 / 配对 schema 检查
  benchmark/tasks.json       # Gold、断言、依赖、预期实际 delta
  benchmark/dialogues.json   # 核心与响应型对话
  benchmark/initial_state.json
  episodes/*.json            # 单次运行、完整状态与评分
  trajectories/*.jsonl       # 每步工具结果、状态前后、错误和延迟
  summary.json
  report.md
```

这些文件属于评测端，含 Gold、测试数据与封存结果，不能给运行中的 Agent 当工具输入。Agent 实际只接收系统提示、工具 schema、已到达的用户轮次与工具返回值。

用户报告保存在单次 episode 的 `episode.final_state.reports`。`write_report` 在运行中只返回 ID，不反馈 MAE；没有可用于循环调参的测试分数接口。

## 接真实模型

全部真实 API 入口默认读取项目级 `CityU_Hackathon_AI4S/API_key_Agent.json`，绝对路径根据代码位置确定，不受工作目录影响。密钥和端点来自同一配置，不再回退到环境变量或其他旧凭据文件。用账户实际可调用的模型名执行：

```powershell
& '.\.venv\Scripts\python.exe' -m rut_science run `
  --agents api_direct api_clarify api_dag --task science_001 --seeds 0 `
  --model deepseek-flash `
  --output outputs/live_model_trial
```

也可以显式指定 `--api-config '../API_key_Agent.json'`。读取器支持 JSON 对象/数组、相邻对象，以及字符串之外的末尾逗号；不会修改或复制密钥文件。`--profile` 从 0 开始，`--credential-field` 可选择同一服务的其他凭据字段。当前文件没有默认模型，因此仍须传入 `--model`。

```powershell
& '.\.venv\Scripts\python.exe' -m rut_science run `
  --agents api_direct --api-config '../API_key_Agent.json' --profile 0 `
  --model deepseek-flash --task science_001 --seeds 0 `
  --max-seconds 180 --max-requests 100 --max-run-tokens 250000 `
  --output outputs/live_trial_new
```

恢复中断运行时重复原命令并添加 `--resume`；相同配置与代码下跳过已保存的完整实例。未完成实例会恢复干净环境重新运行，已保存的失败不会自动重跑。预算账本保留之前请求及未知用量预留。

这是会实际调用模型服务的命令。默认 `run` 仅执行离线控制器。API 使用 JSON action 协议，工具仍在本地执行；实际模型标识和 token 用量保存在 episode 中，不承诺跨调用逐位复现。上下文权限与硬评分不随策略变更。

第一次建议只跑一个任务的 9 个实例确认接口，然后完整跑 35 个配对与 10 个响应型样本。`api_direct / api_clarify / api_dag` 共享模型和工具，只改变附加策略提示。v0.2 以 `--max-requests`、`--max-run-tokens` 和 `--max-context-bytes` 控制全运行准入，并记录实际 token 用量；未配置供应商单价表，不能将 token 准入上限当成账单金额保证。

Moonshot K2.6 请求固定非思考模式并采用供应商默认采样参数；三策略相同。每次无凭据请求体、模型标识和用量保存在 `episode.model_calls`，逐请求账本见 `budget.json`。

该 Moonshot 说明对应历史运行；当前默认配置为 DeepSeek。v0.3.1 的文件配置测试使用同名临时 JSON 与假密钥，网络 mock 不消耗用户额度。历史产物与源码快照保留原版本，凭据入口迁移不会改写既有实验记录。

## 代码入口与后续范围

| 文件 | 职责 |
|---|---|
| `contracts.py` | 任务/对话/工具动作契约；Agent 接口 |
| `environment.py` | 私有数据与状态、工具实现、资源限制 |
| `benchmark.py` | 任务 Gold、七类对话与响应型样本 |
| `validation.py` | Oracle 重放、字段与泄漏验证 |
| `runtime.py` | 对话推进与工具执行日志 |
| `evaluator.py` | 独立硬评分、科学检查与失败归因 |
| `agents.py` | 离线控制器与 HTTP 模型适配器 |
| `analysis.py` / `cli.py` | 配对分析、结果产物与运行入口 |
| `configuration.py` / `budget.py` | 本地凭据读取、运行准入和用量账本 |
| `clarification.py` | 固定的双语开发集澄清规则 |

OpenCode/MCP、SciencePal、真实 Matbench 或论文复现、第二种环境、动态目标、技能检索、学习策略和 LLM Judge 都是后续里程碑。当前状态容器没有运行任意代码的能力，也不是 OS 级安全隔离。
