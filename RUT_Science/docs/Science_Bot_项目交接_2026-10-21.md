# science Bot 项目交接文档

> 2026-10-27 交接补充：当前入口见 [最新交接](../../science_Bot_交接.md) 与 [阶段总结](../../阶段性总结2_2026-10-27.md)。G1/G2/G2.1已进入应用，G2.2/G2.3研究已 [合并](../research/strategy_learning/README.md)，真实CViT工具仍未接入，通用访谈继续默认规则。本文是2026-10-21历史快照，保留当时路径、统计和待办。

交接日期：2026-10-21（北京时间）。本文件面向接手开发者与后续编码 Agent，依据本机源码、交付说明和已保存的验证记录整理。

> 2026-10-22 G2 更新：已交付表格数据与实验设计的受限首版，新增独立两组、配对和mean/OLS预测的真实工具执行与重算证据。当前范围见 [G2 使用说明](Science_Bot_G2_表格与实验设计_zh.md) 和 `delivery/g2_update/`；本文件下文保留原交接快照。

> 后续更新：第 7 节的 P0 已实现，当前终端支持实际模型输出展示与 `/model-output [list|编号]` 只读回看。以下“未实现”描述保留为原交接快照；当前行为以 [模型输出说明](Science_Bot_Model_Output_zh.md) 和 `delivery/model_output_update/` 的新增验收为准。沿用现有启动入口，不新增压缩包。

> 2026-10-22 更新：G1 已交付。默认新会话进入通用分流，支持项目工具问答与原科研引擎统一调度。最新行为见 [G1 使用说明](Science_Bot_G1_通用入口_zh.md) 与 `delivery/g1_update/`；本文件其余内容保留原交接快照。

## 1. 当前结论与接手重点

science Bot 已具备终端科研入口、LangGraph 流程编排、预算约束、本地训练的实验选择策略、真实数值实验、会话持久化与恢复，以及通用 `--workspace` 参数。

它目前是围绕已注册数值工具工作的科研 Agent。工作区支持浏览和读取项目文件；没有向 Agent 暴露源码编辑、补丁应用或任意 shell 执行工具。Agent 会写入自己的会话、日志、实验与报告文件。这是当前工具集合的能力边界，不是操作系统级只读沙箱。

**下一项优先需求：在终端展示底层大语言模型实际返回的结果。用户已提出该需求，目前尚未实现。** 现有模型调用会保存结构化结果，但终端主要展示执行状态和数值摘要。不要将“调用成功并保存”误报为“已经向用户展示”。

本次交接仅新增文档，没有实现该需求、重新训练 RL 或新增真实 API 调用。

## 2. 目录与交付物

项目共同根目录：`D:\Python Files\CityU_Project\CityU_Hackathon_AI4S\LangGraph_RL_Agent`。2026-10-21 整理后，工程主体 `RUT_Science` 已移入此目录；下列位置和启动命令已同步更新。

| 位置（相对共同根目录） | 用途 |
|---|---|
| `RUT_Science/` | Python 应用、虚拟环境、测试、模型与交付证据 |
| `RUT_Science/rut_science/science_bot/` | science Bot 的主要实现 |
| `RUT_Science/prompts/` | 科研角色提示词与结构化输出要求 |
| `RUT_Science/models/planner/v1/` | 正式训练权重、轨迹和清单 |
| `RUT_Science/models/planner/v1/selected/` | 默认部署策略 |
| `RUT_Science/delivery/` | 原始产品验收、科研评测、运行说明 |
| `RUT_Science/delivery/workspace_update/` | 工作区增量验收及测试记录 |
| `LangGraph_RL_demo_规划.md` | 原始规划与历史思考；当前完成状态以实现和验收记录为准 |
| `science-bot.cmd` | Windows 推荐启动入口 |
| `Start-ScienceBot.ps1` | 启动参数包装器 |
| `maintenance/organization_2026-10-21/archive_inspection.json` | 原 ZIP 的逐文件哈希与重复检查 |
| `maintenance/organization_2026-10-21/extracted/` | 解压后保留的不同历史文件与依赖测试样本 |

