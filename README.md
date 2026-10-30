# Science Bot — 科研规划 Harness

把模糊科研想法，逐步整理成有明确边界、证据来源、实验单位、分析方法和验收条件的实验设计。现有 LLM 负责理解文字和提出建议，本地 Harness 负责版本账本、未知与冲突、预算、工具权限及交付校验。

主线流程：**提出问题 → 选项澄清 → 选择论文证据 → 形成设计 → 人类复核 → 导出交付**。当前适合有人监督的科研规划和原型演示；真实科学实验需要另行核实工具支持范围及执行授权。

本说明对应 2026-10-30 当前版本。项目状态与实测限制见[Harness 评估报告](docs/reports/HARNESS_EVALUATION_2026-10-30.md)，完整工作概览见[综合项目报告](docs/reports/PROJECT_REPORT_2026-10-30.md)。

## 1. 安装与快速启动

在本 README 所在的项目根目录打开 PowerShell。当前验收环境为 Windows、Python 3.12；包声明支持 Python ≥ 3.10，其他平台尚未完成同等验收。

### 首次安装

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup.ps1
```

安装脚本创建 `RUT_Science/.venv/` 并安装应用与依赖，需要网络。已有可用环境可跳过。Python 不在 PATH 时使用 `-Python 'C:\path\python.exe'`；完整依赖安装方式见[安装与复现](docs/REPRODUCIBILITY.md)。

### 先体验离线示例

```powershell
.\science-bot-web.cmd -Example  # 浏览器工作台，预置合成研究，不调用模型
.\science-bot.cmd -Example      # 同一合成研究的终端入口
```

两条命令任选一条。示例预置了一个模型比较研究，保留待确认命题和未知的样本依据，可体验选项、设计展示与导出；它不包含真实实验结果。

如果要新建自己的离线研究，使用：

```powershell
.\science-bot-web.cmd -Backend offline -Workspace .
```

离线模式主要使用字段和选项，不调用 LLM，不提供论文语义解读。

### 使用真实模型

首次配置时，从[配置模板](API_key_Agent.example.json)创建本地文件；已有配置时保留原文件：

```powershell
if (-not (Test-Path -LiteralPath '.\API_key_Agent.json')) {
    Copy-Item -LiteralPath '.\API_key_Agent.example.json' -Destination '.\API_key_Agent.json'
}
```

编辑自己的 `API_key_Agent.json`，填写服务地址 `endpoint`、密钥 `API` 和可用模型信息，再启动：

```powershell
.\science-bot-web.cmd -Workspace . -Model 'YOUR_AVAILABLE_MODEL_ID'
# 或使用终端
.\science-bot.cmd -Workspace . -Model 'YOUR_AVAILABLE_MODEL_ID'
```

`YOUR_AVAILABLE_MODEL_ID` 要替换为服务实际支持的模型 ID。启动器默认模型为 `deepseek-flash`，配置文件中的 `model` 不会自动覆盖这个默认值；指定 `-Model` 最明确。本地密钥由 Git 忽略，示例和离线模式不需要填写真实密钥。

### 常用启动参数

| 参数 | 用途 |
|---|---|
| `-Workspace 'D:\my-project'` | 绑定已存在的研究目录；后续文件路径相对此目录 |
| `-Backend api` / `-Backend offline` | 选择真实模型或离线字段/选项模式，默认 `api` |
| `-Model '<模型ID>'` | 显式指定本次模型 |
| `-Example` | 进入预置的离线合成研究 |
| `-Port 8766` | 浏览器端口冲突时更换端口，默认 8765 |
| `-NoBrowser` | 启动浏览器服务但不自动打开页面 |
| `-Resume '<会话路径或ID>'` | 终端恢复会话；浏览器通过左侧最近研究恢复 |

浏览器服务只监听本机。使用启动器自动打开的页面连接自己的会话；直接打开 `http://127.0.0.1:8765/` 只显示公开合成预览。刷新后如失去连接，重新运行启动器获取本地访问凭据。停止服务在启动它的 PowerShell 窗口按 `Ctrl+C`。

