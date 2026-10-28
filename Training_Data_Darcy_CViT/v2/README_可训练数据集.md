# v2：工具库对齐、可在线采样的Harness训练数据

日期：2026-10-28。当前数据入口为本目录；v1完整快照位于 [../v1](../v1/README_训练数据说明.md)。

本版把教学动作换成详细工具库的实际离线工具调用，提供任务库、可执行环境、参考轨迹、专家扩展流程、真实on-policy采样和PPO更新检查。**可以作为这套有界模拟环境的RL训练基础；不是任意科研任务的现成通用训练集，也没有部署新权重。**

优先阅读：[Darcy完整示例](examples/darcy_full_example.json)、[CViT完整示例](examples/cvit_full_example.json)、[专家交接手册](专家扩展数据库_交接手册.md)。

## 1. 本次从“参考JSON”推进到哪里

| 内容 | v1 | v2 |
|---|---|---|
| 动作 | ask / propose_design等教学名称 | plan_patch、plan_review、claim_check_plan、plan_freeze、result_analyze、claim_assess等真实离线工具及参数 |
| 环境 | 手写参考状态链 | reset/step/observe；实际调用固定工具，错误动作产生可检查失败 |
| PPO数据 | log probability和value均为null | 当前策略重新采样，保存实际值及行为策略快照并重算核验 |
| 专家扩展 | 字段说明与待审 | 任务模板、多个合理动作标注、来源防泄漏、导入、环境预检与训练加载 |
| 版本 | 教学协议 | 工具目录、环境、特征、候选动作和奖励版本明确绑定 |

当前12个任务：8训练、2开发、2公开评价示例。12条参考回合共有134个决策，86条训练分区BC参考标签，31条待审决策。全部参考标签仍是脚本来源，真人专家标签0。

## 2. 文件与用途

```text
v2/
  tasks/                  任务、公开目标、来源分组和私有模拟反馈
  episodes/               实际工具运行形成的参考轨迹，不能冒充PPO采样
  examples/               Darcy/CViT的完整展开例子
  labels/                 86条BC参考，来源和pending状态明确
  expert/                 待审队列、任务模板与扩展导入目录
  schemas/                任务、PPO transition、审阅字段schema
  tool_catalog.json       45项契约快照、候选调用与实现状态
  tool_runtime/           工具库副本；仅在本目录写模拟制品
  environment.py          运行实际工具的模拟环境
  protocol.py             版本、来源、动作、特征、奖励及加载约束
  expert_import.py        专家任务与决策审阅导入
  preflight.py            新任务在工具环境中预检
  ppo_smoke.py             新采样、行为概率重算、GAE和PPO更新
  ppo_smoke/              已执行的64条在线采样与行为/更新后JSON权重
  validate.py / tests/    数据、RL协议与专家边界检查
```

工具副本通过清单固定来源，仅对只读DOE适配器的项目根定位作迁移适配。G2.4冻结数学代码复用不改写；主science Bot、详细工具库原目录和已有权重不变。

## 3. 训练单位与公开/私有边界

Task envelope含`task_id/policy_split/root_group/data_lineage/public/simulator/expert_review`。

- `public`保存用户目标、单位、因素水平、指标、方差来源和约束。
- `simulator`保存初始缺陷、模拟结果情景、用户无法回答、已有作业和模拟OOM，只供环境使用。
- 策略只接收`observe()`的结果，不接收整个任务、分区、来源组、初始缺陷或隐藏结果情景。
- `job_run_mock.scenario`属于宿主参数，策略只看到`{"$host":"private_mock_fixture"}`；不能选择benefit来刷正结果。
- `data_lineage`同时记录策略任务来源祖先和科学实验内部train/validation/test引用；同一底层来源不能跨策略分区。

训练特征为32维公开状态投影，不编码任务ID、来源身份或期望动作。23个候选动作采用真实工具名与绑定参数，其中`host.ask_user`和`host.stop_with_evidence`是明确版本化的环境交互控制，不冒充工具库中尚未实现的问答工具。

mask只约束已登记引用、权限和当前可调用条件；四种模型修订选项仍同时可选，错误模型需由verifier判断。引用前置关系确实减小了学习难度，不能把它当作策略已经学会任意工具规划的证据。

## 4. 当前策略学习的范围

动作候选中的参数由公开目标与已有制品绑定，模型学习工具选择、顺序、有限参数修正和停止。这是有限离散候选策略，**不包括任意Python/JSON参数生成，也不是LLM文本级PPO**。