本机源码已包含工作区更新。两个项目交付 ZIP 已在本次整理中完整解压并核对：重复副本和冗余 ZIP 已删除，6 个不同历史文件及全部文件哈希清单保留在上述整理记录中。第三方依赖的测试 ZIP 保留原件。

相关资料：

- [通用工作区说明](Science_Bot_Workspace_zh.md)
- [启动、API 与复现说明](../delivery/README_运行与复现.md)
- [实际科研结果与限制](../delivery/实际交付与研究结果.md)
- [原始产品验收记录](../delivery/verification.json)
- [工作区增量验收记录](../delivery/workspace_update/verification.json)

## 3. 环境与启动

本机使用 Windows PowerShell、Python 3.12 和应用自带 `.venv`。不要依赖系统 `python` 已在 PATH 中；优先使用虚拟环境解释器。完整依赖版本见 `delivery/environment.lock`。

### 3.1 推荐的终端入口

```powershell
Set-Location -LiteralPath 'D:\Python Files\CityU_Project\CityU_Hackathon_AI4S\LangGraph_RL_Agent'

# 连接已配置的模型服务；默认 planner 为 rl
.\science-bot.cmd -Workspace 'D:\Python Files\CityU_Project\MasterThesis_Project\AI4SD_FP\CViT_OFA_Darcy_2026_10_20'

# 离线模式：不调用大模型，使用有限文本解析和本地实验策略
.\science-bot.cmd -Workspace 'D:\Python Files\CityU_Project\MasterThesis_Project\AI4SD_FP\CViT_OFA_Darcy_2026_10_20' -Backend offline
```

`-Workspace` 必须指向已存在目录。包装器在切换应用目录前解析路径，因此 `-Workspace .` 表示调用者所在项目。

交互示例：

```text
/workspace
/files *.py
/read dynamic_cvit.py
在 generated 数据集上运行实验，预算10，门槛0.20。
/status
/confirm
/experiments
/report
/exit
```

`/read` 仅在本地显示文件，不会自动把文件内容提交给 DeepSeek。示例研究任务仍使用注册的 generated 数值后端，不会训练刚读取的 CViT 源码。

### 3.2 Python 入口、恢复和批处理

```powershell
Set-Location -LiteralPath 'D:\Python Files\CityU_Project\CityU_Hackathon_AI4S\LangGraph_RL_Agent\RUT_Science'

& '.\.venv\Scripts\python.exe' -m rut_science science --help
& '.\.venv\Scripts\python.exe' -m rut_science science --workspace 'D:\my-project' --backend offline
& '.\.venv\Scripts\python.exe' -m rut_science science --workspace 'D:\my-project' --resume <session-id>

# 无交互演示：该参数会自动确认并实际执行实验
& '.\.venv\Scripts\python.exe' -m rut_science science --backend offline --demo

# 本地 HTTP 服务，默认监听 127.0.0.1:8765
& '.\.venv\Scripts\python.exe' -m rut_science serve --workspace 'D:\my-project'
```

`D:\my-project` 和 `<session-id>` 是占位符，使用时替换为实际值。也可以用 `--resume <完整会话目录>` 恢复已有会话。

交互入口依赖真实控制台。通过无控制台的子进程捕获交互界面输出，可能触发 `NoConsoleScreenBufferError`；自动化运行使用 `--demo` 或 `ScienceSession` Python 接口。直接运行 `.ps1` 若遇执行策略限制，可使用已提供的 `.cmd` 包装器。

### 3.3 DeepSeek 配置与策略的区别

- 配置读取入口：`rut_science/configuration.py`。
- 默认配置文件：共同根目录下的 `API_key_Agent.json`。
- 历史真实调用验证过 DeepSeek 端点；终端默认请求模型名为 `deepseek-flash`。运行时实际模型与用量应核对当次调用记录，而非只看界面配置名。
- `--backend api` 控制是否调用大模型；`--planner rl` 控制实验行动由本地策略选择。二者可以同时启用，大模型负责需求提取、候选提议与报告解释。
- `--planner llm` 才由大模型选择科研行动；`--backend offline` 不会产生真实大模型输出。

