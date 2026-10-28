# Science Bot — LangGraph Scientific Research Harness

面向科学研究任务的可审计Agent比赛项目。使用LangGraph组织对话路由与状态，结合工具契约、实验设计访谈、DOE复核、版本化证据和本地策略研究。DeepSeek提供语言能力，本地Harness控制工具调用及验收。

**当前进度：2026-10-28。** G1／G2／G2.1应用功能及G2.2／G2.3／G2.4研究接口已接入原入口；详细工具库和v2 RL数据环境作为独立研究模块交付。默认访谈仍为规则策略，当前学习结果尚未证明PPO优于规则。真实CViT／GPU实验不在研究聊天接口中执行。

## 入口：从这里启动

| 入口 | 用途 |
|---|---|
| **[science-bot.cmd](science-bot.cmd)** | Windows主入口；默认API模式 |
| [Start-ScienceBot.ps1](Start-ScienceBot.ps1) | 同一入口的PowerShell启动器 |
| [安装脚本](scripts/setup.ps1) | 新机器建立虚拟环境并安装依赖 |
| [比赛验收与复现](docs/REPRODUCIBILITY.md) | 评委配置、固定用例、检查步骤与复现范围 |
| [研究导航](docs/RESEARCH.md) | 研究、工具库、权重、训练数据与专家交接 |
| [专家交接文档](Training_Data_Darcy_CViT/RL训练数据_专家交接文档.md) | 任务扩充、DOE审阅与标注要求 |

## 快速开始

推荐Windows x64、Python 3.12。在项目根目录的PowerShell执行：

```powershell
# 首次安装；已有可用虚拟环境可以跳过
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup.ps1

# 无需API即可检查入口和本地研究接口
.\science-bot.cmd -Backend offline

# 使用本地API配置启动
.\science-bot.cmd

# 绑定已有项目；该目录必须存在
.\science-bot.cmd -Workspace 'D:\my-project'
```

启动后可逐条输入：

```text
/status
/research status
/doe demo
/doe report
/research simulate g2_3 --policy bc_ppo --seed 37
/research compare g2_3 --seed 37
```

`/doe demo`是有意设置错误并修复的脚本演示；研究模拟使用冻结策略，不等于Agent在真实CViT任务中完成训练。默认通用入口不会自动创建Darcy实验。

### API配置

现有`API_key_Agent.json`保留在本地，并由Git忽略。新机器复制[配置模板](API_key_Agent.example.json)，另存为根目录`API_key_Agent.json`，填入自己的endpoint和API key；程序默认读取第一个profile。

```powershell
# 仅在还没有本地配置时创建，保留已有key
if (-not (Test-Path -LiteralPath '.\API_key_Agent.json')) {
    Copy-Item -LiteralPath '.\API_key_Agent.example.json' -Destination '.\API_key_Agent.json'
}
```

当前终端默认模型参数是`deepseek-flash`。**配置文件里的model字段不会覆盖终端的显式默认值**；需要其他模型时，从项目根目录使用：

```powershell
Push-Location .\RUT_Science
try {
    & '.\.venv\Scripts\python.exe' -B -m rut_science science --backend api --model 'YOUR_AVAILABLE_MODEL_ID'
} finally { Pop-Location }
```

更换API key不会改变本地策略权重，但模型版本和在线回答可能变化。验收以任务行为、工具证据和固定检查结果为准，不要求自然语言逐字一致。

## 功能与研究进度

| 阶段 | 已完成内容 | 当前边界 |
|---|---|---|
| G1 | 通用对话、项目工作区与路由 | 已进入应用 |
| G2 | 受限表格分析和实验设计工具 | 按已注册契约执行 |
| G2.1 | 多轮设计访谈、信息补全与学习环境 | 默认规则访谈 |
| G2.2 | 专家标注协议、BC和冻结任务基准 | 研究接口已接入；标签尚未完成真人校准 |
| G2.3 | CPU策略PPO、CViT模拟、公开证据审计和修订试验 | 尚未显示PPO优势，不默认推广研究策略 |
| G2.4 | 三类有界DOE设计、版本与来源校验、功效／预算检查 | 通过表示可审阅，不证明科学假设为真 |
| 详细工具库 | 45项契约，其中20项离线实现；方案修订、复核、冻结、模拟及结论闭环 | 独立模块，尚未整体注册到在线Agent |
| RL数据v2 | 12任务、134参考决策、86条BC参考标签、31条待审决策；专家导入与环境预检 | 真人专家标签0；公开示例不构成盲测 |
| v2 PPO检查 | 64步on-policy采样、1个PPO批次更新，22项测试通过 | 仅证明有界CPU链路可运行，未部署默认策略 |

