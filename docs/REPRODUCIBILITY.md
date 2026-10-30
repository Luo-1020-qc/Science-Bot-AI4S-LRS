# 安装与复现

## 环境与启动

推荐Windows x64、Python 3.12；包声明Python>=3.10。其他平台尚未完成同等验收。在项目根目录执行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup.ps1
.\science-bot-web.cmd -Example
```

已有可用虚拟环境时直接启动。Python不在PATH时向安装脚本传入 `-Python 'C:\path\python.exe'`。`-Exact`使用已导出的完整依赖版本；默认安装使用包内依赖范围。安装需要网络，记录软件源或环境差异，虚拟环境由目标机器重建。

日常入口、工作区和示例操作见[使用说明](USAGE.md)。

## API配置

从根目录 `API_key_Agent.example.json` 复制为 `API_key_Agent.json`，填写自己的配置。该文件由Git忽略；模型请求发生时才读取。

endpoint会补全 `/chat/completions`，默认选第一个profile。终端默认模型为 `deepseek-flash`，显式模型参数优先；配置中的model不会覆盖此默认值：

```powershell
.\science-bot-web.cmd -Model 'YOUR_AVAILABLE_MODEL_ID'
```

先做离线检查，再测试真实接口并单独记录费用、模型和请求预算。

## 当前检查

```powershell
# 便携检查：链接、忽略规则、受保护文件、v2制品及冻结研究
& '.\RUT_Science\.venv\Scripts\python.exe' -B scripts/check_repository.py

# 核对当前完整性和已保存的测试证据
& '.\RUT_Science\.venv\Scripts\python.exe' -B scripts/verify_pdf_reading.py

# 需要实际重跑当前应用、完整性和界面状态测试时
& '.\RUT_Science\.venv\Scripts\python.exe' -B scripts/verify_pdf_reading.py --run-tests
```

默认检查不联网、不训练、不执行真实科研任务。当前层记录在[PDF阅读验收](integration/pdf_reading_2026-10-30/README.md)，便携检查输出在 `.local/checks/`。界面状态测试使用发布的JavaScript和模拟DOM，浏览器视觉验收仍待完成。PDF解析依赖已加入安装清单；旧环境重新运行安装脚本即可补齐。

`verify_dynamic_upgrade.py`、`verify_interfaces.py`、`verify_question_tool.py`、`verify_branding.py`、`verify_context_choices.py`、`verify_planning_mainline.py` 和 `verify_session_history.py` 的默认当前验收链均转入上述入口。旧回执只说明各自版本；历史训练重算按原实验说明执行。

## 规划评估与示例

```powershell
# 完整回合规则基线：输出目录必须是新目录
& '.\RUT_Science\.venv\Scripts\python.exe' -B scripts/evaluate_planning_mainline.py --output .local/mainline_evaluation/new_run

# 重新生成三份静态界面示例
& '.\RUT_Science\.venv\Scripts\python.exe' -B scripts/preview_interfaces.py
```

基线默认离线，从自然请求进入规划，后续用显式字段和选项；结果口径见[完整回合报告](evaluation/mainline_2026-10-30/REPORT.md)。真实接口用独立 `--live` 条件并另存结果。此前动态问题诊断见[历史报告](evaluation/dynamic_clarification_2026-10-29/REPORT.md)，不与本轮样本相加。

旧研究接口可用 `/research status`、`/research verify g2_4`、`/research compare g2_3 --seed 37` 核对范围与冻结模拟。科研规划命令见[规划指南](HARNESS_PLANNING.md)。

## 数据与训练

| 内容 | 复现入口 |
|---|---|
| Question tool候选 | [训练说明](../RUT_Science/research/question_tool_v1/README.md) |
| 上下文选项匹配 | [训练说明](../RUT_Science/research/context_choices_v1/README.md) |
| ClariQ/QASPER与人工对话 | [数据课程](../Training_Data/scientific_dialogue_v1/README.md) |
| v2工具环境与专家扩展 | [数据入口](../Training_Data/README_训练数据说明.md) |
| 独立工具库 | [工具说明](../Research_Tool_Library/README_详细工具库.md) |

复现使用新目录，保留原始分区、来源、参数和失败结果。当前主线不开展LLM微调，也不继续扩展旧PPO。旧审计有当轮文件哈希或原机路径约束，迁移与源码变更须通过新授权记录衔接。

## 分发与迁移

源码、提示词、必要模型、当前数据协议和评估证据保留；本地密钥、虚拟环境、私有会话、待审输入及大型原始语料由Git忽略。手工复制目录也应遵守同一范围。

训练目录现为 `Training_Data/`，旧名称通过完整性层映射；原清单不改写。全新机器依赖重建和真实API仍需实际验证。公开前确认自有代码、论文和第三方数据的分发权限。
