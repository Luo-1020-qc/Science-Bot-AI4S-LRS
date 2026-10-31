# 架构与维护

应用代码、提示词、有效模型、测试和冻结研究均在 `RUT_Science/`。从[项目入口](../README.md)启动；操作见[使用说明](USAGE.md)，科研流程见[规划指南](HARNESS_PLANNING.md)。

## 调用链与模块

```text
science-bot.cmd / science-bot-web.cmd
  → Start-ScienceBot.ps1 → terminal.py / workbench.py + api.py
  → GeneralSession → LangGraph 路由与调度
      ├─ 科研规划：语义提议 → 账本 → 校验 → 问题/模板 → 复核与交付
      ├─ CSV设计访谈和受限执行
      ├─ 显式文件问答、通用问答
      └─ /tools、/research、/doe
```

以下路径相对于 `RUT_Science/rut_science/science_bot/`：

| 模块 | 职责 |
|---|---|
| `general/conversation.py`、`graph.py`、`router.py` | 会话、预算、LangGraph路由及检查点 |
| `general/provider.py`、`../configuration.py` | 原生chat/completions、tool_calls、API配置及调用账本 |
| `general/planning/intake.py`、`ledger.py` | 引文支持的字段提议、快照、冲突、未知、依赖和确认失效 |
| `general/planning/routing.py`、`turn_feedback.py`、`method_review.py` | 规划持续路由、采纳回执与失败更正阻断、方法风险及待人审状态 |
| `general/planning/blueprint.py`、`runtime.py` | 20类声明、11节点计划、复核与规划命令 |
| `general/planning/clarification.py`、`choices.py` | 动态问题、候选校验、模板降级和版本绑定选项 |
| `general/planning/synthesis.py` | 单次原生请求合成实验初稿及关键问题；建议与事实分开，绑定来源版本、缓存与模板降级 |
| `general/planning/question_tool.py`、`question_ranker.py` | 只读字段排序、回答变化和脱敏观察 |
| `general/planning/evidence.py`、`understanding.py` | 所选片段快照、共享授权和复述讨论 |
| `general/planning/pdf_document.py`、`pdf_worker.py`、`paper_reading.py`、`paper_context.py` | PDF全文/范围隔离提取、无损分批阅读、覆盖和续读、带原文引用的解读与规划摘录 |
| `paper_library.py` | 显式二进制上传、本地内容寻址存储与去重、PDF检查、库索引和独立证据选择 |
| `general/planning/delivery.py`、`presentation.py` | 实验设计阅读层、只读界面和版本绑定交付 |
| `general/tool_library.py`、`registry.py`、`interview/` | 详细离线工具、契约和CSV访谈 |
| `workbench.py`、`api.py`、`session_history.py` | 本地HTTP、历史删除、并发保护与缓存清理 |
| `workbench_assets/dist/`、`interface_demo.py` | 随Python包分发的页面资源及离线合成示例 |

## 状态、权限与持久化

会话引擎为 `general_v1`，规划状态为 `research_planning_v1`。规划快照保存于会话的 `planning/<id>/snapshots/<revision>.json`，元数据保存引用与哈希。原文、声明、未知、冲突、证据及决定可追溯；修改关键前提后撤销确认并重查依赖。

模型tool_calls经宿主校验后进入注册工具。20个详细工具为离线实现，45项契约的其余状态见[工具库](../Research_Tool_Library/README_详细工具库.md)。规划确认、CSV/数值草案确认和真实执行授权各有适用范围。

浏览器只在内存中保存本地服务凭据。删除限定于会话根目录内身份匹配的目录，清理会话文件和请求缓存，保留删除ID以阻止旧请求恢复记录；原始项目文件保留。HTML交付与冻结快照核对后转义展示。

## 模型与研究资源

| 路径 | 用途 |
|---|---|
| `RUT_Science/models/planner/v1/` | 数值适配器使用的BC/RL/selected权重 |
| `RUT_Science/models/design_interview_bc/` | CSV访谈BC参数；默认访谈仍为规则 |
| `RUT_Science/models/retained_delivery_checkpoint/` | 保留的历史检查点 |
| `RUT_Science/data/darcy_cpu_v1/` | 当前数值适配器的数据依赖 |
| `RUT_Science/research/strategy_learning/studies/` | 冻结任务、策略、代码和研究结果 |
| `RUT_Science/research/question_tool_v1/`、`context_choices_v1/` | 30维字段排序候选、上下文选项匹配训练 |
| `Training_Data/v2/` | 32维/23动作的有界离线工具环境及训练记录 |
| `Training_Data/scientific_dialogue_v1/` | 公开追问/证据候选与科研对话标注管线 |

权重须与特征顺序、动作映射、mask、工具和数据版本共同使用。`models/planner/v1`、`data/darcy_cpu_v1`及旧数值引擎仍是依赖；冻结研究中的reference_copy用于回归与来源核验。

## 接续维护

1. 在独立分支检查Git状态，保留未提交成果；协作要求见[CONTRIBUTING](../CONTRIBUTING.md)。
2. 当前源码、权重及旧记录通过 `scripts/integrity.py` 的授权链校验。源码升级追加授权记录，历史清单保持原字节。
3. 按影响范围验证，命令见[复现说明](REPRODUCIBILITY.md)。当前回执见[PDF上传验收](integration/paper_upload_2026-10-31/README.md)，规划和PDF等阶段历史保留于各接入记录及[变更记录](../CHANGELOG.md)。
4. 训练与标注见[数据入口](../Training_Data/README_训练数据说明.md)。科研质量依赖独立领域审阅和实际用户观察，工程回归与合成诊断分别报告。
