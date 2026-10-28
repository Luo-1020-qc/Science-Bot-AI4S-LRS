# science Bot G2：CSV 与实验设计

> 后续 G2.1 已加入逐轮设计访谈与决策学习基础，见[G2.1说明](Science_Bot_G2_1_设计访谈与学习环境_zh.md)。本文的单轮规格入口与数值协议继续保留。

日期：2026-10-22。沿用 `science-bot.cmd` / `Start-ScienceBot.ps1`，通过源码、示例、文档和验收证据交付，不新增 ZIP。G2 接入新的表格任务族，原 generated / Darcy 引擎和 RL 权重保持原用途。

## 直接使用

在 `LangGraph_RL_Agent` 根目录启动内置合成示例：

```powershell
.\science-bot.cmd -Workspace 'RUT_Science\examples\g2'
```

输入以下自然语言，让模型通过原生工具检查 CSV、准备设计：

```text
请为 two_groups.csv 设计独立两组 Welch 比较。研究问题：A组与B组平均y是否不同。response=y，unit=id，factor=group，levels=[A,B]，数据来源为合成 synthetic。sampling_note=全部现有合成样本，仅作探索性演示；未进行事先功效计算。alpha=0.05，seed=42。
```

Agent 会显示实际设计、数据身份、样本与缺失处理、分析方法和执行步骤。检查后输入：

```text
/confirm
/report
/model-output list
```

只检查表格结构、不准备设计：

```text
检查 two_groups.csv 的列和缺失值
```

缺少数据来源、实验单位、因素水平/特征或样本依据时，不创建可执行实验；可完整重述需求，或使用下面的结构化规格。自然语言字段校验是保守的，复杂表述可能要求补充；它不是已证明理解任意科研请求的分类器。

## 不调用模型的完整示例

```powershell
.\science-bot.cmd -Backend offline -Workspace 'RUT_Science\examples\g2'
```

终端中选择一种设计：

```text
/design independent_design.json
/confirm
/report
```

另两种设计分别为：

```text
/design paired_design.json
/design prediction_design.json
```

每个新设计都需分别检查并 `/confirm`。默认12次工具操作；独立/配对设计从准备到报告需4次，预测设计需7次。准备前不足以执行剩余计划时会说明预算不足，可新建会话。API模式的模型请求/token继续使用同一根账本；数值工具次数与请求/token分别计数。

三个 CSV 与设计文件均为专门生成的合成演示数据，不来自用户作业或论文实验。示例规格文件声明了探索性样本依据；将工具运行成功解释为科学假设成立是不正确的。

## 支持的任务和协议

| 设计 | 数据结构 | 实际分析 | 报告与限制 |
|---|---|---|---|
| `independent` | 每行不同单位，因素恰好两个水平 | Welch 双侧 t 检验，不假设两组方差相同 | 每组数量/均值、前水平减后水平的差、自由度、p值与置信区间 |
| `paired` | 每单位在两个水平下各一条记录 | 按单位键匹配的双侧配对 t 检验 | 完整配对数、均值差、p值与置信区间；行顺序不决定配对 |
| `prediction` | 每行不同的独立可交换单位，1至20个数值特征 | 固定60/20/20训练/验证/测试；比较均值基线与OLS | 训练集拟合标准化和系数；验证MSE选方法，平局取均值；不重新拟合；冻结后一次测试 |

预测报告含各方法测试 MSE、胜出方法 RMSE、固定模型下测试损失的1000次单位 bootstrap 区间，以及均值基线减OLS的配对损失差和 t 区间。比较方法已在草案中固定，测试结果不能用于改变选择；这里的不确定性不是多次独立模型训练之间的变异。

独立均值比较默认假设独立单位及均值的正态近似；配对比较要求单位之间独立、单位内差值适合 t 推断。异常值、非正态、小样本及相关结构仍可能使推断不可靠。数量检查只设最低可计算边界，不是功效分析。工具不自动核实实验单位独立性或随机分配是否真实。

均值比较每组至少3个观测；配对设计至少3个完整单位。预测训练数量必须超过特征数加截距，验证和测试各至少3个单位。常量特征、秩不足/严重病态的训练矩阵、无差值变异的配对检验等会暂停，不输出虚构显著性。

## ExperimentSpec

最小独立组规格：

```json
{
  "data_path": "two_groups.csv",
  "research_question": "A组与B组平均y是否不同？",
  "design": "independent",
  "response": "y",
  "unit": "id",
  "factor": "group",
  "levels": ["A", "B"],
  "provenance": "synthetic",
  "sampling_note": "全部现有合成样本，探索性分析，未做事先功效计算"
}
```

终端 `/design <项目相对JSON路径>` 或 `/design {单行JSON}` 均可。HTTP通过原 `POST .../messages` 的 `text` 提交 `/design {JSON}`；HTTP不读取客户端任意规格路径。闭合规格拒绝额外参数，实验规范版本为 `experiment_spec_v1`。