## 2. 从一个想法走到实验设计

以下 `/plan` 等命令在 Science Bot 对话框或交互终端中**逐条发送**；上一节的 PowerShell 命令用于启动程序。

### 第一步：输入研究想法

可以直接粘贴这个简单示例：

```text
/plan 我想比较模型A和模型B在同一份合成数据上的预测误差，预算最多2小时。请把需要澄清的地方做成选项让我选择，最后生成实验设计。本轮只规划，不执行实验。
```

显式 `/plan` 可以减少当前自然语言入口漏判。也可用 `/plan start <研究目标>` 开始，或用 `/plan new <新目标>` 在同一会话内建立另一份规划并保留旧快照。

### 第二步：回答问题、选择边界

系统默认展示一条当前问题及相关选项。浏览器点击选项，终端输入当前编号；也可选择“暂不确定”“其他”或自己补充。旧选项绑定旧内容版本，继续回答时以最新问题为准。

主要需要明确这些内容，具体必填项随比较、预测、探索、因果或复现目的变化：

| 内容 | 需要回答的问题 |
|---|---|
| 研究问题与边界 | 想检验什么？结论适用于哪些对象、条件？本轮不回答什么？ |
| 单位与比较 | 什么才是独立样本？是否配对、重复或分组？比较谁与谁？ |
| 数据与证据 | 数据从哪里来？怎样隔离训练、验证和测试？有哪些依据缺口？ |
| 测量与分析 | 主要指标、改善方向、估计对象和不确定性怎样定义？ |
| 验收与资源 | 怎样算完成？如何报告阴性结果？什么时候停止？ |
| 复现与责任 | 谁复核、谁执行？记录哪些版本、配置和偏离？交付什么？ |

需要精确表达或自然语言未被采用时，用字段输入，例如逐条发送：

```text
/plan objective_type: comparison
/plan scope: 仅限同一分布的合成二维场，不外推其他方程或分辨率。
/plan experimental_unit: 每个独立完整场为单位，两模型在同一场上配对，网格点不算独立重复。
```

只有核对当前提议确实准确后，才用 `/plan accept <字段>` 确认。模型改写显示为待确认提议，不会自动变成用户已确认的边界。

### 第三步：保留未知，明确更正

不知道样本或重复数的依据时，明确输入：

```text
/plan sampling: 未知
```

当系统询问如何取得依据时，再说明查找先导记录、核对单位或请方法负责人审核等步骤。记录查证计划后，该字段仍然未知；取得依据再更新。不要为了填满设计而补默认方差或功效保证。

更正已经写入的内容，使用明确修订命令：

```text
/plan revise resources: 后续最多2次模型拟合、1小时上限；本轮只规划。
```

随后用 `/plan map` 核对账本实际采用的值。当前版本存在自然语言更正未生效的案例，因此发送更正后仍需检查。关键修订会撤销原确认，并要求重新核对受影响的依赖。

### 第四步：查看设计和未决项

| 命令 | 看到什么 |
|---|---|
| `/plan map` | 研究问题、主要边界、未知和当前状态 |
| `/plan draft` | 实验设计、11 节点步骤、依据、产物与验收条件 |
| `/plan review` | 已声明项、待确认、冲突、过期依赖和关键缺口 |
| `/plan explain experimental_unit` | 字段含义与追问解释；字段名可替换 |
| `/plan decisions` | 已记录的选择与修订历史 |
| `/plan understanding` / `/plan reflect 我的理解是……` | 查看复述提示，记录自己的理解、疑问或异议 |

浏览器也可在研究计划和交付中心阅读当前设计。草案可以保留缺口；依赖未知依据的最终确认仍可能被阻断。

### 第五步：复核当前版本

