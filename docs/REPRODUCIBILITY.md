# 比赛安装、使用与复现

## 1. 环境安装

推荐Windows x64和Python 3.12。项目包元数据声明Python>=3.10，但当前实测环境为3.12。终端启动脚本使用Windows路径；其他平台可自行建立venv并安装`RUT_Science[science-bot]`，尚未提供跨平台验收承诺。

从项目根目录执行：

```powershell
python --version
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup.ps1
```

已有Python不在PATH时，可向安装脚本传入`-Python 'C:\path\python.exe'`。安装依赖需要网络；应用、研究和权重不依赖原作者虚拟环境，`.venv`不应复制到新机器。

默认安装使用包元数据中的直接依赖范围。`-Exact`安装`requirements-science-bot.lock.txt`记录的完整环境版本，其中PyTorch CPU依赖使用额外CPU索引。该文件由本机已安装包导出，不包含密钥或editable绝对路径；不是带下载哈希的跨平台锁文件。软件源没有对应版本时，应保留失败记录，使用默认安装并登记新环境，再进行对照验收。

## 2. API与模型

将根目录`API_key_Agent.example.json`复制为`API_key_Agent.json`，填入评委自己的API key。当前已有key保留且被Git忽略；程序在请求时才读取配置。

endpoint会补全`/chat/completions`。默认选择第一个配置profile。终端默认模型为`deepseek-flash`；配置中的model字段不自动覆盖终端模型参数。若该模型在评委服务中不可用，按根README使用`--model`显式指定可用模型。

先运行离线验收，再按需测试API，以区分本地Harness问题和模型／服务问题。API产生费用，便携检查不发出模型请求。

## 3. 便携验收

```powershell
& '.\RUT_Science\.venv\Scripts\python.exe' -B scripts/check_repository.py
```

该脚本检查文档链接、Git忽略行为、当前架构／权重保护清单、v2数据、冻结研究、终端预览、CViT冻结策略模拟和DOE演示；如有依赖或文件缺失将明确失败。它不修改冻结文件、不发起模型请求、不训练新策略。输出位于Git忽略的`.local/checks/`。

继续进行交互演示：

```powershell
.\science-bot.cmd -Backend offline
```

| 输入 | 应核对的行为 |
|---|---|
| `/research status` | 显示本地研究范围、默认规则访谈 |
| `/doe demo` | 展示错误方案与脚本修订，输出可审阅状态及限制 |
| `/doe report` | 返回同一会话最新DOE证据 |
| `/research simulate g2_3 --policy bc_ppo --seed 37` | 加载冻结本地策略，运行开发场景模拟，保留成功或失败行为 |
| `/research compare g2_3 --seed 37` | 同一场景下比较策略；不要求学习策略胜过规则 |

API模式可再输入项目介绍或实验设计请求，用`/model-output`查看模型提议，与工具执行证据分开核对。比较在线运行时需固定模型、输入、工作区、会话起点和预算；温度0也不承诺逐字或调用顺序完全一致。

## 4. 研究与数据专项检查

```powershell
& '.\RUT_Science\.venv\Scripts\python.exe' -B 'Training_Data_Darcy_CViT/validate_current.py' --tests
& '.\RUT_Science\.venv\Scripts\python.exe' -B 'Research_Tool_Library/run.py' test
```

第一条检查v2基础集和PPO记录，包含真实log probability／critic值重算；第二条执行离线工具库测试。两者可能更新各自报告并创建本地模拟制品，不启动真实科研计算。专家扩展另按交接文档执行import和preflight，基础集校验不能代替新增任务预检。

## 5. 可复现边界

在线研究worker使用相对本仓库的`online_artifacts.json`检查冻结制品，适合评委新检出路径。部分**历史迁移审计**（包括relocation清单、旧项目保护检查和v2原始工具来源记录）保存了原机绝对路径，它们是原交付证据，不是新机器启动依赖。换路径时不要批量修改冻结清单以“通过”旧审计；使用便携验收，并保留旧记录的历史性质。

当前统一研究`verify`已使用清理后的保护清单，不依赖旧delivery或弃用数据v1。冻结study源码里保留的早期隔离审计具有当轮语义，不能代替当前统一入口；不要为使旧审计通过而恢复整套历史工作区。

新机器的完整依赖重建和API调用尚需评委按以上步骤验证。本次整理在现有环境执行离线检查，并使用仅包含Git可提交文件的异路径副本检查研究worker，以发现被忽略的必要文件和路径依赖；不将其描述为全新机器安装测试。

## 6. 上传范围

源码、提示词、冻结策略、研究结果、工具库、当前v2数据和专家说明随仓库交付。弃用训练数据v1已删除，历史交付／输出移到同级归档目录，不再是运行依赖。本地key、虚拟环境、训练临时沙箱及未审专家输入由Git忽略。

Git忽略规则不保护人工全目录复制；若通过其他平台直接上传文件夹，按相同规则选取文件。目标Git仓库为根README中的Science-Bot-AI4S-LRS；API key不进入提交。仓库权限与比赛材料授权由项目维护者确认。
