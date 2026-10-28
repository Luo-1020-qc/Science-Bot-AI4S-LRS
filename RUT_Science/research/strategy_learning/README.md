# Harness策略学习研究

研究模块保留G2.2／G2.3／G2.4的有效源码、任务库、模型、原始结果与回归测试。阶段交付说明已合并到[PROGRESS](../../../docs/PROGRESS.md)，交互命令见[USAGE](../../../docs/USAGE.md)。历史交付快照与测试输出已移出主目录，不作为当前依赖。

| 研究 | 保留目录 | 任务与结果 |
|---|---|---|
| G2.2 | `studies/g2_2/` | 训练／开发／最终任务192/64/96；BC20.83%，规则100% |
| G2.3 | `studies/g2_3/` | 240/90/96；公开证据严格评分BC11.81%、BC+PPO6.25%、从零PPO0% |
| G2.3修订 | `studies/g2_3/experiments/feedback_v2/` | 新48项最终任务；聚合基线60.42%、加PPO43.06%、规则100% |
| G2.4 | `studies/g2_4/` | 84/42/42；开发42/42符合脚本预期，非真人准确率；42条待审 |

这些是各自合成机制下的冻结研究结果，不能跨测试集直接比较或外推为真实科研能力。真人专家标签仍为0，默认在线访谈rule，研究策略仅显式推理，不默认推广。

在项目根目录运行：

```powershell
& '.\RUT_Science\.venv\Scripts\python.exe' -B 'RUT_Science/scripts/science_bot_research.py' list
& '.\RUT_Science\.venv\Scripts\python.exe' -B 'RUT_Science/scripts/science_bot_research.py' test
& '.\RUT_Science\.venv\Scripts\python.exe' -B 'RUT_Science/scripts/science_bot_research.py' verify
```

各轮在独立进程中运行；当前测试日志与保护报告写入study/evidence。`online_artifacts.json`与主仓库`docs/cleanup/2026-10-28/protected_current.json`核验冻结研究、架构与权重。旧迁移清单是历史证据，不再要求复制旧delivery或弃用训练数据v1。

研究写入边界和真实工具禁用保持不变。`reference_copy`中的必要源文件与CSV仍被来源检查／回归测试引用，不能作为重复交付盲删。正式新研究需另设版本、预算、独立来源和选模协议，不覆盖现有权重。
