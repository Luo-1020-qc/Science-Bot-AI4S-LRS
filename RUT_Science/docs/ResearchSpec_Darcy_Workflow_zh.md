# v0.3：工具契约、研究规格与真实 Darcy 科研工作流

本次完成两个工程目标：把精确参数与用户确认的研究规格接入执行器；建立一个基于本地公开 Darcy 数值数据、可独立重算的 CPU 科研工作流。已有 `demo_verified` 和 `live_kimi_*` 原始记录保留。新版本不使用旧结果来宣称改进。

v0.3.1 配置更新：全部当前 API 入口和扫描脚本统一默认读取项目级 `API_key_Agent.json`。本页正式 v0.3.0 结果与源码快照为历史证据；配置修改后当前源码哈希会不同，复跑须使用新输出目录。

## 1. 工具契约与 ResearchSpec

实现位置：[environment.py](../rut_science/environment.py)、[research_spec.py](../rut_science/research_spec.py)、[runtime.py](../rut_science/runtime.py)。

- 合成任务 `train_model.model` 的合法接口值为 `linear`、`mean`；`ridge` 不作为别名。训练比例为 `[0.4,0.7]`，划分种子为非负整数。未知字段、布尔值冒充数字、非有限值、越界值在工具执行前拒绝。
- Darcy 使用独立契约：合法模型为 `ridge_field`、`mean_field`，训练比例固定为 `0.8`；该比例只应用于公开训练来源的子集，不包含独立测试来源。
- `ResearchSpec` 保存版本、数据名与哈希、目标与单位、模型、划分策略与种子、验证比例、指标、拟合/封存测试次数上限及固定方法参数。记录内容哈希绑定确认与报告。
- `confirm_research_spec()` 是可信宿主接口，没有登记为模型工具。合成基准由明确编写的用户对话 fixture 在第 2 轮确认；Darcy 命令由操作者提交的 JSON 规格确认。当前不从任意自然语言自动推断授权，也没有完成交互式规格提案 UI。
- 规格不匹配的合法参数也会被拒绝，例如允许 `mean` 的工具不能替代已确认的 `linear`。规格绑定当前数据，写入后不允许替换。失败调用回滚状态。
- 公开规格只在绑定的确认轮次投递；私有 Gold、未来对话、测试标签与参考预测不提供给 Agent。运行级时间、步骤、请求/token 上限仍由运行器与 Manifest 管理，规格中的预算限定成功拟合和封存测试各一次。

合成基准的新规格实例见 [research_specs.json](../outputs/contracts_verified_v030/benchmark/research_specs.json)，新版回归结果见 [report.md](../outputs/contracts_verified_v030/report.md)：35 个执行实例与 10 个澄清实例通过。该结果是规则控制器的工程检查。

## 2. 为什么选 Darcy