交接文档和分发包不复制密钥。现有 API 服务使用独立本地令牌，不与供应商 API key 混用。

## 4. 实现结构与科研流程

| 模块 | 责任 |
|---|---|
| `terminal.py` | Rich / prompt_toolkit 终端、命令分发与事件展示 |
| `session.py` | 草案提取、确认、候选提议、运行控制、恢复和报告解释校验 |
| `graph.py` | LangGraph 节点、确认中断与 SQLite checkpoint |
| `contracts.py` | 科研规格、固定实验目录、预算与契约 |
| `environment.py` | 共享行动内核、合法性 mask、扣费、作业、证据及封存评价 |
| `numerics.py` | 真实 mean/ridge 拟合、生成任务及已有 Darcy 数据适配 |
| `policies.py` | 规则、共享候选 actor/critic、BC/PPO 策略加载 |
| `training.py` / `evaluation.py` | 训练、开发选择、冻结比较 |
| `llm.py` | 模型角色调用、schema 检查、请求与结果落盘 |
| `workspace.py` | 项目身份、路径约束、本地目录浏览与文本读取 |
| `api.py` / `gym_adapter.py` | 本地 HTTP 与训练环境适配，共用科研行动内核 |

流程为：自然语言需求 → 结构化草案 → 用户确认 → 候选提议 → 观察当前证据 → 策略选择合法行动 → 数值工具执行并记账 → 循环或终局评价 → 报告与模型解释。

LangGraph 实际节点为 `await_confirmation → propose → observe → dispatch → observe … → finish`。图状态主要存会话引用、版本和步数，完整科研账本由 `environment.json` 管理。

当前科研工具围绕固定 mean/ridge 实验目录。搜索 CU 是逻辑实验成本，不等于人民币、token 或运行秒数；程序另记耗时、请求和 token。终局预留 2 CU、2 次工具操作、1 次模型解释请求与 4096 token 准入额度。

## 5. 工作区、持久化与恢复约束

指定工作区后，默认目录结构为：

```text
<workspace>/.sciencebot/
  workspace.json                 # 稳定身份、规范根路径、读取策略
  sessions/<session-id>/
    session.json                 # 模式、科研规格、确认与错误等
    environment.json             # 科研状态和资源账本
    graph.sqlite                 # LangGraph checkpoint
    events.jsonl                 # 业务事件
    llm_ledger.json               # 模型请求与 token 记账
    model_calls/*_request.json    # 调用记录，不含认证 header
    model_calls/*_response.json   # 通过顶层 schema 检查的结构化模型结果
    jobs/                        # 已登记数值作业及结果
    report.json / report.md      # 主机生成的科研报告（完成后）
    explanation.json             # 通过额外检查的模型解释（可选）
```

`--sessions` 可显式覆盖保存位置；不指定工作区时保留旧版默认会话位置 `RUT_Science/outputs/science_bot`。工作区不会改变应用的模型、数据和凭据查找根目录。

恢复核对 workspace_id、规范根路径、读取策略、数据与策略身份。旧版无工作区会话不能通过附加参数静默改绑项目。科研草案更新会撤销旧确认；确认哈希包含工作区绑定。普通源文件内容没有自动纳入科研输入哈希，未来工具若使用源码或项目数据，必须另行绑定具体输入。

作业通过登记、原子快照、幂等键与恢复对账避免重复扣费或重复提交；图 checkpoint 落后于账本时跳过已提交步骤。执行状态无法确认时暂停，不宣称任意外部进程都能自动恢复。

本地读取限制：UTF-8 文本单文件最多 128 KiB，列表默认最多 200 项，并限制扫描量；排除凭据、二进制、控制字符、依赖与内部状态目录。校验最终路径，目录遍历不跟随重定向目录，`.sciencebot` 与默认会话目录拒绝 junction/symlink 重定向。HTTP 工作区由服务启动者选择，客户端不能在创建会话时提交任意项目路径。

