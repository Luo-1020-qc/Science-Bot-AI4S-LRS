# 50 个合成场景：可训练批次与已完成的 BC/PPO 训练

本批是 `rl_training_50_tasks` 的重新设计版本，保持 `tool_harness_rl_v2`、23 个候选动作、32 维特征和 `public_evidence_completion_v2` 不变。**50/50 场景预检通过，已完成一次覆盖全部任务的 BC→PPO 训练。**

全部内容为合成夹具。没有人类专家审批、真实先导观测或独立来源；不会修改当前在线默认策略。`expert_review.status=approved` 仅为现有导入接口所需的合成夹具兼容许可，reviewer 和 reason 已明确此含义，不能作为专家身份或科学合理性的证明。

## 数据和结果入口

| 文件 | 用途 |
|---|---|
| [tasks.jsonl](tasks.jsonl) | 50 个机器可读任务，全部 train |
| [tasks_展开注释.jsonc](tasks_展开注释.jsonc) | 与 JSONL 一致的展开审阅视图 |
| [50场景清单.md](50场景清单.md) / [scenarios.json](scenarios.json) | 每个场景的差异、预期行为、主要对比和预期终态 |
| [依据与争议.md](依据与争议.md) | 合成假设、功效尺度、来源与限制 |
| [tasks_imported.json](tasks_imported.json) / [预检证书](tasks_imported.preflight.json) | 现有 read_tasks 的扩展加载入口 |
| [reference_episodes.jsonl](reference_episodes.jsonl) | 50 条真实离线工具回放，502 个参考决策；不是 PPO 数据 |
| [bc_reference.jsonl](bc_reference.jsonl) | 脚本 BC 标签，真人审阅均 pending |
| [训练后权重](training_run_001/updated_policy.json) | 本次 BC 初始化后经 PPO 更新的 Actor–Critic 参数 |
| [训练报告](training_run_001/verification.json) / [训练集回测](training_run_001/training_task_evaluation.json) | 实际采样/更新及逐任务诊断 |
| [独立校验](verification.json) / [制品清单](release_manifest.json) | 概率、价值、奖励重算、旧文件保护与 SHA-256 |

## 50 个场景具体意味着什么

Darcy 26 个、CViT 24 个；完全随机两组设计 17 个、区组两组设计 17 个、区组 2×2 因子设计 16 个。

六种领域/设计组合各覆盖八种情形：合格初稿与零结果、错误模型、错误响应、可修复的初稿预算、旧复核失效、方差不可获得、新作业 OOM、已有作业复用。另有响应方向为 higher 的负误差分数，以及 0.90 功效目标两个任务。

因子任务还区分第一因素、第二因素、交互作用的预先指定对比。任务在非文本公开字段和模拟机制的组合上确实有 50 种差异，不靠改任务 ID 或提示词凑数。**初始 Actor 投影只有 36 种不同特征向量**；某些差异在后续工具反馈中出现，不能声称当前 Actor 理解了 50 类自由文本科研问题。

场景验收不仅看有没有结束：模型/响应/预算错误必须执行对应修复；失效复核必须重新核验；OOM 必须实际出现公开失败证据；复用场景必须对账并避免 run_mock；方差缺失必须询问后依据证据停止。参考回放共 38 条完成模拟闭环、12 条有依据停止（6 方差缺失、6 OOM）。

本批不声称支持 missingness_review、等效/非劣、跨分布评估、任意样本量重规划等尚未进入候选环境的能力。修复初稿预算仅恢复预先声明的可用上限，不代表增加实验重复或调整不可变的真实预算。

场景清单和 simulator 仅供宿主/审阅，不提供给策略。公开提示词不提前说明零效应、反向结局或将出现OOM；校验器还会反事实替换隐藏结局/未来作业失败，确认初始完整观察不变。

## 已执行的训练

- 脚本 BC：502 个决策，300 个 epoch；训练示范动作准确率 100%。这是对脚本标签的拟合率。
- PPO：固定 BC 初始化策略后重新随机采样，每任务 16 步，共 800 个 transition；4 个 epoch、52 次 minibatch 梯度更新。
- 所有 50 个任务均被采样；保存真实行为概率、critic、mask、观察、奖励、终止/截断和完整行为策略。
- 800 条概率/价值与奖励均独立重算通过。分任务采样片段的最后一步作外部截断并 bootstrap，不冒充业务终止。
- 更新后的贪心策略在同一 50 个训练任务上完成 50/50。**没有独立测试集，不证明泛化，也不证明 PPO 超过 BC 或规则。**
- 既有环境、奖励、工具源代码和历史权重保持不变；真实科学执行与模型 API 请求均为 0。

沿用旧 schema 中固定的 `source=fresh_on_policy_cpu_smoke` 字段，以确保原验证器可重算；本次规模和方法以训练报告为准。不能把该字段改成任意字符串后绕过版本校验，也不能把静态参考轨迹冒充 PPO 采样。

## 在项目根目录运行

```powershell
# 校验已交付的批次和首次训练，不重复训练
& '.\RUT_Science\.venv\Scripts\python.exe' -B 'Training_Data_Darcy_CViT/v2/synthetic_batch_050/verify.py'

# 新训练运行：重新初始化 BC，再执行 3 个 fresh PPO 批次（共 2400 步）
# 每个批次都保存其自己的行为快照；不会复用旧 rollout 冒充新采样
& '.\RUT_Science\.venv\Scripts\python.exe' -B 'Training_Data_Darcy_CViT/v2/synthetic_batch_050/train.py' --output training_run_002 --iterations 3 --steps-per-task 16 --bc-epochs 300

# 校验新的运行（--run 相对路径按当前项目目录解析）
& '.\RUT_Science\.venv\Scripts\python.exe' -B 'Training_Data_Darcy_CViT/v2/synthetic_batch_050/verify.py' --run 'Training_Data_Darcy_CViT/v2/synthetic_batch_050/training_run_002'
```

`train.py` 拒绝覆盖已有输出目录；该命令是从新 BC 初始化开始的独立实验，不是恢复旧优化器。正式断点续训需要另行实现优化器/RNG 状态恢复。`prepare.py` 只用于首次构建，已封存批次不可重复生成覆盖。

## 接入原训练加载器和读取权重

在 Python 中将 v2 目录加入 sys.path 后：

```python
from protocol import read_tasks, ROOT
from ppo_smoke import load_policy
import json
import torch

batch = ROOT / 'synthetic_batch_050'
ids = {json.loads(line)['task_id'] for line in (batch / 'tasks.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()}
tasks = [t for t in read_tasks('train', purpose='ppo', extension=batch / 'tasks_imported.json') if t['task_id'] in ids]
policy = load_policy(json.loads((batch / 'training_run_001/updated_policy.json').read_text(encoding='utf-8')))
# obs 来自 ToolEnvironment.reset()/step()，env 是同一个环境实例
# features = torch.tensor([env.features(obs)])
# mask = torch.tensor([[c['available'] for c in obs['candidates']]], dtype=torch.bool)
# with torch.no_grad():
#     distribution, value = policy(features, mask)
# action_index = int(distribution.probs.argmax(-1).item())
```

该权重用于固定的候选策略环境，不能直接当作 DeepSeek 权重或任意 LLM 工具调用模型加载。原 Science Bot 入口保持现有策略；本次不自动切换默认策略。