任务覆盖错误模型、响应指标不一致、预算不足、旧复核失效、方差依据缺失和已有作业复用。每次修改生成新方案，旧复核/冻结不能直接沿用；模型不能修改检查结果、真实权限或模拟结局。

`report_build`完成后仅表示“模拟研究闭环完成”；reward不因得到正向、零效应或相反结果而改变。正确的阴性报告同样可以成功。不确定结果不会自动加样本直到显著。

## 5. 三种数据必须分开使用

**任务库**可反复供环境reset使用，前提是训练只读训练分区。

**专家/脚本示范**用于BC、行为诊断或适当的偏好/离线方法。`episodes/`中行为概率和value仍为null，`ppo_eligible=false`；不能补造数值再当作PPO数据。

**PPO rollout**来自当前行为策略的真实随机采样。本版记录并可重算：

```text
任务/环境/工具/奖励版本
行为策略hash与完整参数快照
公开观察、公开特征、候选参数和mask
采样action_index、behavior_log_probability、value_estimate
真实环境feedback、reward、next_observation、next_value_estimate
terminated、truncated、episode_index
```

log probability是“选择这个带已绑定参数的候选项”的概率，不是整段自然语言或任意参数生成的概率。它必须与保存的行为策略、mask、特征和动作一致。

PPO按采样—更新交替；一次更新完成后的下一批必须重新采样，不能把旧静态示范反复当作新on-policy样本。[PPO原论文](https://arxiv.org/abs/1707.06347)

GAE区分两类结束：业务决策预算耗尽是已声明任务的terminal；外部截断保留最终状态bootstrap，并切断到下一reset回合的lambda递推。真正terminal不bootstrap。采样批次末尾不伪造环境终止。[Gymnasium终止与截断](https://gymnasium.farama.org/tutorials/gymnasium_basics/handling_time_limits/)

## 6. 奖励与验收

使用统一`public_evidence_completion_v2`：

- 完成当前版本的复核、对齐、冻结、工作流核验、对账、模拟分析、结论复核和报告：终局+10。
- 当前公开证据证明方差依据无法获得或当前模拟资源失败：合理范围内停止+10。
- 无依据停止−10；错误调用−1；每步−0.02。
- 复核通过、对齐、冻结、工作流检查、对账、分析与结论检查，只对首次达到的里程碑各+0.2，不能反复刷奖励。
- 方差未知时，模板中的默认值不能替代来源，复核和冻结被阻断。

同一个环境和评分函数用于训练、开发与公开评价，分区不会切换成功口径。它只评价这套协议闭环，不构成专家科学合理性的最终评分；仍需人类审阅奖励及停止语义。

## 7. 已执行的RL机械检查

已用CPU初始化的小型actor-critic新采样64个transition，保存真实log probability/value与初始参数，再进行1个PPO批次、2个epoch、4次minibatch梯度更新。行为概率与critic值均已重算匹配，更新前后参数哈希不同。

结果见 [PPO检查](ppo_smoke/verification.json)。这64步单独记为smoke训练，不计入正式科研训练预算，也不声称成功率、效率或泛化能力提高。没有LLM API、真实Darcy拟合或CViT/GPU训练。

## 8. 操作命令

在 `LangGraph_RL_Agent` 根目录执行：

```powershell
# 数据、环境接口、专家边界和PPO记录核验
& '.\RUT_Science\.venv\Scripts\python.exe' -B 'Training_Data_Darcy_CViT/v2/validate.py' --tests

# 另采样一批，仅用于机械验证；不覆盖已有ppo_smoke目录
& '.\RUT_Science\.venv\Scripts\python.exe' -B 'Training_Data_Darcy_CViT/v2/ppo_smoke.py' --steps 64 --output 'D:\Python Files\CityU_Project\CityU_Hackathon_AI4S\LangGraph_RL_Agent\Training_Data_Darcy_CViT\v2\ppo_smoke_next'
```

专家扩展后按交接手册依次执行import、preflight，再通过`--extension`加入训练加载器。当前smoke工具限制8～256步，正式多批训练、选模和独立最终集仍需另设研究版本。

12个示例与答案均公开，分区共享合成机制，真正盲测数量0。增加数量前，应先由专家补充独立来源、机制组合、合理替代动作和争议案例；后续另封存最终评测。
