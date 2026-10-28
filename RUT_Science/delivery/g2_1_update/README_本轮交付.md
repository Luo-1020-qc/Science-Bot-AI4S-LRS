# G2.1 设计访谈与可学习决策环境交付

日期：2026-10-22。已完成 G2.1，沿用现有 `science-bot.cmd` 和 `Start-ScienceBot.ps1`；不新增ZIP、不升级依赖、不改原数值RL权重。

## 当前新增行为

- 多轮实验设计访谈，逐轮累计明确字段，保留来源、原文、轮次和设计版本。
- 下一问针对当前缺项；展示设计选项及前提；“不知道”不被补造，冲突不静默覆盖。
- LangGraph显式执行收集、验证、策略选择、展示四个节点，使用独立SQLite checkpoint。
- 固定验证报告区分passed、blocked、unverified；列结构检查不证明真实随机化和独立性。
- 完整访谈经原G2工具准备草案；仍需 `/confirm` 执行，策略不能增加权限或跳过预算。
- 实际决策轨迹及专家待审队列；用户评分进入待审记录，不自动训练。
- 可学习的决策模拟环境、规则和合法随机基线、真实训练并保存的BC策略。

本轮没有训练PPO，没有更新LLM权重；BC属于模仿学习。默认仍使用规则，因为留出模拟任务尚未显示BC的优势。完整使用及设计边界见[G2.1说明](../../docs/Science_Bot_G2_1_设计访谈与学习环境_zh.md)。

## 体验

在 `LangGraph_RL_Agent` 根目录：

```powershell
.\science-bot.cmd -Backend offline -Workspace 'RUT_Science\examples\g2'
```

进入后逐行输入；前两个 `1` 分别选择独立单位关系和独立两组设计：

```text
/interview two_groups.csv
/answer 比较A组与B组的平均y
1
1
/answer {"response":"y","unit":"id","factor":"group","levels":["A","B"],"provenance":"synthetic","sampling_note":"全部现有合成样本，探索性演示"}
/confirm
/report
```

其他常用操作：`/interview-status`、`/interview-options`、`/resolve {字段JSON}`、`/revise {字段JSON}`、`/interview-refresh`、`/interview-policy bc`。切换到普通问题后用 `/interview` 恢复；新设计和数据变化不能使用旧确认。

## 验收

| 项目 | 结果 |
|---|---|
| 完整回归 | 280项，278通过、2个Windows文件符号链接权限相关跳过 |
| G2.1新增测试 | 28项，覆盖来源、未知、冲突、候选、预算、误执行、恢复、HTTP、学习环境及权重校验 |
| 真实数值场景 | independent、paired、prediction均通过多轮收集、确认、暂停、新进程恢复和独立重算 |
| 预测实验 | BC访谈策略准备mean/OLS比较，测试MSE=0.07063582068357449；成功提交测试一次 |
| 真实模型 | 1次原生record_design_fields调用，632 token；用户声明“这些测量来自合成数据”被有原文依据地记录 |
| 真实终端 | 原CMD入口完成逐轮回答、选项、草案、确认、报告、模型回看及退出；离线0次模型调用 |
| 重复执行 | 完成后重复run没有新增工具次数；在线历史回看没有新增模型成本 |
| 默认与边界 | 不隐式启动generated/Darcy；未知事实停止；无执行授权时阻止run |

实际实验与模拟环境分开报告。三个真实CSV都是G2专用合成数据，不涉及用户作业、论文数据或GPU训练。

## 学习结果及其限度

BC使用masked-softmax分类器，在规则参考轨迹上训练240轮。训练240个任务/1733条决策，开发60个任务/430条决策；仅根据开发集动作一致率选择第7轮，策略哈希及数据哈希已保存。

配对任务整族留出90个，不进入训练或开发；含9个无法给出样本依据的模拟用户。规则、BC与合法随机均有81个设计就绪、9个正确停止，非法动作均为0。规则/BC平均7.5111次决策，随机7.3111次。BC对规则动作一致率95.71%。

因此，本轮证明决策训练、保存、加载、观察隔离和部署约束的流程可运行，**不证明BC优于规则，也不证明广泛科研泛化**。模拟器较简单、宿主mask约束较强；继续强化前需要增加真正影响设计质量的选择、真实专家标注及用户反馈。没有把“生成正确规格”等同于“科学实验有创新或结论成立”。

规则参考标签明确标为 `rule_reference_not_human_expert`。实际轨迹 `expert_action` 保持null，专家队列状态为待审，未伪造专家反馈。奖励与p值、显著性、测试误差大小无关；权限、预算、评估器不开放给学习策略修改。

## 文件与复现

- `verification.json`：总体验收、用量、源文件哈希和限制。
- `tests.log`：最终全量回归。
- `offline_verification.json`、`offline_sessions/`：真实三种数值任务及未知停止场景。
- `live_verification.json`、`live_session.json`、`live_sessions/`：一次真实原生字段提取与数值闭环。
- `expert_review/`：实际访谈决策的待审队列，需从trace_ref回到原记录核对上下文。
- `terminal_acceptance.json`、`terminal_replay.txt`：实际CMD入口输入与保存状态展示重放；后者不是PTY原始录像。
- `bc_baseline/`：BC权重、manifest、任务清单、训练曲线及规则/BC/随机比较结果。
- `source_snapshot/`：本轮相关最终源码、测试、文档和原入口快照。
- `../../models/design_interview_bc/`：运行时内置BC策略，以及完整训练/开发参考轨迹。

在 `RUT_Science` 目录复核，不新增在线调用：

```powershell
& '.\.venv\Scripts\python.exe' -X utf8 scripts/verify_g2_1_delivery.py
```

第一次复核执行小规模离线验收，后续重核缓存证据。`--live`仅在显式指定且不存在保存证明时调用模型；已存在未完成在线请求则拒绝自动重发。

训练复现到新目录：

```powershell
& '.\.venv\Scripts\python.exe' -X utf8 scripts/train_design_interview.py --output outputs/design_bc_reproduction
```

下一阶段先建设人工审阅的设计任务集与更有区分度的模拟器，再做规则、BC、PPO的公平比较；不以继续增加训练步数替代评估。
