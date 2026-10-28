# science Bot G2.1：设计访谈与可学习决策环境

日期：2026-10-22。沿用 `science-bot.cmd` / `Start-ScienceBot.ps1`，不新增 ZIP。此次是在 G2 三类已注册实验之上增加设计访谈、结构化反馈与决策学习基础，不扩展到任意科研领域。

## 直接体验

在 `LangGraph_RL_Agent` 根目录：

```powershell
.\science-bot.cmd -Backend offline -Workspace 'RUT_Science\examples\g2'
```

终端逐行输入，前两个 `1` 分别回答“独立单位”和“独立两组设计”：

```text
/interview two_groups.csv
/answer 比较A组与B组的平均y
1
1
/answer {"response":"y","unit":"id","factor":"group","levels":["A","B"],"provenance":"synthetic","sampling_note":"全部现有合成样本，探索性演示"}
/confirm
/report
```

也可以只说“设计一个实验”，先从研究问题开始访谈。自由文本用 `/answer <回答>` 明确回复当前字段，编号/注册枚举值或字段JSON可以直接回复。问题中已提供的字段会累计，后续不再要求全部重填。

`/interview` 不带参数恢复当前访谈；带CSV参数开启新访谈并明确授权该CSV的结构检查。读取数据仍须绑定工作区。API模式移除 `-Backend offline`：无法由本地解析器理解的显式 `/answer` 文本可请求模型提取字段；模型提议必须包含当前回复中的真实引用，不得由列名或常识补造来源、独立性或随机化。

当前字段提取采用保守的词面与有限别名检查，不能保证识别所有复杂语义；遇到误拒绝可以用字段JSON。自由文本未被识别为访谈回复时会按普通问题处理，避免把无关聊天写入科学事实。

## 状态和命令

| 命令 | 用途 |
|---|---|
| `/interview [CSV相对路径]` | 开启或恢复访谈，不执行实验 |
| `/answer {字段JSON}` | 增量补充信息；值冲突时保留旧值并要求解决 |
| `/answer <文本>` | 明确回答当前问题，支持离线短答及API引用提取 |
| `/resolve {字段:确认值}` | 只解决当前存在冲突的字段 |
| `/revise {字段:新值}` | 明确修订已声明内容，生成新版本并使旧确认失效 |
| `/interview-options` | 浏览三种方法及条件，不替代用户选择或设计校验 |
| `/interview-status` | 终端本地查看完整状态，不发模型请求、不消耗访谈轮数 |
| `/interview-refresh` | 数据变化后重新检查CSV、修订证据版本并重新准备草案 |
| `/interview-reset` | 开始空白访谈，旧记录保留 |
| `/interview-policy rule` / `bc` | 显式选择规则或内置版本化BC策略，不接受任意权重路径 |
| `/design-feedback {"rating":1至5,"note":"说明"}` | 保存待审反馈，不自动训练或改变部署权重 |

原 `/design` 完整规格、`/confirm`、`/pause`、`/resume`、`/cancel`、`/report` 和 `/model-output` 保留。HTTP客户端通过原 `/messages` 路由提交访谈命令；GET会话状态含 `interview` 字段，读取状态不需要发送消息。以消息形式提交 `/interview-status` 仍属于会话变更；只读检查使用GET状态。

切换到其他问题会暂停访谈的自动接答；`/interview` 可恢复。新问题撤销未完成草案的旧确认。访谈修改、数据身份变化或验证失败不能沿用旧草案确认。所有已完成的科研报告仍由 `/report` 回看。

## 设计内容与校验

访谈保存研究问题、CSV、响应、实验单位、设计、因素/水平或特征、数据来源、样本依据，以及原G2参数。新增必需字段 `unit_structure`：

- `independent_rows`：用户声明每行对应不同、独立且可交换的单位。
- `paired_units`：同一单位在两个条件下测量。
- `clustered` / `temporal`：标明当前不支持的聚类/时间结构，停止套用G2方法。

设计选项为 independent（Welch）、paired（配对t）、prediction（mean/OLS）。选择与单位关系不一致会阻止准备。此处是声明和结构检查，不是对真实独立性或随机化的证明，也没有新增功效计算、ANOVA、多重比较或CViT训练。

每个字段保留来源、轮次、引用原文。`protocol_default` 与 `user_structured`、`user_answer`、`user_grounded_model` 分开；模型提取代表有用户原文依据，不代表模型观察到了真实实验。

回答“不知道”会记录未知并停止准备；不补造事实、不反复询问同一未知项。补充明确字段后可以继续。冲突不会静默覆盖；`/resolve` 或 `/revise` 才接受明确解决或修订。缺失删除必须显式选择，配对删除整个单位。

验证报告 `design_validation_v1` 包含各检查的 `code/status/detail/fields`，状态为 `passed/blocked/unverified`。检查包括缺项、未知、冲突、单位关系、规格、数据身份、实际数值可解析性和工具预算。来源、独立性、随机化及样本依据标记为未独立验证。执行完成不等于科学假设成立，不按p值大小给学习奖励。

