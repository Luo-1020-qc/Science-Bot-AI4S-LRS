# science Bot 工作区更新

本机源码已更新。此目录保存本轮增量验证，原始 v1 压缩包和科研结果保持原记录。

新增功能：

- Python/console 入口：`--workspace <现有项目目录>`。
- PowerShell/CMD 包装器：`-Workspace <现有项目目录>`；相对路径按调用者目录解释。
- 默认状态目录：`<project>/.sciencebot/sessions`；显式 `--sessions` 可覆盖存储位置。
- `/workspace`、`/files [glob]`、`/read <UTF-8 文本路径>`，读取保持本地。
- 工作区身份纳入科研确认和会话恢复校验；旧版会话保持兼容。
- 本地 HTTP 服务可由启动者绑定工作区，客户端不能传任意项目路径。

示例（在 LangGraph_RL_Agent 目录）：

```powershell
.\science-bot.cmd -Workspace "D:\Python Files\CityU_Project\MasterThesis_Project\AI4SD_FP\CViT_OFA_Darcy_2026_10_20"
```

本轮全套测试：159 项，158 通过、1 跳过。跳过项是需要 Windows 额外权限的文件符号链接测试；目录 junction 的越界、状态目录重定向及默认会话目录重定向均已实测通过。

真实交互测试使用含中文和空格的独立 fixture 项目，验证包装器 `-Workspace .`、三个文件命令和按原会话 ID 跨进程恢复。没有改动用户的 CViT 源码，没有新增真实模型 API 调用，没有重新训练 RL。

`science_Bot_workspace_update.zip` 是应用于已有 science Bot 安装的增量包，按压缩包内的项目相对路径覆盖对应源码即可；它不包含旧版权重、依赖或凭据。完整说明见 `RUT_Science/docs/Science_Bot_Workspace_zh.md`，机器验收见本目录 `verification.json`。

当前工作区提供项目文件访问和会话管理；CViT 训练及新数据集仍需专门的工具注册和科研契约。
