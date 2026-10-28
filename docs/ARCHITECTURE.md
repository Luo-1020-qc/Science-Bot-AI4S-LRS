# Harness架构、接口与权重

## 当前调用链

```text
science-bot.cmd → Start-ScienceBot.ps1 → science_bot/terminal.py
→ GeneralSession → LangGraph route_task / dispatch_task
→ 规则访谈、项目问答、表格工具或显式研究接口
```

应用源码保留在`RUT_Science/rut_science/`。`general/graph.py`组织图与SQLite检查点，`general/conversation.py`负责持久会话与调度，`general/registry.py`校验工具契约和宿主权限。

## 模型API

`general/provider.py`中的GeneralProvider读取`configuration.py`的配置，通过_NativeHTTPAgent发送`/chat/completions`请求。实际HTTP调用为`urllib.request.urlopen`。模型提出的tool_calls必须由本地宿主校验后执行。

根目录`API_key_Agent.json`保留在本地并由Git忽略。终端默认模型参数为deepseek-flash；需要其他服务模型时使用CLI的`--model`，不能假定配置文件model覆盖终端默认值。旧数值流程使用`science_bot/llm.py`与`agents.py`，仍被显式数值适配器引用，属于Harness功能，不按“历史科研代码”删除。

## 三个动作层次

| 层次 | 当前范围 |
|---|---|
| 在线应用 | 项目列表／显式文件读取、CSV检查、表格／数值方案准备、研究接口；实验执行需宿主确认 |
| 详细研究工具库 | 45项契约，20项离线实现，其余为已有能力引用、待实现、人审或禁用真实执行 |
| v2 RL环境 | 23个离散候选动作，32维公开特征；工具参数由环境绑定，仅执行离线模拟 |

v2动作包含review、align_claim、diff、四种model修订、repair_response、repair_budget、resolve、freeze、workflow、verify_workflow、reconcile、run_mock、poll、analyze、assess、next、report、read_plan、ask_variance和stop。候选定义以`Training_Data_Darcy_CViT/v2/protocol.py`为准。

## 必须保留的模型与数据

| 位置 | 作用 |
|---|---|
| `RUT_Science/models/planner/v1/` | 数值引擎仍从这里加载BC／RL及selected权重；v1是有效模型目录 |
| `RUT_Science/models/design_interview_bc/` | 访谈BC参数；默认访谈仍为rule |
| `RUT_Science/models/retained_delivery_checkpoint/` | 从旧delivery移入的完整检查点材料，权重未删除 |
| `RUT_Science/research/strategy_learning/studies/` | G2.2／G2.3策略、修订试验权重、任务库和冻结研究代码 |
| `Training_Data_Darcy_CViT/v2/ppo_smoke/` | 64步链路检查的行为／更新参数与采样证据 |
| `Training_Data_Darcy_CViT/v2/sample_batch_001/ppo_run_001/` | 三个任务96步采样及更新参数 |
| `RUT_Science/data/darcy_cpu_v1/` | 数值适配器仍读取的数据，不是本次弃用的训练数据v1 |

权重须与架构、特征顺序、动作映射、mask和工具版本一同加载。更换DeepSeek key不覆盖本地权重。保存权重不等于已部署默认入口；本次清理不重新训练、不修改默认策略。

## 当前边界

研究命令通过只读worker执行固定模拟及DOE检查。20个详细离线工具已通过独立会话worker接入ToolRegistry，使用/tools call或/tools chat；API与训练宿主可共享execute_library_tool。v2学习策略权重尚未部署默认入口。DOE可审阅状态不证明科学假设成立；已有研究未显示PPO优于规则，真人专家标签仍为0。详见[工具接入](TOOL_LIBRARY.md)。
