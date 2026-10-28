# science Bot 项目工作区

当前版本已接入 G2 表格与实验设计：在 G1 通用入口基础上，新增 CSV 检查、独立/配对均值比较及 mean/OLS 预测比较，先审阅设计再确认执行。原 `science-bot.cmd` 入口保持，详见 [G2 使用说明](RUT_Science/docs/Science_Bot_G2_表格与实验设计_zh.md) 和[本轮交付](RUT_Science/delivery/g2_update/README_本轮交付.md)。[G1 说明](RUT_Science/docs/Science_Bot_G1_通用入口_zh.md)保留基础入口、项目问答及原数值引擎用法。

2026-10-21 整理后，本目录是 science Bot 的统一项目根目录。

```text
LangGraph_RL_Agent/
├── science-bot.cmd                  # Windows 启动入口
├── Start-ScienceBot.ps1              # PowerShell 参数包装器
├── API_key_Agent.json               # 本地模型配置；不提交、不打包
├── RUT_Science/                     # 完整工程主体
│   ├── rut_science/                 # Agent、环境、工具、训练与评测源码
│   ├── .venv/                      # 当前机器的 Python 虚拟环境
│   ├── models/                     # 已训练权重及轨迹
│   ├── data/                       # 已有本地科研数据
│   ├── prompts/                    # 固定 LLM 提示词
│   ├── tests/                      # 回归测试
│   ├── scripts/                    # 复现与交付脚本
│   ├── docs/                       # 技术文档
│   ├── delivery/                   # 原始交付和科研验收证据
│   └── outputs/                    # 历史运行和默认新会话
└── maintenance/
    └── organization_2026-10-21/     # 本次 ZIP 核对、历史差异、迁移备份与验证
```

## 启动

在本目录的 PowerShell 中运行：

```powershell
.\science-bot.cmd
.\science-bot.cmd -Backend offline
.\science-bot.cmd -Workspace "D:\my-project"
```

`-Workspace` 必须指向已有项目；会话默认保存在该项目 `.sciencebot/sessions/`。它不会改变 Agent 安装位置，也不赋予任意代码执行能力。

直接使用 Python 或启动 HTTP 服务：

```powershell
& '.\RUT_Science\.venv\Scripts\python.exe' -m rut_science science --backend offline
& '.\RUT_Science\.venv\Scripts\python.exe' -m rut_science serve
```

路径与工作区说明见 [工作区文档](RUT_Science/docs/Science_Bot_Workspace_zh.md)，研究结论见 [实际交付与研究结果](RUT_Science/delivery/实际交付与研究结果.md)。

已支持自动展示实际模型返回，以及 `/model-output`、`/model-output list`、`/model-output <编号>` 本地历史回看。详见 [模型输出说明](RUT_Science/docs/Science_Bot_Model_Output_zh.md)。

## 整理说明

- 原相邻 `RUT_Science` 已移入本目录；本地配置、源码、数据、模型和运行记录均位于本项目内。
- 两个交付 ZIP 已解压、逐文件计算 SHA-256 并核对。删除 1,723 个重复解压副本及两个冗余 ZIP；6 个不同的历史文件保存在 `maintenance/organization_2026-10-21/extracted/science_Bot_delivery_2026-10-20/`。
- 第三方库的 `my-test-package.zip` 是测试资源；已解压核对，其 7 个文件保存在同一 `extracted/` 下，原 ZIP 保留以维护依赖完整性。
- 同内容的科学证据、训练种子目录和交付权重副本具有各自的溯源用途，保留原结构。
- 虚拟环境、控制台入口和可变会话中的安装路径已修复；迁移前元数据保存在 `runtime_before_relocation/`。内部测试工作区路径改变后，其未完成会话需要重新确认。
- 原始科研报告、训练权重、历史验收文件中的旧绝对路径作为历史证据保留，不批量改写。完整核对清单见 `archive_inspection.json`，迁移清单见 `relocation.json`。
- 上级共享 `API_key_Agent.json` 保留给独立的 `LangGraph_Demo`；science Bot 使用本目录的配置。该教学 Demo 的导入路径已同步更新。

本地 `.venv` 仍依赖本机已安装的 Python 3.12 基础解释器；移动到另一台机器后按交付文档重建环境。

本次整理后验证：主项目 159 项测试中 158 通过、1 项跳过；独立教学 Demo 3 项通过。生成任务与 Darcy 的离线执行、跨进程恢复及 Windows 启动入口均通过，未新增真实模型 API 调用。详情见 [整理结果](maintenance/organization_2026-10-21/整理结果.md)。
