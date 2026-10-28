# science Bot

新增通用项目入口：`science-bot.cmd -Workspace "D:\my-project"`，或 Python 入口 `--workspace "D:\my-project"`。支持 `/workspace`、`/files`、`/read`，会话默认保存在项目的 `.sciencebot/sessions`。完整说明见 [项目工作区](../docs/Science_Bot_Workspace_zh.md)。原始 v1 压缩包与研究结果保留，本次工作区更新的测试记录位于 `workspace_update/`。

面向受限科研实验的终端 Agent。固定 LLM 理解需求、提出注册目录内的候选并解释结果；本地学习策略选择下一行动；宿主执行真实数值工具、结算预算、保存证据并独立核验。

## 启动

在 `LangGraph_RL_Agent` 目录运行：

```powershell
.\science-bot.cmd
# 明确选择离线模式，仍加载真实训练权重
.\science-bot.cmd -Backend offline
# Darcy 数值工具
.\science-bot.cmd -Dataset darcy
```

也可在 `RUT_Science` 目录运行：

```powershell
& '.\.venv\Scripts\python.exe' -m rut_science science
& '.\.venv\Scripts\python.exe' -m rut_science science --backend offline --dataset darcy
```

默认 API 模式读取相邻项目根目录的 `API_key_Agent.json`，模型默认 `deepseek-flash`，不会读取其他历史凭据或在 API 故障时自动改用规则。默认 planner 为本地 RL，加载 `models/planner/v1/selected`，缺失或哈希不符会失败。

终端采用青色/紫色视觉、独立研究工作区、实验表、底部预算状态和实时事件。输入自然语言任务，检查展示的规格、默认质量门槛和资源，再输入 `/confirm`。默认的生成任务和 Darcy 压力场预测是当前注册任务；任意写代码和运行 shell 不属于 v1 工具域。

| 命令 | 用途 |
|---|---|
| `/help` | 命令说明 |
| `/status` | 规格、预算、确认状态、权重身份 |
| `/experiments` | 已尝试实验与实际验证误差 |
| `/confirm [hash]` | 确认当前展示的草案并执行 |
| `/pause` | 当前行动完成或对账后暂停 |
| `/resume` | 恢复已确认会话 |
| `/cancel` | 取消后续调度，不把已有实验包装成成功 |
| `/report` | 终局报告 JSON |
| `/events` | 最近事件 |
| `/clear` | 重绘入口 |
| `/exit`、Ctrl+D | 安全暂停、保存并退出 |

Ctrl+C 在输入提示处请求暂停。首版同会话串行执行；执行开始后改变任务或增加预算需创建新会话，避免把已产生证据重新解释为另一项研究。

恢复会话：

```powershell
& '.\.venv\Scripts\python.exe' -m rut_science science --resume 'outputs\science_bot\<session-id>'
```

离线自然语言入口是明确标注的有限解析器，支持 `generated`/`合成`/`Darcy`、`预算6`、`门槛0.20`。API 模式使用固定 LLM 结构化提取，并由宿主核验来源、目录和数值。

## 本地 HTTP API

```powershell
& '.\.venv\Scripts\python.exe' -m rut_science serve --host 127.0.0.1 --port 8765
```

独立本地令牌保存在 `outputs/science_bot/.local_token`，不复用模型供应商密钥。所有请求都需 Bearer 令牌；所有 POST 需要 `Idempotency-Key`。令牌不写入交付会话副本。

```powershell
$localToken = (Get-Content -LiteralPath '.\outputs\science_bot\.local_token' -Raw).Trim()
$botHeaders = @{ Authorization = "Bearer $localToken"; 'Idempotency-Key' = 'create-001' }
$session = Invoke-RestMethod 'http://127.0.0.1:8765/v1/sessions' -Method Post -Headers $botHeaders -ContentType 'application/json' -Body '{"backend":"offline","planner":"rl","spec":{"split":"demo"}}'
```

随后调用：

- `POST /v1/sessions/{id}/messages`：`{"text":"..."}`
- `POST /v1/sessions/{id}/confirm`：`{"draft_hash":"当前完整哈希"}`
- `POST /v1/sessions/{id}/resume`：启动后台执行
- `POST /v1/sessions/{id}/cancel`：停止后续调度
- `GET /v1/sessions/{id}`：公开状态
- `GET /v1/sessions/{id}/events?after=0`：按序号轮询事件
- `GET /v1/sessions/{id}/report`：终局报告

每个不同 POST 使用不同幂等键。相同键和请求返回已有结果，改变请求载荷会被拒绝。当前事件接口采用轮询，未实现 SSE。

## 实现与状态

新增实现集中在 `rut_science/science_bot/`；旧 `ResearchSpec`、固定六步/八步协议与评分语义保持。复用既有 `RunBudget`、`JSONHTTPAgent`、凭据读取、Darcy bundle 校验和跨进程会话锁。