G2.2／G2.3／G2.4已记录的研究测试合计125项通过。各轮数量对应各自报告版本，不应相加后表述为一次完整比赛验收。详细历程见[阶段总结](阶段性总结2_2026-10-27.md)和[进度记录](CHANGELOG.md)。

## 项目结构

```text
LangGraph_RL_Agent/
├── README.md / CHANGELOG.md / CONTRIBUTING.md
├── science-bot.cmd / Start-ScienceBot.ps1   # 保留原入口
├── API_key_Agent.example.json              # 可提交的无密钥模板
├── API_key_Agent.json                      # 本地配置，Git忽略
├── scripts/                               # 安装、便携验收与Git检查
├── docs/                                  # 比赛使用、研究导航和整理记录
├── RUT_Science/
│   ├── pyproject.toml / rut_science/       # Python包与应用源码
│   ├── prompts/ / models/ / examples/      # 提示词、已保存模型与用例
│   ├── tests/ / docs/ / scripts/           # 模块测试与原有说明
│   ├── research/strategy_learning/         # 冻结研究、权重与评测证据
│   └── delivery/                          # 历次交付和验收记录
├── Research_Tool_Library/                  # 独立离线工具库与闭环演示
├── Training_Data_Darcy_CViT/               # 数据入口、专家交接、v1快照和v2
├── Reference_Paper/                        # 方法笔记
└── maintenance/                            # 历史迁移与本次整理记录
```

采用保留路径的多模块Git项目布局，避免移动冻结研究、相对导入和哈希绑定制品。历史报告保留当时路径；当前使用以上入口。

## 检查与复现

```powershell
# 无网络、无真实实验的便携检查；报告写入忽略的运行目录
& '.\RUT_Science\.venv\Scripts\python.exe' -B 'scripts/check_repository.py'

# v2参考数据、环境和PPO记录检查
& '.\RUT_Science\.venv\Scripts\python.exe' -B 'Training_Data_Darcy_CViT/validate_current.py' --tests

# 独立工具库测试
& '.\RUT_Science\.venv\Scripts\python.exe' -B 'Research_Tool_Library/run.py' test
```

安装脚本默认按`pyproject.toml`的依赖范围安装。`-Exact`使用[本机依赖快照](requirements-science-bot.lock.txt)；它是当前环境版本记录，尚不代表所有平台都已验证。新机器迁移和历史绝对路径校验的区别见[复现说明](docs/REPRODUCIBILITY.md)。

## Git与提交

本目录已初始化为独立Git仓库，默认分支`main`。虚拟环境、本地key、输出会话、临时训练沙箱和早期解包副本保留在磁盘但不纳入Git；源码、研究权重、冻结证据和示例数据保留为可提交内容。`.gitattributes`保留原始字节，避免换行转换破坏研究哈希。

```powershell
git status --short
git check-ignore API_key_Agent.json RUT_Science/.venv/
git add .
git diff --cached --stat
# 检查后由维护者创建首次提交、设置远程并推送
```

交付仓库：[Luo-1020-qc/Science-Bot-AI4S-LRS](https://github.com/Luo-1020-qc/Science-Bot-AI4S-LRS)。API key仍只保留在本地，不进入提交。机器若找不到Git，可将本机已存在的MinGit目录加入当前会话PATH；比赛评委使用自己的Git安装即可。协作约定见[CONTRIBUTING](CONTRIBUTING.md)。未擅自指定开源许可证，发布授权由项目负责人确认。