## 6. 验证记录与科研结论

以下为已保存的历史验收结果；本次文档交接没有重新执行测试或在线模型验收。

| 记录 | 结果与证据 |
|---|---|
| 原始产品验收 | `delivery/verification.json`：21 项产品检查通过，含真实 API、恢复、幂等和 HTTP/CLI 一致性等 |
| 原始回归 | 139 项；见 `delivery/tests.log` 与原始验收 JSON |
| 工作区增量全量回归 | 共 159 项，158 通过、1 跳过；见 `delivery/workspace_update/tests.log` |
| 跳过原因 | 当前 Windows 账户不能创建文件符号链接；目录 junction 的越界和状态重定向测试已通过 |
| 实际终端检查 | 在含中文和空格的 fixture 项目中验证 `-Workspace .`、文件命令、退出与同 ID 跨进程恢复 |
| 工作区增量成本 | 未新增真实 API 调用，未重新训练 RL；测试项目与用户 CViT 源码分开 |

正式 RL 主线为从零 PPO 和 BC＋PPO 各 5 个种子、每个 20,000 transitions，另有 4 组各 20,000 步的单种子消融，合计 **280,000** 个正式 PPO transitions。开发 pilot/smoke 额外消耗 **280,512** 个 transitions，已有记录，不能隐去。

默认 `selected` 是按开发集选择的 **scratch PPO，seed 33，checkpoint 5120**，不是 BC＋PPO。来源见 `models/planner/v1/selected/manifest.json`；选择后没有依据最终测试重新挑选部署权重。

冻结测试为 8 个机制组 × 3 个实例 × 3 个预算 × 2 个故障档位，每策略 144 个任务。关键结果：

- 廉价、稠密和自适应强规则成功率均为 100%。
- BC＋PPO 五种子均为 100%，平均搜索消耗约 9 CU；自适应规则约 1.99 CU，没有表现出效率收益。
- 从零 PPO 五种子平均成功率约 90.3%；BC 为 87.5%。
- 结论：本轮结果不支持 RL 相对强规则具有稳定收益，不应包装为 RL 科研能力突破。

机制组数量有限，派生实例和预算副本不视作独立机制组。Darcy 使用历史已暴露的小 bundle，仅作真实数值工具与迁移 pilot；实时 LLM 选择器只有两个 demo 根任务；消融各一个种子。不支持跨科学领域泛化或新盲测结论。

## 7. 首要待办：展示底层模型输出

### 7.1 原始需求与当前缺口

用户原话：“很好，你能不能还是让它输出背后大语言模型输出的结果”。结合上下文，优先解决现有真实模型结果在终端不可见的问题。是否增加通用代码问答、流式输出或源码编辑，不属于这句话已经确定的具体实现范围。

当前调用角色：

| 角色 | 已保存的实际结构化输出 |
|---|---|
| `intake_v2` | fields、missing_required、conflicts、questions |
| `candidate_generator_v1` | candidates、unresolved |
| `llm_selector_v1` | action_id、evidence_refs、reason 等 |
| `report_explainer_v1` | summary、findings、limitations、artifact_refs |

`ScienceLLM.call()` 会把通过顶层 schema 检查的结果写入 `model_calls/*_response.json`。这些文件是解析后的应用层 JSON，不是完整供应商 HTTP 响应体；当前没有保存完整响应 envelope 的承诺。

`terminal.py` 的事件回调主要展示 `selected`、`tool_result`、`error`。完成面板只展示成功标记、封存误差和报告位置；`/report` 显示主机科研报告 JSON。`session.finish()` 会尝试保存 `explanation.json`，但终端没有完整展示其内容。

### 7.2 建议实施方式

