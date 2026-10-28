# science Bot 通用项目工作区

> 2026-10-27 当前状态：G2.2/G2.3 已合并至 [统一研究模块](../research/strategy_learning/README.md)。该模块不作为对话工作区注册工具，也不改变 `-Workspace`、`.sciencebot/workspace.json` 或默认规则策略。当前完整能力与限制见 [阶段总结](../../阶段性总结2_2026-10-27.md)。下文保留工作区用法。

G2.1 更新：`/interview [CSV]`启动逐轮设计访谈，`/answer`补充字段，`/resolve`解决冲突，`/revise`明确修订。完整设计仍先生成G2草案再确认执行。见[G2.1说明](Science_Bot_G2_1_设计访谈与学习环境_zh.md)。

G2 更新：绑定工作区后，支持显式 CSV 的检查、独立/配对均值比较与 mean/OLS 预测设计执行。`/design <项目内JSON路径>` 可使用完整规格，无需模型调用；自然语言 API 规划发送列元数据。完整范围与隐私边界见 [G2 使用说明](Science_Bot_G2_表格与实验设计_zh.md)。

G1 更新：同一入口现已支持普通问答与显式文件问题的模型分析。`/read` 仍为本地读取；自然语言要求分析指定文件时，会在 API 模式下提交有限片段并返回来源引用。详见 [G1 使用说明](Science_Bot_G1_通用入口_zh.md)。

`--workspace` 将项目根目录与 Agent 安装目录分开。它不会调用 `os.chdir`；默认模型、DeepSeek 配置、数据集注册表和 RL 权重仍由应用管理。

## 使用

在 `LangGraph_RL_Agent` 目录运行：

```powershell
.\science-bot.cmd -Workspace "D:\Python Files\CityU_Project\MasterThesis_Project\AI4SD_FP\CViT_OFA_Darcy_2026_10_20"
# 离线启动同一项目
.\science-bot.cmd -Workspace "D:\Python Files\CityU_Project\MasterThesis_Project\AI4SD_FP\CViT_OFA_Darcy_2026_10_20" -Backend offline
```

也可以使用 Python 入口。在 `RUT_Science` 目录：

```powershell
& '.\.venv\Scripts\python.exe' -m rut_science science --workspace "D:\Python Files\CityU_Project\MasterThesis_Project\AI4SD_FP\CViT_OFA_Darcy_2026_10_20"
```

直接调用 `science-bot` 时，相对工作区路径相对于启动目录解析。PowerShell 包装器在切换到应用目录之前解析 `-Workspace`，因此 `-Workspace .` 仍指调用者的项目目录。指定目录必须已存在，拼写错误不会自动创建项目。

交互界面在真实终端中运行；无控制台的批处理使用 `--demo` 或 Python 会话接口。

项目中的状态结构：

```text
<project>/
  .sciencebot/
    workspace.json         # schema、稳定 workspace_id、规范根路径、读取策略
    sessions/
      <session-id>/
        session.json
        environment.json
        graph.sqlite
        jobs/
        report.json
        report.md
```

`--sessions` 显式指定时优先控制会话保存位置，路径继续相对启动目录解析；工作区身份仍绑定原项目。没有 `--workspace` 时保留旧会话目录和行为。

## 终端操作

```text
/workspace
/files *.py
/read cvit_static.py
/read "source folder/dynamic model.py"
```

`/workspace` 展示根目录、身份和状态位置。`/files` 最多返回 200 项，并限制扫描量，支持按项目相对路径匹配 glob。`/read` 展示 UTF-8 文本、字节数和文件哈希，单文件上限 128 KiB。读取命令保持本地，不自动把源文件提交到 DeepSeek，也不消耗科研 CU。

解析文件时同时核对命名路径和符号链接/junction 的最终路径；拒绝项目外的文件、凭据文件以及 `.git`、`.venv`、`.sciencebot` 等排除目录。目录遍历不跟随重定向目录。`.sciencebot` 自身不能通过 junction/symlink 重定向。二进制、大文件和终端控制字符交由专门工具处理。

默认 `.sciencebot/sessions` 及状态锁路径同样拒绝重定向；需要外部会话目录时由启动者显式指定 `--sessions`。

## 恢复

```powershell
& '.\.venv\Scripts\python.exe' -m rut_science science --workspace "D:\my-project" --resume <session-id>
# 完整会话目录同样可用，省略 --workspace 会读取会话原有绑定
& '.\.venv\Scripts\python.exe' -m rut_science science --resume "D:\my-project\.sciencebot\sessions\<session-id>"
```

会话保存 workspace_id、规范根路径和读取策略。恢复时核对现有配置；换项目、删除后重建身份、篡改配置都不能静默恢复。旧版无工作区的会话仍可按原目录恢复；为它额外指定 `--workspace` 会被拒绝，需要新建会话。

研究确认哈希额外绑定工作区身份。项目普通源文件的编辑不会改变 workspace_id；后续若科研工具使用这些文件或数据，需要再由工具/数据契约绑定具体输入哈希。

## 本地 API

```powershell
& '.\.venv\Scripts\python.exe' -m rut_science serve --workspace "D:\my-project"
```

服务由启动者绑定单个工作区，默认会话和独立本地令牌保存在该项目 `.sciencebot/sessions` 下。HTTP 客户端不能在创建请求里自行指定任意 `workspace` 路径；状态响应会显示服务绑定的项目。

## 代码结构与能力边界

- `science_bot/workspace.py`：路径、项目身份、目录浏览及受限文本读取。
- `science_bot/session.py`：默认会话位置、身份恢复与确认绑定。
- `science_bot/terminal.py`：`--workspace`、`/workspace`、`/files`、`/read`。
- `science_bot/api.py`：服务端工作区绑定。
- `Start-ScienceBot.ps1`：保留调用者目录语义的启动参数。

当前工作区是项目管理与文件访问层。CViT 训练、任意脚本执行、自动代码分析及新数据集仍需单独注册工具和契约；现有 mean/ridge 的 RL 动作目录保持原样，本次不需要重新训练权重。

本轮增量交付及 159 项测试记录见 `delivery/workspace_update/`；原始 v1 研究结果与压缩包不覆盖。