“规划可复核”表示声明已足以交给人类审阅。独立性、功效、因果假设、数据质量和结论仍须核实。先读 `/plan draft` 与 `/plan review`，确认后再使用程序显示的当前内容哈希：

```text
/plan approve <当前内容哈希>
```

尖括号内要替换为实际哈希，不要复制旧会话的值。哈希绑定当前规划内容；修改预算、来源或其他关键声明后须重新复核。规划确认保存已复核版本，不会启动模型训练或实验。

### 第六步：导出交付

在浏览器交付中心导出，或逐条使用：

| 命令 | 产物 |
|---|---|
| `/report` | 查看当前设计与交付概览 |
| `/deliver` | 生成 HTML 阅读版、Markdown 和 JSON |
| `/plan export` | 导出 Markdown 和 JSON |
| `/plan handoff` | 为已确认且无阻断的版本生成工作交接 |

HTML 适合阅读或打印，Markdown 适合讨论和修改，JSON 保留结构化状态、来源和版本。允许导出带未知及未决项的草案，导出本身不代表批准。

## 3. 读取论文与 PDF

先用 `-Workspace` 绑定论文所在目录，启动规划，再明确选择文件和范围。界面的证据页可填写相对路径、物理 PDF 页码或文本行号，并选择是否允许模型使用。

本项目有一份两页合成 PDF，使用 `-Workspace .` 时可先仅在本地读取：

```text
/plan evidence add {"path":"examples/papers/synthetic_paper.pdf","start_page":1,"end_page":2,"share_with_model":false}
```

如果明确同意将所选页提供给模型，把同一选择改为 `true` 后重新提交：

```text
/plan evidence add {"path":"examples/papers/synthetic_paper.pdf","start_page":1,"end_page":2,"share_with_model":true}
```

随后逐条发送：

```text
/plan evidence list
/plan evidence understand <实际返回的PDF片段编号>
```

API 模式下会生成带页码和原文引用的研究问题、方法、数据、结果、局限与复现缺口。该文件仅是功能演示用合成片段，不能提供真实科研证据。真实论文也必须由用户明确选择；程序不自动读取 IDE 标签页、父目录或论文中的链接。

| 功能或限制 | 当前行为 |
|---|---|
| 本地展示与模型共享 | 默认 `share_with_model=false`；显式设为 `true` 才允许用于模型处理 |
| PDF 范围 | 文字型 PDF ≤16 MiB，一次选 1–12 个物理页，文字最多 18,000 个 UTF-8 字节 |
| 文本片段 | Markdown/TXT 文件 ≤128 KiB；每段最多 120 行、6,000 字节 |
| 总证据预算 | 最多 6 个片段，总文字 ≤18,000 字节，并受会话读取预算约束 |
| 引用与解读 | 保存原文及哈希；解读保持待人类验证，不自动写成实验事实 |
| 失败处理 | 格式、引文或数字校验失败时保留原文与拒绝状态；模型解读并非每次成功 |
| 未支持内容 | 扫描件需先 OCR；图表、公式及复杂排版需回原文核对 |