1. 在模型调用与会话层补充结果通知，明确 role、请求编号和输出文件引用，保留现有请求/token 账本。
2. 在终端按角色展示实际返回的可读内容。报告解释可显示 summary、findings 和 limitations；选择器理由只在实际使用 LLM planner 时展示，RL 行动不得冒充 LLM 决策。
3. 增加只读回看命令，例如 `/model-output`，从当前会话保存结果中展示最近一次或指定编号结果。该命令是建议接口，尚不存在；回看不重新调用模型、不增加 CU。
4. 区分“模型返回的提议”和“主机核验后的实验结论”。`llm.py` 的顶层 schema 检查之后，`session.py` 仍会检查字段来源、合法行动、证据引用或解释中的数值与工件引用。
5. 报告解释沿用 `verify_explanation()` 检查；解释失败应给出明确状态，主机科研报告仍可查看。不要把额外检查描述为对所有语义事实的完整验证。
6. 对模型文本采用安全的纯文本渲染，避免把返回内容当作 Rich markup、终端控制序列、命令或文件路径执行。不回显密钥与认证头。

该功能应保持现有实验策略、数值契约和会话恢复行为，不需要重新训练 RL。当前 `/read` 是本地显示，若后续增加“把文件发给模型分析”，需明确新增的数据流和输入选择，不能把现有读取动作悄悄改成外发。

### 7.3 建议验收标准

- API 模式下，终端可看到当次真实模型返回内容，并能对应到保存文件；离线模式明确没有真实模型输出。
- 默认 RL planner 不展示虚构的 LLM 行动理由；LLM planner 展示其真实返回理由。
- 恢复会话后可回看历史输出，重复查看不会新增请求或费用。
- 模型失败、格式错误、解释检查失败时有可见状态，既有实验与主机报告仍保留。
- 覆盖输出渲染、结果回看、离线分支、错误分支及恢复的必要测试；进行一次真实终端验证。在线验证如执行，应记录新增调用及成本。

## 8. 后续扩展与维护注意事项

| 优先级 | 事项 | 接手说明 |
|---|---|---|
| P0 | 展示真实模型输出 | 已有明确用户需求，按上一节实施 |
| P1 | 项目文件的模型问答 | 需要明确上下文选择、模型输入上限和记账；当前未提供通用 `/ask` |
| P1 | CViT/新数据集工具适配 | 当前读取源码不等于能训练它；需要输入输出契约、数据身份、资源成本和评价隔离 |
| P2 | 源码编辑能力 | 目前没有；若新增，应设计受限路径、补丁预览、应用与回滚、文件版本冲突检测 |

这些优先级用于交接排序，除 P0 外不表示用户已经要求立即实现全部功能。

维护时从 `rut_science/science_bot/` 入手，保留旧 `ResearchSpec`、旧协议与评分语义。不要修改用户打开的论文笔记或 CViT 代码来完成 science Bot 的界面需求。

新验证结果另存或更新对应增量记录，保留历史失败与原始负结果。新功能有源码变化时，需要重新形成对应验收，不能沿用旧哈希声称新版本已验收。普通界面更新无需重新运行大规模训练和冻结测试。

常用验证命令（在应用目录执行）：

```powershell
# 自动化回归，不主动进行真实模型调用
& '.\.venv\Scripts\python.exe' -m unittest discover -s tests -v

# 全产品在线验收：会创建新会话并产生真实 API 请求
& '.\.venv\Scripts\python.exe' scripts/verify_science_bot_delivery.py --live
```

历史证据索引以第 2、6 节为准。工作区增量打包脚本为 `scripts/package_science_workspace_update.py`，依赖已有 fixture 和验证材料；增加新功能时先核对打包范围，避免把新功能误装成旧验收版本。

## 9. 可直接交给下一位开发者的任务

> 请在 `D:\Python Files\CityU_Project\CityU_Hackathon_AI4S\LangGraph_RL_Agent\RUT_Science` 继续 science Bot 开发。先阅读本交接文档以及 `science_bot/terminal.py`、`llm.py`、`session.py`。当前通用工作区已完成；首要未完成需求是在终端显示底层 DeepSeek 的实际输出，并提供不会新增模型调用的历史回看方式。保留模型提议与主机验证结论的区别，沿用预算和解释检查，不新增任意 shell 或源码修改工具，不重新训练 RL。完成后补充相关测试、真实终端验证与使用说明，并准确记录是否产生新的在线调用。
