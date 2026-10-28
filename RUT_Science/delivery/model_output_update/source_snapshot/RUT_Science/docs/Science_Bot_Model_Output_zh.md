# science Bot 模型输出展示与历史回看

日期：2026-10-21。直接更新现有安装，保持 `science-bot.cmd` / `Start-ScienceBot.ps1` 入口，不新增分发压缩包。

## 使用

仍在 `LangGraph_RL_Agent` 目录启动：

```powershell
.\science-bot.cmd
# 可继续指定项目工作区
.\science-bot.cmd -Workspace 'D:\my-project'
```

API 模式下，输入科研需求后会显示当次实际模型返回，包括角色、调用编号、模型名和保存位置。需求确认、实验选择和报告等行为沿用原协议。

```text
/model-output
/model-output list
/model-output 1
```

- `/model-output`：显示最近一次调用的保存结果或失败状态。
- `/model-output list`：列出当前会话的调用编号、角色、模型和校验状态。
- `/model-output 1`：显示编号 1 的结果；`0001` 等补零编号同样可用。

回看只读当前会话的编号输出文件，不发送模型请求，不增加 CU、token 或调用次数，不修改科研账本。恢复已有会话后仍可使用。编号来自会话内共享请求账本，各角色使用同一编号序列。

## 自动展示的内容

| 角色 | 终端显示 |
|---|---|
| 需求理解 `intake_v2` | 提取字段、缺项、冲突、澄清问题 |
| 候选提议 `candidate_generator_v1` | 实际候选及未解决项 |
| LLM 行动选择 `llm_selector_v1` | 实际 action_id、reason 和证据引用；只在使用 LLM planner 时产生 |
| 报告解释 `report_explainer_v1` | summary、findings、limitations 和工件引用 |

默认 `planner=rl` 的行动仍由本地权重决定，行动事件明确显示 planner 来源；界面不会为 RL 动作补造 LLM 理由。`--backend offline` 没有新大模型输出；空历史时会明确提示。

这些内容是供应商返回文本经解析后的应用层 JSON，界面按字段展示实际值，不另发请求进行改写或润色。它不是完整 HTTP 响应、流式输出或隐藏推理记录。

## 模型提议与宿主检查

收到符合顶层格式的输出后先显示“模型提议 · 待宿主校验”；后续单独通知宿主检查结果。

| 状态 | 含义 |
|---|---|
| 待宿主校验 | 只通过顶层格式检查，尚未完成业务检查 |
| 宿主契约检查通过 | 需求来源、候选域、行动引用或报告解释的相应检查通过；不代表所有语义事实均已证明 |
| 需要补充信息 | 模型提出缺项或冲突，尚未授权执行 |
| 宿主拒绝 | 返回已保存，但被来源、参数、引用或解释检查拒绝 |
| 输出格式错误 | 未满足结构化返回契约；若能解析则保留其实际 JSON，不能解析则仅保存失败状态 |
| 模型调用失败 | 服务或连接失败，未制造替代模型回复 |
| 历史输出 | 老会话没有独立校验状态，保守显示“未记录宿主校验状态” |

科研结论继续以宿主 `report.json` / `/report` 为准。解释检查失败会明确提示，已完成的数值实验与科研报告仍可查看。

## 文件与显示边界

当前会话新增或复用：

```text
model_calls/0001_response.json    # role、request_index、model、response 与 response_hash
model_calls/0001_status.json      # 同编号的宿主校验/失败状态
events.jsonl                     # model_output、model_validation 等事件
```

旧版只有 `role`、`response`、`response_hash` 的返回文件仍可回看。读取时核对输出哈希、限制单文件 512 KiB，并拒绝重定向路径；不会读取请求文件或认证头。哈希用于一致性检查，不是防篡改签名。

显示采用纯文本：Rich 标记保留为字面文字，终端控制字符和方向控制符转义为可见字符串。文件引用只用于展示。现有 `/read` 继续只在本地显示项目文本，不自动提交给模型。

## 验证位置

测试：`tests/test_model_output.py`。本次增量验收：`delivery/model_output_update/`，与历史产品验收分开保存。当前项目入口、RL 权重、训练协议和既有科学评分保持原语义。

本轮完整回归 171 项：170 通过、1 项因 Windows 文件符号链接权限跳过。现有入口的真实终端验证完成了 3 次 API 调用，共 4111 个供应商报告 token；退出并恢复后回看未增加资源消耗。[本轮交付记录](../delivery/model_output_update/README_本轮交付.md) 包含逐项验收与证据索引。