`/plan evidence show <编号>` 查看片段，`/plan evidence remove <编号>` 移除。已保存的解读可重复查看而不新增请求，并随规划导出。引用对齐只能约束出处，解释是否忠实仍需研究者审核。更多命令见[论文证据说明](docs/HARNESS_PLANNING.md#显式选择论文片段)。

## 4. 历史、文件与预算

浏览器左侧“最近研究”可切换会话，每条右侧“删除”按钮删除该整段研究/对话。确认后清除其计划、聊天、会话内导出与请求缓存，无法撤销；原始项目文件保留。正在处理的会话须先等待或停止，静态预览不能管理私有历史。

绑定工作区后，会话保存于该目录的 `.sciencebot/sessions/`；未绑定时默认在 `RUT_Science/outputs/science_bot/`。规划快照位于会话内 `planning/<规划ID>/snapshots/`，导出位于 `planning/<规划ID>/exports/`。磁盘保存完整轮次，但当前页面切换主要恢复最后回复，完整对话阅读体验仍有缺口。

用 `/status` 查看资源。默认新会话上限为 12 次模型请求、60,000 个计账 token、40 次工具尝试及 24,000 字节读取额度。一次自然语言规划回答可能包含语义整理和动态澄清两次请求，失败也可能消耗额度；查看、复核和导出不追加动态模型请求。

提示词里的“2小时、6次拟合”属于未来实验的资源声明，不会自动改变会话 API 预算。触发上限后保留现有规划，可用显式字段/选项继续整理；不要将没有生成回答理解为没有产生请求。

## 5. Harness 内部如何工作

```text
浏览器 / 终端
  → GeneralSession 与 LangGraph 路由
  → 原生 LLM 语义提议 + 用户明确选择的证据
  → 宿主校验：字段、原话、未知、冲突、数字、预算与权限
  → 版本账本、依赖重查与确认失效
  → 动态问题和选项；失败回退模板
  → 设计阅读层 → 人类复核 → 版本绑定交付
```

账本区分 `declared`（用户声明）、`proposed`（待确认提议）、`unknown`（明确未知）、`conflict`（冲突）和 `stale`（依赖变更后待重查）。声明和出处可追踪，不等于外部事实已经验证。

Question tool 在合法候选内选择下一步追问字段。默认保留规则路径，合成训练的排序候选可用 `/plan question trained` 显式试用；`/plan question history` 和 `/plan question export` 可查看、导出待审观察。用户应答不是专家标签，不自动进入训练。详见[Question tool 与训练路线](docs/HARNESS_PLANNING.md)。

## 6. 已有工具、数据与能力边界

| 内容 | 当前实现与入口 |
|---|---|
| 科研规划 | 20 类声明、11 节点计划、动态/模板追问、未知与冲突、批准和导出 |
| 文件与论文 | 显式文件读取、Markdown/TXT 片段、文字型 PDF 按页提取和模型解读 |
| CSV/数值任务 | 受限的比较与预测适配器，沿用各自草案确认和执行权限；细节见[使用说明](docs/USAGE.md) |
| 详细工具库 | `/tools list`、`/tools call`、`/tools chat`；45 项契约中 20 项为离线实现，见[工具说明](Research_Tool_Library/README_详细工具库.md) |
| 冻结研究与 DOE | `/research status`、`/doe demo` 等受控入口，范围见[使用说明](docs/USAGE.md) |
| 数据与标注 | ClariQ/QASPER 候选、科研多轮标注管线、队友数据复核和旧 v2 工具环境，见[数据入口](Training_Data/README_训练数据说明.md) |

当前没有通用 shell、源码编辑或真实 CViT/FNO/LinearNO/GPU 训练执行器。工具契约、离线演练与真实科学执行应按各自状态核实，规划批准也不替代 CSV 或数值任务的确认。

目前没有进行 LLM 微调。已有 Question tool、选项族匹配和公开数据排序等小模型研究制品；合成课程命中率不能推导为真实科研质量。ClariQ/QASPER 候选未部署，旧 PPO 结果按原版本保留。当前主线是完善和评估 Harness，再考虑使用审核过的科研对话训练单个决策入口。

## 7. 最近评测与已知限制

以下为 2026-10-30 已完成的评测结果，本 README 整理不代表重新训练或修复这些问题：

| 项目 | 已有结果 |
|---|---|
| Python 工程回归 | 608 项，606 通过、2 跳过、0 失败；跳过项受 Windows 创建符号链接权限限制 |
| 离线完整回合 | 10 个合成开发案例均达预设结果：8 个完整设计、2 个保留未知及取证步骤的阻断草案 |
| 自然语言脚本 | 8 例中 4 例建立规划账本，终点无可复核完成态；含短探针及未确认提议，不作为统一能力准确率 |
| 方法风险探针 | 5 类有问题但措辞完整的声明仍被判为可复核，包括伪重复、测试集调参和隐瞒阴性结果 |
| PDF 解读 | 开发阶段曾通过；本轮新调用发生格式拒绝，跨论文稳定性尚未建立 |
| 真人与界面 | 专家追问质量、研究者理解改善、完整浏览器视觉验收尚未完成 |

当前还存在自然语言误路由、补充内容形成假冲突、预算更正未入账和反复确认同一字段等问题。实际使用时核对账本、方法假设与修订结果；“规划可复核”不能作为方法学正确或科学结论成立的保证。失败轨迹和评价口径见[综合评估](docs/reports/HARNESS_EVALUATION_2026-10-30.md)。

## 8. 目录与文档导航

```text
LangGraph_RL_Agent/
├─ README.md                 # 项目入口、快速启动与完整使用流程
├─ Start-ScienceBot.ps1      # 浏览器/终端共用启动器
├─ science-bot*.cmd          # Windows 便捷入口
├─ RUT_Science/              # 应用、提示词、模型、测试及冻结研究
├─ Research_Tool_Library/    # 详细工具契约、离线实现及工具验证
├─ Training_Data/            # 公开数据管线、人工标注、v2 协议与历史实验
├─ docs/                     # 专项指南、报告及评估/接入证据
├─ examples/                 # 静态界面、交付示例及合成 PDF
└─ scripts/                  # 安装、完整性和复现检查
```

文档按用途保留，已有训练原件、冻结结果和失败证据不因整理重复另存；日常从本页进入，无需逐份阅读历史接入记录。

| 要查什么 | 文档 |
|---|---|
| 更多界面、历史、CSV 和工具操作 | [统一使用说明](docs/USAGE.md) |
| 完整规划命令、状态、证据与 Question tool | [科研规划指南](docs/HARNESS_PLANNING.md) |
| 模块、存储和模型位置 | [架构与维护](docs/ARCHITECTURE.md) |
| 安装、依赖、配置、检查和迁移 | [安装与复现](docs/REPRODUCIBILITY.md) |
| 当前实测能力与问题 | [Harness 评估](docs/reports/HARNESS_EVALUATION_2026-10-30.md)、[综合项目报告](docs/reports/PROJECT_REPORT_2026-10-30.md) |
| 原完整回合基线与人工评价口径 | [主线报告](docs/evaluation/mainline_2026-10-30/REPORT.md)、[评分表](docs/evaluation/mainline_2026-10-30/RUBRIC.md) |
| 数据来源、标注与历史学习结果 | [训练数据入口](Training_Data/README_训练数据说明.md) |
| 历史变更与协作规则 | [变更记录](CHANGELOG.md)、[协作约定](CONTRIBUTING.md) |

无需启动服务的静态展示：[浏览器预览](examples/interfaces/browser.html)、[终端预览](examples/interfaces/terminal.html)、[交付阅读版](examples/interfaces/delivery.html)。这些页面不连接自己的私有会话。

## 9. 检查与复现

在根目录执行离线仓库检查，核对文档链接、忽略规则、受保护文件和冻结研究制品：

```powershell
& '.\RUT_Science\.venv\Scripts\python.exe' -B scripts/check_repository.py
```

该命令不调用模型、不训练、不执行真实科学实验，当前检查输出位于 `.local/checks/`。完整测试、合成任务重跑和历史实验重算见[复现说明](docs/REPRODUCIBILITY.md)；输出使用新目录，保留原来的来源、权重与失败记录。

本地密钥、虚拟环境、私有会话及临时输出由 Git 忽略；安装在新机器重建，个人论文和大型原始数据不自动纳入分发。项目尚未指定开源许可证，公开前需核对自有代码及第三方材料的分发权限。

仓库：[Luo-1020-qc/Science-Bot-AI4S-LRS](https://github.com/Luo-1020-qc/Science-Bot-AI4S-LRS)。
