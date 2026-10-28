# G2.2 / G2.3 / G2.4 研究接口上线交付

日期：2026-10-27。已将三轮研究接口接入现有 `science-bot.cmd` 和本地HTTP消息路由，保留原启动文件，不新增ZIP。

完整命令见 [研究接口使用说明](../../docs/Science_Bot_研究接口上线_zh.md)。在science Bot聊天中先输入：

```text
/research
/doe demo
/research simulate g2_3
```

| 能力 | 上线范围 |
|---|---|
| G2.2 | 冻结结果、制品核验、规则/BC的开发模拟、待审副本导出和审阅验证 |
| G2.3 | 严格审计结果、规则/BC/两种PPO及修订策略的开发模拟和同场景比较、CViT作业对账/恢复模拟 |
| G2.4 | 三种DOE模板、固定需求与草案验证、反馈演示、输入变更复核、待审副本导出和审阅验证 |
| 主会话 | 研究工具注册、路由与命令、结果持久化、哈希校验、状态及报告、共享预算 |
| HTTP | 原messages/status/report接口，认证和幂等机制保留；确认与恢复不能运行真实实验 |

默认访谈保持规则。研究学习权重只在显式选择的开发模拟中进行CPU前向推理，不作为正式任务策略；不提供在线训练、重新选模或封存任务执行接口。没有真实实验工具、DeepSeek请求或GPU作业。

宿主通过只读子进程桥接固定研究操作。冻结研究源码、模型、任务、原始结果和队列保持原样；研究输出仅写入会话。新加入的极端数值阻断在桥接层实现，未修改G2.4冻结验收器。

验收证据：

最终结果：集成与兼容测试54项中53项通过、1项Windows符号链接权限跳过；原研究39＋37＋49＝125项全部通过。2,034个受保护文件按授权清单核对，其中575个原研究文件逐字节保留；78个在线研究依赖制品已固定身份。当前8份文档的89个本地链接无断链。

- [tests.json](tests.json)、[tests.log](tests.log)：专门交付测试目录，复制兼容性测试并新增终端、HTTP、真实桥接进程和边界测试；输入使用临时项目与合成数据。
- [verification.json](verification.json)：本次总验收、制品与启动入口完整性。
- [authorized_source_changes.json](authorized_source_changes.json)：用户授权的6个宿主源码修改及哈希；可用原版备份保存在`source_before/`。
- [protected_before.json](protected_before.json)：原研究与应用受保护清单；配置仅保留哈希。
- [entry_acceptance.json](entry_acceptance.json)：从现有会话接口实际运行并恢复的研究结果。
- `historical_before/g2_4_verification.json`：接入前隔离验收快照，保留原“应用未改动”结论的时间范围。

G2.4的冻结`run.py verify`仍描述原隔离基线。当前应用已按授权改动，使用统一研究脚本的`verify`，它调用当前兼容审计；不要将原“整个源码未变化”验收继续当成当前上线条件。旧独立交付报告保留为历史证据。

本次验收入口（项目根目录）：

```powershell
& '.\RUT_Science\.venv\Scripts\python.exe' -B 'RUT_Science/delivery/research_online_update/run_checks.py'
& '.\RUT_Science\.venv\Scripts\python.exe' -B 'RUT_Science/scripts/science_bot_research.py' test
& '.\RUT_Science\.venv\Scripts\python.exe' -B 'RUT_Science/scripts/science_bot_research.py' verify
& '.\RUT_Science\.venv\Scripts\python.exe' -B 'RUT_Science/delivery/research_online_update/verify_delivery.py'
```

当前仍有0个已独立核验的真人专家标签，DOE通过仅表示可审阅，模拟指标不能作为真实实验精度。下一步应进行专家审阅与独立任务验证，再决定新一轮策略训练。

持久化验收曾暴露Windows长路径限制，已将研究目录名缩短为请求哈希前16位，完整哈希仍在记录中校验；失败试验会话保留在acceptance_sessions中用于溯源，成功会话由entry_acceptance.json明确引用。
