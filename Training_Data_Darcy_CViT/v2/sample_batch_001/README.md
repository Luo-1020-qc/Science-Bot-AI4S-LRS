# 可直接运行的RL示例批次：Darcy与CViT

批次：`sample_batch_001`；格式：`tool_harness_rl_v2`。包含3个合成训练任务，复用现有工具环境与动作协议。**已通过任务导入、环境预检，并仅在这3个任务上实际采样96步、完成1个CPU PPO批次更新。**

这是一份可执行的数据交付样本。它不含真实Darcy数组或CViT训练结果，真人专家标签为0，未证明策略改进。自动生成的任务、脚本示范、PPO新采样分开存放。

## 先看什么

| 文件 | 内容与使用方式 |
|---|---|
| [tasks.jsonl](tasks.jsonl) | 3个完整任务，每行一个JSON对象 |
| [Darcy任务](tasks/sample001_darcy_block_repair_v1.json) | 易读版：遗漏区组模型→复核→修正→模拟结论 |
| [CViT任务](tasks/sample001_cvit_interaction_repair_v1.json) | 易读版：架构×学习率，需要交互模型 |
| [停止任务](tasks/sample001_cvit_variance_unavailable_v1.json) | 方差缺失→询问→用户无法提供→有依据停止 |
| [tasks_imported.json](tasks_imported.json) | 现有v2训练加载器可读取的任务扩展 |
| [预检证书](tasks_imported.preflight.json) | 绑定任务、工具、环境与奖励协议 |
| [reference_episodes.jsonl](reference_episodes.jsonl) | 实际工具执行生成的30个参考决策；log probability与value为null |
| [bc_reference.jsonl](bc_reference.jsonl) | 30条脚本BC参考，均标pending，不伪装专家批准标签 |
| [decisions_pending.jsonl](decisions_pending.jsonl) | 3条新状态的待审记录；当前全局决策导入器尚未注册这些ID |
| [设计依据](design_rationale.md)／[来源说明](sources.md)／[审阅记录](review_log.md) | 供专家理解与接手 |
| [PPO采样](ppo_run_001/rollout.jsonl) | 96条当前行为策略实际采样；每个任务32条 |
| [更新后权重](ppo_run_001/updated_policy.json) | 保存本次本地策略更新；未替换在线默认策略 |
| [PPO结果](ppo_run_001/verification.json)／[批次验收](verification.json) | 概率、critic值、状态链与训练兼容性证据 |

## 审批字段的准确含义

任务的`expert_review.status=approved`用于兼容当前批准任务扩展加载器；reviewer明确为`automated_synthetic_fixture_author_NOT_A_HUMAN_EXPERT`，reason明确仅批准作为合成兼容性夹具。**这不表示真人完成科学审批。**本批次不得计入真人标注库或科学设计准确率。

若专家接手，应核实问题、单位、设计、来源及假设，使用真实身份和理由形成新的版本化任务与批次，再执行正式导入。不能只把reviewer字符串改成人名而不审阅。待审决策属于本批次新状态，需工程侧扩展已登记队列后才能用现有全局决策导入器导入；这里不声称标签已经接入BC训练器。

## 直接进入现有训练加载器

在项目根目录执行下面的独立示例训练脚本。它调用现有`read_tasks(..., extension=...)`，按本批task_id筛选，保证3个任务都参与采样，不混入原来8个任务的记录。

```powershell
# 核验已交付的数据、PPO概率和值，不重复训练
& '.\RUT_Science\.venv\Scripts\python.exe' -B 'Training_Data_Darcy_CViT/v2/sample_batch_001/verify_sample.py'

# 再运行一批96步；输出必须使用新目录名，不覆盖已有证据
& '.\RUT_Science\.venv\Scripts\python.exe' -B 'Training_Data_Darcy_CViT/v2/sample_batch_001/train_sample.py' --output ppo_run_002
```

训练使用32维公开特征、23个已绑定参数的候选动作、CPU actor-critic。每个任务采样32步；块末未终止的回合标为外部truncated并保留bootstrap。每次终止重新reset。PPO使用clip 0.2、gamma 0.99、GAE lambda 0.95、学习率0.0003、2个epoch和32条minibatch，共6次梯度更新。

脚本会重新预检以适配当前源码哈希。旧rollout不作为新on-policy批次继续反复使用；`ppo_run_002`会重新初始化并采样，用于复跑机械兼容性示例，不是从001接续正式训练。

## 当前样本能训练什么

可用于学习工具选择、顺序、有限模型修正、复核和停止；可作为后续专家任务的格式示例。它不训练DeepSeek参数，不生成任意工具参数，不自动扩充真实科学数据，也不进行正式多轮选模。3个任务沿用训练来源A，不能算成3个新独立来源，更不能用于证明泛化。

本批次新增文件位于独立目录，随项目Git仓库交付；基础v1／v2数据、冻结权重及在线入口未改动。本地API key仍由Git忽略。