完整设计只触发既有 `prepare_tabular_experiment` 生成草案。`execution_authorized` 在访谈验证中恒为false；执行仍需原G2确认与宿主检查。每次访谈最多24轮；通用模型/工具限额沿用G1/G2，访谈文本问答不消耗数值工具次数，检查CSV与准备草案计入工具次数。

## LangGraph 与持久化

通用路由在需要时进入独立持久化图：

```text
collect_fields → verify_design → choose_action → present_decision
      ↑                  下一轮用户回复                  │
      └─────────────────────────────────────────────────┘
```

节点实现位于 `general/interview/runtime.py`；LangGraph checkpoint在会话的 `design_graph.sqlite`。跨轮事实保存为版本化状态，模型不需要重放全部聊天记录。

```text
<会话>/
  session.json                       # 当前访谈引用及状态哈希、共享限额
  design_graph.sqlite
  design_interviews/<访谈ID>/
    state.json                       # 字段、来源、未知、冲突、版本、验证、待回答问题
    turns/<轮次>.json                # 实际输入、更新、观察、动作、策略哈希、验证结果
  experiments/<G2实验ID>/             # 原G2数据快照、计划、数值节点、报告
```

状态/策略文件的重定向与身份变化会被拒绝。已提交轮次与工具结果保持原幂等机制；没有承诺跨所有文件写入的全局事务，非正常中断若造成状态哈希不一致会停止并要求检查，而不会猜测恢复。尚未建模外部GPU任务。

## 可学习环境和基线

`DesignDecisionEnv`提供 `reset/step` 的Gym式接口；策略只能看到公开字段完整度、缺项、冲突/未知、验证摘要和动作mask，模拟用户的隐藏事实与任务ID不进入策略观察。动作是询问某字段、展示设计选项、解决冲突、准备或停止，不包含训练脚本、shell或执行许可。

奖励 `design_reward_v1`：每步成本-0.1；模拟用户真实补齐一个字段/解决冲突+0.25；未知信息额外-0.2；合法完成设计+3；适当停止+1；非法动作-5并终止。它是决策环境的工程奖励，不衡量科学创新、显著性或真实用户满意度。准备只能在宿主mask允许时选择；实际权限、评估器和预算不由策略修改。

本轮实现了规则、合法随机和masked-softmax行为克隆基线：

- 训练240个模拟任务、1733条决策；开发60个任务、430条决策。
- BC训练240轮，仅按开发集动作一致率选第7轮权重。
- 训练/开发只有independent、prediction；90个paired模拟任务整族留出，不参与选择。
- 模拟演示标签来自规则参考，**不是已经收集到的真实专家标注**。
- BC权重：`models/design_interview_bc/policy.json`；版本、数据哈希、选择记录和结果在同目录。

| 留出指标（90个模拟任务） | 规则 | BC | 合法随机 |
|---|---|---|---|
| 设计就绪比例 | 90% | 90% | 90% |
| 正确停止比例 | 10% | 10% | 10% |
| 解决或适当停止比例 | 100% | 100% | 100% |
| 平均决策数 | 7.5111 | 7.5111 | 7.3111 |
| 非法动作 | 0 | 0 | 0 |

默认仍采用规则。相同就绪率和强动作mask表明当前模拟器较简单，不能据此声称学习优于规则或泛化科研能力已被证明。BC对参考规则动作的一致率约95.71%，该指标也不是科学设计正确率。

未训练PPO、未修改LLM权重、未更新原mean/ridge RL权重。后续应先增加真实专家标注、用户回答不确定性和会影响设计质量的决策，再比较RL与规则/BC，避免在已触顶的简单环境中继续堆训练。

## 专家轨迹和复现

实际访谈轨迹保留 `expert_action=null` 和 `annotation_status=unreviewed`。导出待审队列：

```powershell
# 在RUT_Science目录；输出文件必须尚不存在
& '.\.venv\Scripts\python.exe' -X utf8 scripts/export_design_review.py '<会话目录>' 'outputs/review_queue.jsonl'
```

队列含动作、公开观察与原轨迹哈希，等待专家填写判断、理由和审阅身份。评分反馈同样处于待审状态；本轮没有把用户评分直接作为训练奖励，也不自动导入尚未审查的标签。

重新训练BC需选择新的输出目录，保留已有版本：

```powershell
& '.\.venv\Scripts\python.exe' -X utf8 scripts/train_design_interview.py --output outputs/design_bc_reproduction --seed 21 --epochs 240
```

重核交付，不新增在线调用：

```powershell
& '.\.venv\Scripts\python.exe' -X utf8 scripts/verify_g2_1_delivery.py
```

真实API验收已保存，仅1次字段提取调用，632个供应商报告token；只提交合成示例的用户声明，无用户作业或论文数据。三种真实数值设计均通过多轮收集、确认、一步后暂停、新进程恢复、独立公式核对及完成后重复执行不新增成本。

最终全量回归280项：278通过、2因Windows文件符号链接权限跳过。详情见[本轮交付说明](../delivery/g2_1_update/README_本轮交付.md)。
