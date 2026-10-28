# G1 通用入口与工具内核交付

日期：2026-10-22。G1 已完成，采用现有项目内源码、文档和验收证据交付；保持 `science-bot.cmd` / `Start-ScienceBot.ps1` 入口，不新增 ZIP。

## 当前行为

- 默认启动 `general_v1` 通用会话，未选择科研任务时不创建 generated 环境、不加载 Darcy 数据或 RL 权重。
- 普通知识问题直接问答；项目问题使用原生 `tool_calls`，由宿主注册、校验和执行 `project_list` / `project_read`。
- 文件内容回答绑定实际读取的路径、行号和哈希；目录列表不能支持文件内容结论，文件列表也不自动授予读取权限。
- 明确的 generated 回归和 Darcy 压力场任务经注册适配器创建草案，沿用原确认、预算、科研执行、暂停恢复与独立评价。
- 未知任务、非注册目标/方法、非法或冲突预算，以及当前未支持的超参数修改，不再静默映射到默认实验。
- 新问题撤销未完成草案的旧确认；已经完成的科学报告保留。
- 普通知识、文件问答与数值引擎共用模型请求/token 账本与历史编号；旧会话按旧引擎恢复。
- HTTP 状态、事件与取消在等待模型时保持可访问；重复幂等请求及已记录失败不会重复消耗模型调用。
- `/read` 保持本地；`/model-output` 保持只读回看。

## 使用

在 `LangGraph_RL_Agent` 根目录：

```powershell
.\science-bot.cmd
.\science-bot.cmd -Workspace 'D:\my-project'
```

示例输入：

```text
什么是区组设计？请用两句话回答。
列出项目文件。
请阅读 dynamic_cvit.py，解释模型结构并引用文件行号。
运行 generated 回归实验，预算6，门槛0.20。
/confirm
/report
/model-output list
```

文件问题需要通过 `-Workspace` 绑定对应的已有项目。API 模式下，明确选择文件进行分析意味着把有限片段提交给模型；`/read` 不外发。

完整范围与接口见 [G1 使用说明](../../docs/Science_Bot_G1_通用入口_zh.md)。

## 验证结果

| 项目 | 结果 |
|---|---|
| 完整回归 | 223 项，221 通过、2 跳过 |
| 跳过原因 | Windows 账户无文件符号链接权限；已有目录 junction 检查仍执行 |
| 真实终端 | 现有 CMD 入口完成普通问答、原生文件读取、数值草案与确认、执行、后续问答、拒绝未知目标、新进程历史回看 |
| 真实模型调用 | 6 次：通用问答 → 文件调用/回答 → 数值候选/解释 → 通用问答 |
| 供应商报告用量 | 输入 4114、输出 1917，合计 6031 token；金额未配置 |
| 文件证据 | 实际读取 fixture `model.py` 第1–9行，返回文件哈希与对应引用 |
| 实时数值实验 | generated 成功，封存相对 L2 为 0.05678283862595852 |
| 离线数值恢复 | generated、Darcy 均完成一行动后暂停，新进程恢复并成功结束；封存评价各一次 |
| 不重复执行 | 完成后重复运行未新增实验；历史回看未增加请求/token/通用工具消耗 |
| 旧会话兼容 | 原模型输出交付的真实数值会话可恢复，旧证据文件哈希未改变 |
| RL | 沿用原权重，未重新训练 |
| 凭据检查 | 新增证据中未发现实际 API 密钥 |
| 分发 | 无新增 ZIP |

本轮初次完整回归发现 Windows 上 HTTP 提前拒绝未读 POST 请求体可能导致连接中断。已修复并重新通过完整回归；`tests_initial_failure.log` 保留初始失败，`tests.log` 为最终全量结果。`tests_before_final_route_guards.log` 保存增加最后两项协议约束测试前的通过批次。

## 证据索引

- `verification.json`：逐项检查、真实用量、旧会话兼容、最终源码哈希和限制。
- `tests.log`：最终 223 项完整测试。
- `offline_verification.json`、`offline_sessions/`：无默认实验、拒绝/澄清、真实本地数值与跨进程恢复。
- `sessions/b1ca426dc1e54da9918bfb9547c5d95c/`：真实 API 会话、原生调用 ID、工具结果、消息轨迹及实验子目录。
- `fixture_project/`：专用合成源码 fixture；`.sciencebot/sessions/` 保存默认入口离线启动证明。
- `terminal_replay.txt`：同一显示函数从已保存真实返回生成的纯文本重放，不是 PTY 原始录像。
- `source_snapshot/`：本轮相关实现、测试、使用文档和既有入口快照。

只重核已保存证据、不新增在线调用：

```powershell
# 在 RUT_Science 目录
& '.\.venv\Scripts\python.exe' -X utf8 scripts/verify_g1_delivery.py
```

首次重核会执行小规模离线数值恢复检查；其记录已生成后复用保存证据，不重复训练。

## 范围与后续

路由是保守的宿主规则，模糊表述会要求澄清。引用检查验证读取范围、文件身份与引用覆盖，不证明每项自然语言结论均正确。真实 API 验收仅覆盖一个合成文件 fixture 与一个 generated 实验，不构成广泛泛化效果研究。

G2 的 CSV/统计实验设计执行、G3 的 CViT GPU 训练，以及源码编辑、任意 shell、联网搜索仍未实现。下一步应接入表格数据工具与独立实验设计协议，不扩大旧 RL 行动枚举来假装获得新场景能力。