| 字段 | 规则 |
|---|---|
| `data_path` | 当前工作区内的规范相对CSV路径；一次一个文件 |
| `research_question` | 当前研究问题；设计目标与可检验假设另由固定协议派生 |
| `design` | independent / paired / prediction |
| `response`、`unit` | 明确列名；单位ID不能为空 |
| `factor`、`levels` | 两种均值比较必需；水平顺序决定差值方向 |
| `features` | prediction必需；1至20个数值列，不含响应或单位ID |
| `provenance` | observational / randomized / synthetic，由用户声明，不由模型推断 |
| `sampling_note` | 样本/实验数或可用数据的依据；允许明确探索性限制，不自动补造功效计算 |
| `randomization_note` | randomized必须说明实际随机分配方式；其余省略或严格为not_applicable |
| `missing_policy` | 默认reject；显式drop_complete_case删除缺失单位，配对删除整个单位 |
| `alpha` | 默认0.05，范围0.001至0.2；双侧区间置信水平为1-alpha |
| `seed` | 默认42，0至2^32-1；用于预测划分和bootstrap，不是独立实验重复 |

观察性CSV不支持仅凭显著性作因果结论。随机分配声明也不足以自动建立完整因果识别。设计中的控制、随机化、区组和重复仅记录适用信息；当前执行器不接受区组、多因素、聚类或时间依赖任务，并要求使用另一个适配器。

## CSV 边界与模型上下文

- UTF-8（可带BOM）、逗号分隔、标题行列名唯一且非空；最多128 KiB、20000条记录、100列。TSV尚未接入。
- 列数不一致、空记录、非法控制字符、越出工作区或受保护文件会被拒绝。
- 缺失标记为空白、NA、N/A、NaN、null、none，不区分大小写。数值列须能解析为有限数；不自动编码类别或填补均值。
- ID/因素缺失始终拒绝；配对不完整或重复、独立设计出现重复单位、因素额外水平不能静默丢弃。
- `csv_inspect`向规划模型提供列名、数值/文本类型、缺失数、唯一值数和少量文本水平，以及数据哈希；不提供数值原始记录、响应均值或实验结果。低基数文本水平可能包含所选数据内容，敏感数据需先本地脱敏。
- 实际数值计算在本机完成。G2不把用户CSV的原始记录或测试结果发给模型进行后续选模，但当前方案不构成对任意历史上下文的隐私隔离证明。

## 计划、恢复与证据

宿主根据通过校验的规格构建 `execution_plan_v1`，绑定规格哈希与CSV哈希。均值比较为 `compare → report`；预测为 `partition → fit → select → evaluate → report`。每个节点需匹配已确认计划、依赖已完成且具有匹配哈希的结果；模型看不到执行工具。

工具都在注册表内：`csv_inspect`、`prepare_tabular_experiment`，以及仅由确认后执行器调用的 `tabular_compare/partition/fit/select/evaluate/report`。没有任意Python、shell或编辑用户文件的执行路径。

```text
<会话>/
  session.json、llm_ledger.json、model_calls/、turns/、tool_results/
  experiments/<实验ID>/
    experiment.json      # 规格、派生协议、计划、确认、已完成节点及哈希
    input.csv            # 实际输入快照，字节哈希与原文件一致
    nodes/               # 划分索引、训练参数、选择依据、逐条测试预测与指标
    report.json / report.md
```

原始CSV、快照、规格或节点证据被修改会阻止相应确认/继续执行。输入源变化后需新草案。`/pause`在工具边界暂停；`/resume`继续已确认计划。重复已提交的工具调用使用持久化结果，不重新消耗工具次数；完成后的重复执行不新增评价。若在工具返回落盘前进程崩溃，纯本地工具可能重新计算，不能把它描述为任意崩溃点都保证物理恰好执行一次；不会重新启动外部/GPU作业。

新问题会撤销未完成草案的旧确认；最后一个已完成科研报告继续可回看。`/cancel`取消当前调度，重新执行需新草案。原G1会话和旧数值会话仍按原版本恢复。

本轮验收覆盖三种合成数据、独立公式重算、跨进程恢复、数据变化、缺项、预算、幂等、原生tool_call_id及本地HTTP。一个真实在线合成任务不能证明广泛泛化能力；分类、多因素ANOVA、功效/样本量规划、任意模型搜索、CViT训练仍不在本轮范围。

统计实现依据为SciPy的[独立样本检验](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.ttest_ind.html)、[配对检验与置信区间](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.ttest_rel.html)及NumPy的[最小二乘求解](https://numpy.org/doc/stable/reference/generated/numpy.linalg.lstsq.html)。实际运行版本随报告记录，无依赖升级。

交付与复核入口见[本轮交付](../delivery/g2_update/README_本轮交付.md)。