`BudgetedEnvironment.step_action` 是 terminal、HTTP 和 Gym 的公共行动内核。公开观察采用字段白名单；实际数据、生成器参数、缓存结果表与封存评价不进入策略输入。18 个语义行动槽加 padding 到 24；候选共享评分器支持乱序，ID/哈希/路径不作为网络特征。

业务状态以原子 `environment.json` 为科研账本权威来源；`session.json` 保存交互配置；SQLite 保存 LangGraph 执行位置和确认中断。作业先预留、登记，再执行并持久化结果，最后提交证据。恢复先对账已登记结果；作业或封存评价的执行情况未知时暂停，避免盲目重复。

逻辑费用：mean=1 CU，half ridge=2，full ridge=4，诊断=1；调用前故障 fixture=0.25 调度 CU。搜索预算之外明确预留 2 CU、2 次终局工具操作、1 次解释模型调用和 4096 token 准入额度。CU 不是时间或金额；同时记录实际耗时、请求和 token。API 未报告用量时保留保守预留。

## 训练与冻结评测

主线为 BC、从零 Masked PPO、BC＋Masked PPO。只更新本地 actor/critic；全部奖励无塑形，终局成功加归一化成本惩罚。网络为显式实验历史编码、共享候选评分器和独立 value head。CPU 训练使用真实拟合或私有真实结果缓存。

正式 v1 训练为每变体五种子 `[11,22,33,44,55]`，每种子 20,000 transitions。四组消融分别重训 20,000 transitions，种子 11。每 512 步更新，周期性 meta-dev 评测，按开发回报选择检查点；最终留出集不参与选择。逐批保存全部特征、mask、候选映射、概率、价值、奖励和版本；保存最后一批更新前权重供独立核验。

```powershell
& '.\.venv\Scripts\python.exe' -m rut_science.science_bot.evaluation --audit-only
# 完整复现包含主线五种子和四组重训消融；输出目录必须尚不存在
& '.\.venv\Scripts\python.exe' scripts/reproduce_science_bot.py --output models/planner/reproduction
```

最终比较包含随机合法、廉价规则、稠密规则、证据响应规则、预算随机配置搜索、BC、全部 PPO 种子以及四组重训消融。8 个留出机制组 × 3 实例 × 3 预算 × 2 故障档位；派生副本不作为独立任务组。区间按根机制组配对 bootstrap。预算搜索是随机配置搜索，不声称实现 BOHB。

查看 `evaluation/summary.json`、`evaluation/final_test.json` 和研究结果说明。真实 LLM 选择器另做两个 demo 根任务的小额对照，不能据此宣称统计优势。运行最终评测时输出目录必须是新的，避免覆盖留出结果。

## 验收与交付索引

- `verification.json`：逐项产品检查、失败及限制。
- `实际交付与研究结果.md`：产品验收与完整负结果解释。
- `tests.log`：旧协议与新增语义测试。
- `policy_checkpoint/`：部署权重、来源清单和哈希。
- `training/`：所有权重来源、学习曲线；完整 rollout 在 `models/planner/v1/*/rollouts`。
- `benchmark_manifest/`：划分和行动目录。
- `evaluation/`：环境准入、开发选择、原始配对结果、区间和实时 API 小批对照。
- `demo_sessions/`：真实 API、Darcy 冷运行、故障 fixture、跨进程恢复和 HTTP 会话。
- `science_bot_terminal.svg`：真实终端布局导出预览。

完整产品复验：

```powershell
& '.\.venv\Scripts\python.exe' scripts/verify_science_bot_delivery.py --live
```

该命令会创建新的会话并产生真实模型 API 调用。`--demo` 也是显式确认并执行的非交互验收入口，交互运行仍先展示草案。

## 环境与结论边界

现有 `.venv` 已安装依赖，精确版本见 `environment.lock`。移到另一台机器后用 Python 3.12 创建虚拟环境，安装锁定依赖（CPU torch 使用 PyTorch CPU wheel 索引），再安装本地项目 `pip install -e . --no-deps`。

生成任务是受控数值回归，不是独立科学来源。旧 Darcy 的 160/32 小 bundle 已被历史实验使用，仅作真实工具与迁移 pilot；未把它重新包装为盲测，也未扩展未审计的原始 GB 级 MAT 数据。当前阈值是预注册工程门槛，没有物理领域通用标准的含义。

产品可运行、权重确实训练，与 RL 在科研问题上取得收益是两项不同结论。正式比较若不支持收益，报告负结果；仅有 8 个留出机制组、单种子消融、两个实时 LLM demo 根任务，不足以声称跨科学领域泛化。

可移植交付包不含原始 Darcy 数据、虚拟环境或模型供应商凭据。生成任务在重建环境后可独立运行；Darcy 需另行提供已校验本地 bundle。完整正式训练轨迹和全部种子权重随交付包提供；开发 pilot 元数据另表保留。