本地已有两个标准源文件：`piececonst_r421_N1024_smooth1.mat`、`piececonst_r421_N1024_smooth2.mat`，公开参考入口可核查同名数据与系数场到解场任务：[原 Transolver Darcy 入口](https://github.com/thuml/Transolver/blob/main/PDE-Solving-StandardBenchmark/exp_darcy.py)。

本次实际读取源 MAT 的 `coeff` 与 `sol`，不从旧预测结果反向生成数据，也不依赖未验证的缓存。源文件各约 1.69 GB，内容做 SHA-256 校验；提取后再次确认源文件没有变化。保存的数值 bundle、样本索引、空间采样规则与文件哈希均写入数据 Manifest。

这里的“真实科研工作流”指在已有公开数值 PDE 数据上实际进行训练与独立测试；数据由科学数值模拟产生，不是物理实验测量。小规模协议由本项目定义，不复现论文完整训练协议。

## 3. 冻结的 CPU 协议

| 项目 | 固定设置 |
|---|---|
| 输入与目标 | 介质系数场 → 压力解场；目标使用无量纲数值约定 |
| 数据子集 | 第一份源文件前 160 个样本；第二份源文件前 32 个样本 |
| 空间网格 | 原始 421×421 按步长 30 取样为 15×15，包含边界 |
| 模型输入 | 15×15 系数场按步长 3 取 5×5，共 25 个特征 |
| 输出 | 完整 15×15 解场，共 225 个值 |
| 划分 | 对 160 个训练来源样本用 NumPy PCG64、种子 2026，划分 128 train / 32 validation；32 test 来自独立源文件 |
| 模型 | `ridge_field`；输入逐特征训练集均值/标准差，输出训练集均值中心化，固定 alpha=1.0 |
| 物理边界 | 预测边界显式置零，记录此约束；没有声称实现 PDE 残差验收 |
| 指标 | 每个样本的 `||预测−真实||₂ / ||真实||₂`，再对样本取平均 |
| 封存 | 验证误差可返回；测试误差只写入评测器持有的最终报告；测试后禁止重新训练或再次测试 |
| 比较基线 | 训练均值解场 `mean_field`；独立参考报告仅列其验证误差，不依据测试选择方法 |
| 资源 | CPU；Agent 最多 16 步；API 请求最多 16 次、token 准入最多 100,000；默认每 episode 180 秒 |

alpha、采样网格、样本数与模型在查看 Agent 测试结果前已固定。本轮没有参数搜索、训练神经算子或修改现有毕业论文实验。

## 4. 实际结果与独立验收

同一固定协议的确定性工具控制器已完成六步：查看、核查、划分、训练、封存测试、报告。

| 指标 | 实际值 |
|---|---:|
| ridge_field 验证平均相对 L2 | 0.1184913299（11.8491%） |
| ridge_field 独立测试平均相对 L2 | 0.1250051181（12.5005%） |
| mean_field 验证平均相对 L2 | 0.2568546692（25.6855%） |

环境通过正规方程拟合；参考计算使用 SciPy 增广最小二乘/SVD 路径，不调用环境拟合或预测函数。评分器从实际权重、私有数据重新计算预测与误差，并对照参考计算；还检查数据来源隔离、训练集归一化、规格与报告哈希、对象绑定、封存次数和边界。当前固定六步流程仍采用严格过程评分，不包含允许故障恢复的新协议。

证据入口：

- [已确认研究规格](../outputs/darcy_cpu_control_release_v030/research_spec.json)
- [科学报告](../outputs/darcy_cpu_control_release_v030/scientific_reports.json)
- [独立参考](../outputs/darcy_cpu_control_release_v030/reference.json)
- [运行与评分](../outputs/darcy_cpu_control_release_v030/episode.json)
- [逐步轨迹](../outputs/darcy_cpu_control_release_v030/trajectory.jsonl)
- [重算、状态链与产物验证](../outputs/darcy_cpu_control_release_v030/verification.json)
- [可重新计算的预测与真实场 NPZ](../outputs/darcy_cpu_control_release_v030/test_predictions.npz)

`outputs/darcy_cpu_control_v030` 保留第一次本地运行的未完成记录（评分中的 NumPy 布尔值序列化问题），已修复并加入序列化检查；交付以 `*_release_v030` 为准。

本次增加 15 项针对规格与真实工作流的测试，共 **53 项通过**。单元测试使用明确标注的生成 fixture，真实科研结果来自上述 MAT 数据运行。

完整交付核查见 [v0.3 验证结果](../outputs/v030_delivery_verification.json)：两份正式工作流运行核验通过，当前源码与冻结快照一致，文档本地链接有效，未发现密钥泄漏。可用 `python -m scripts.verify_v030_delivery` 重跑交付核查，无 API 请求。

## 5. API 检查与配置变化

当前用户提供的配置仅有一个 DeepSeek 条目，端点为 `api.deepseek.com`，没有默认模型。先前记录中的 Kimi 配置已不适用于当前文件。因此两次使用旧模型名称的运行在工具执行前返回 HTTP 400，保留在 `outputs/darcy_cpu_kimi_verified_v030` 与 `outputs/darcy_cpu_kimi_release_v030`。额外一次有界诊断请求确认：服务器支持 `deepseek-flash`、`deepseek-v4-pro`；这是接口配置失败，不是 Agent 的科研能力失败。

新模型名称与非思考参数已对照 [DeepSeek Chat Completions 官方文档](https://api-docs.deepseek.com/api/create-chat-completion/) 核查。当前模型适配器将可信宿主上下文合入请求最前面的单个 system 消息，并保持只在规格确认后投递。后续有效模型运行单独保存，不覆盖上述失败记录。

**DeepSeek Flash 的实际执行检查已通过。** 它完成了六次成功的科研工具调用，生成与控制器一致的预测和测试误差，并通过独立参考、状态链、请求体与产物校验。共 8 次模型请求，12,802 输入 token、652 输出 token，未知用量预留为 0；请求上限 16、token 准入上限 100,000。第 7 步有一次输出不符合动作格式，运行器反馈后第 8 步给出合规结束消息；原记录保留。当前严格科研评分检查工具参数、依赖、结果和违规工具调用，格式反馈次数另行说明，不将其描述为零交互错误。

证据：[真实模型报告](../outputs/darcy_cpu_deepseek_release_v030/report.md)、[完整轨迹](../outputs/darcy_cpu_deepseek_release_v030/trajectory.jsonl)、[用量账本](../outputs/darcy_cpu_deepseek_release_v030/budget.json)、[独立核验](../outputs/darcy_cpu_deepseek_release_v030/verification.json)。同模型多策略、多次重复及七种交互尚未运行。

上述三次 HTTP 400 请求没有服务端 usage：两份运行账本保留未知用量预留，一次诊断请求单独计数。不能从失败状态推断免费，货币费用未配置或核对。

## 6. 如何复跑

在 `RUT_Science` 项目目录执行；各个输出目录须新建或为空。

```powershell
# 科研扩展依赖；核心合成任务仍只用标准库。
& '.\.venv\Scripts\python.exe' -m pip install -r requirements-darcy.lock.txt

# 仅首次准备；直接读取本地源 MAT，输出约 0.33 MiB 的私有数值 bundle。
& '.\.venv\Scripts\python.exe' -m rut_science darcy prepare --data data/darcy_cpu_new

# 操作者确认该 JSON 规格，执行固定工作流。
& '.\.venv\Scripts\python.exe' -m rut_science darcy run --data data/darcy_cpu_new --output outputs/darcy_control_new

# 在同一环境中执行真实 LLM 工具调用；使用当前 DeepSeek 配置。
& '.\.venv\Scripts\python.exe' -m rut_science darcy run --data data/darcy_cpu_new --agent api_direct --api-config '../API_key_Agent.json' --model deepseek-flash --output outputs/darcy_api_new --max-seconds 180

# 独立核验已保存运行（无模型调用）。
& '.\.venv\Scripts\python.exe' -m rut_science darcy verify --data data/darcy_cpu_new --output outputs/darcy_control_new

& '.\.venv\Scripts\python.exe' -m unittest discover -s tests -v
```

可用 `--spec <path>` 提交另外一份明确确认的合法规格，例如独立的 `mean_field` 运行；不可在一次已经写入的 episode 中修改规格。`darcy reference` 提供独立参考入口。Darcy 当前不支持中途续跑，失败应保留并使用新输出目录；原合成/API 基准仍保留 `--resume`。

源数据路径在 `dataset.json` 保存；源文件不随本项目复制或发布。`data/darcy*/` 与 `outputs/darcy*/` 已加入忽略规则；科学数组、Gold 与参考产物不能挂载给 Agent 的任意文件访问工具。当前仍是进程内工具边界，未实现针对任意代码执行的 OS 沙箱。

## 7. 下一阶段边界

本次完成精确契约、可信规格与一个真实数值工作流；尚未实现结构化计划执行、LangGraph、OpenCode/MCP、分支/恢复任务、盲人工 Judge 或 RL。Darcy 目前只有固定协议的理想实例，尚未扩展成七种配对交互，也没有留出泛化结论。该弱 CPU 基线用于建立工程与验收参考，不应与完整神经算子论文结果直接比较。

下一步应在这个已跑通的后端上加入计划节点与版本管理，再构建需要选择、恢复的任务；冻结同一模型/工具/预算进行对照。
