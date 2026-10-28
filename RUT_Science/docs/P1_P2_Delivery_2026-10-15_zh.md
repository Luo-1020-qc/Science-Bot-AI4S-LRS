# P1 / P2 交付与验收记录

2026-10-15，v0.5.0。交付范围是 PowerShell 科研交互入口，以及两个固定候选的验证集选择和有界原子恢复。完整契约和命令见 [使用说明](Research_Interaction_and_Recovery_zh.md)。历史 `阶段性总结1.md` 和旧实验记录保留。

## 完成内容

| 工作 | 已实现内容 |
|---|---|
| P1 对话入口 | `python -m rut_science chat`、`Run-ResearchAgent.ps1`；API 提取或有限离线控制解析 |
| 需求整理 | 数据/目标缺失追问，规格与约束校验，来源和默认值展示 |
| 确认边界 | 终端确认绑定草案、ResearchSpec 和完整执行策略；模型不能确认自己；修改后撤销原授权 |
| 会话持久化 | 原始轮次、草案、确认记录、模型请求与共享预算、子执行目录、冻结代码 |
| P2 数据分支 | 同一划分拟合 ridge/mean 两个候选，`select_model` 按验证集选择，LangGraph 记录分支，仅选中者测试一次 |
| P2 执行恢复 | 白名单原子临时故障，同节点同参数有界重试，plan v2 + 父哈希，保留失败和成功证据 |
| 评分与审计 | 原严格评分和恢复扩展分开；独立 SciPy 数值参考、状态/计划链、来源/确认和请求账本核验 |

对应实现：`research_chat.py`、`intake_contract.py`、`chat_cli.py`、`adaptive_plan_spec.py`、`adaptive_workflow.py`、`recovery.py`、`planning_agent.py`、`planning_evaluation.py`、`chat_verification.py`。

## 已通过的验证

- **108 项自动测试通过**：保留原 80 项，新增 28 项；覆盖确认权限、来源和旧哈希、修改撤销授权、准备模式、预算共享、两条数据分支、封存测试、局部恢复与拒绝边界。
- 新增完整 mock API 对话→确认→计划→Darcy 执行→故障恢复→共享账本核验，以及保存恢复决策后中断、不重复消耗重试预算的测试；这些测试不消耗真实 API 额度。
- `pip check` 通过。
- Windows PowerShell 脚本实际启动，新进程恢复成功。合成对话工作流在三步后暂停，恢复后总计六次工具调用，没有重复已完成步骤。
- 真实公开 Darcy 数值数据完成两个候选的实际拟合、验证集选择、一次封存测试和独立科学验收。离线控制器生成计划，科研工具执行真实数值计算。
- 故障运行在岭回归拟合前注入一次明确标注的临时故障，生成 plan v2 后重试；在四个成功节点边界暂停，新进程恢复后总计九次尝试、两次成功拟合和一次封存测试。严格评分保留失败，恢复扩展通过。
- 两条分支都经过自动测试；均值分支使用常数场测试 fixture 触发严格相等的择优规则，不能称作真实 Darcy 数据上均值胜出。

Darcy 数值结果：

| 候选/最终指标 | 数值 |
|---|---:|
| ridge_field 验证集平均相对 L2 | 0.11849132989591322 |
| mean_field 验证集平均相对 L2 | 0.25685466921394545 |
| 选中方法 | ridge_field |
| 选中模型独立测试平均相对 L2 | 0.12500511806556025 |

这些结果验证候选选择、执行与审计协议，没有新增模型精度贡献；测试数值与此前固定岭回归工作流相同。

## 真实 API 当前未通过验收

本轮全部真实模型尝试均使用项目指定的 `API_key_Agent.json` 和 `deepseek-flash`，未改写凭据文件。三个对话运行分别尝试两次提取，共六次请求；前两轮单次等待 20 秒，最后一轮最多 55 秒，均发生传输 `TimeoutError`。最后一次单请求连接诊断也失败。没有形成可确认规格，因此没有生成科研执行子目录。

HTTPS 根路径探测得到服务端 401，表明该探测获得 HTTP 响应；它不代表带凭据的模型 POST 已成功。默认权限与提升网络权限下的模型尝试均超时，当前无法进一步确定是网络中间环节还是服务端处理问题。没有将失败归因于模型科研能力。

超时响应没有供应商实际 token 用量，账本保留未知用量预留，不能假定费用为零。没有自动反复重发超时请求。生产路径已通过 mock 的真实请求格式、凭据入口和共享预算测试；**P1/P2 的真实 DeepSeek 端到端运行仍未验证**，不能用旧版 API 成功记录代替本轮验收。

接口恢复后可直接复跑，无需修改实现：

```powershell
& '.\.venv\Scripts\python.exe' -m rut_science chat --model deepseek-flash --recover
```

本地可立即演示真实 Darcy 工具闭环：

```powershell
powershell -NoProfile -ExecutionPolicy RemoteSigned -File .\scripts\Run-ResearchAgent.ps1 `
  -Backend offline -Recover -InputFile examples/research_conversation_zh.json
```

脚本输入的确认均记录为 `scripted_operator`，不冒充真人多轮交互评测。交互启动后用户自己输入确认时才记录为 `terminal_user`。

## 证据入口

- [Darcy 对话正常运行](../outputs/chat_darcy_offline_release_2026-10-15_v050/execution_001/report.md)、[需求与确认对话](../outputs/chat_darcy_offline_release_2026-10-15_v050/conversation.json)
- [Darcy 故障恢复报告](../outputs/plan_p1p2_recovery_release_2026-10-15_v050/report.md)、[原始失败与重试轨迹](../outputs/plan_p1p2_recovery_release_2026-10-15_v050/trajectory.jsonl)、[计划版本与分支历史](../outputs/plan_p1p2_recovery_release_2026-10-15_v050/planning_history.json)
- [PowerShell 会话恢复审计](../outputs/chat_ps_offline_release_2026-10-15_v050/verification.json)
- [API 初次尝试账本](../outputs/chat_api_p1p2_2026-10-15_v050/budget.json)、[提升网络权限后的尝试](../outputs/chat_api_p1p2_network_2026-10-15_v050/budget.json)、[55 秒等待的最终尝试](../outputs/chat_api_p1p2_final_2026-10-15_v050/budget.json)、[单请求诊断](../outputs/agent_api_config_check_p1p2_2026-10-15.json)
- [交付总审计](../outputs/p1p2_delivery_verification_v050.json)

核验命令：`python -m scripts.verify_p1p2_delivery`。该命令不调用模型；其 `status` 表示离线工程和真实数值后端通过，`api_end_to_end_status` 单独显示真实接口尚未通过。不要把二者混为“全链路 API 已验收”。

下一阶段优先冻结多轮任务、故障类型和预算，构建普通工具循环与结构化规划的同模型配对对照。随后扩展更多候选/工具和留出任务；当前没有实现通用任意参数重规划、运行中原位修改目标、RL 或 OpenCode/MCP 集成。
