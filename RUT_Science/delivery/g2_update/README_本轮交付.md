# G2 表格与实验设计交付

日期：2026-10-22。G2 已完成受限首版交付。保持 `science-bot.cmd` / `Start-ScienceBot.ps1` 原入口，无新增 ZIP；未重新训练 RL、未更换模型服务或升级依赖。

## 本轮新增

- `csv_inspect`：真实 CSV 的数据哈希、行数、列类型、缺失与低基数文本水平。
- `ExperimentSpec`：研究问题、单位、来源、因素水平/特征、样本依据、缺失处理和参数；宿主派生可检验假设、指标、方法与停止条件。
- 设计与数据校验：拒绝缺项、来源猜测、重复单位、不完整配对、多余组别、非法数值、不足样本和未支持参数。
- `ExecutionPlan`：绑定规格及数据哈希，校验注册工具、依赖、确认、预算、结果身份和节点恢复。
- 三个真实任务族：独立两组 Welch、配对 t 检验、固定 mean/OLS 预测比较。
- 模型原生工具规划与无模型的 `/design` 结构化路径，沿用共享请求/token账本、`/model-output`、`/report`、HTTP幂等和旧会话恢复。

这三个任务族不是任意统计实验系统。分类、多因素/区组ANOVA、聚类/时间依赖、功效规划、自动超参数搜索及CViT训练仍未接入。数据来源与单位独立性由用户声明；宿主校验列结构不能证明这些科学前提成立。

## 直接运行

在 `LangGraph_RL_Agent` 根目录：

```powershell
.\science-bot.cmd -Backend offline -Workspace 'RUT_Science\examples\g2'
```

终端输入：

```text
/design independent_design.json
/confirm
/report
```

另外两个设计文件为 `paired_design.json` 和 `prediction_design.json`；每次分别确认。预测任务需7次工具操作，建议新建会话体验各示例。

API模式移除 `-Backend offline`，可以输入：

```text
请为 two_groups.csv 设计独立两组 Welch 比较。研究问题：A组与B组平均y是否不同。response=y，unit=id，factor=group，levels=[A,B]，数据来源为合成 synthetic。sampling_note=全部现有合成样本，仅作探索性演示；未进行事先功效计算。alpha=0.05，seed=42。
```

完整使用、协议与边界见 [G2 使用说明](../../docs/Science_Bot_G2_表格与实验设计_zh.md)。

## 验证结果

| 检查 | 结果 |
|---|---|
| 全量回归 | 252项：250通过、2跳过；日志 `tests.log` |
| 跳过原因 | Windows账户缺少文件符号链接权限；已有目录junction检查仍执行 |
| G2新增 | 29项，含原生调用、HTTP、参数/证据校验、故障恢复与数据隔离 |
| 独立组示例 | Welch：A减B=-3.27356713205425，p=0.00258848929234127；独立公式复核一致 |
| 配对示例 | 按ID匹配：before减after=-1.5454934138640486，p=0.004010810606680008；独立公式复核一致 |
| 预测示例 | 验证集选择OLS；冻结测试MSE=0.07063582068357449；原坐标系重建系数与指标一致 |
| 数据隔离 | 划分互斥；标准化及模型仅拟合训练；验证选模；测试结果不反馈计划 |
| 真实恢复 | 三种任务均一步后暂停，在新进程恢复完成；完成后重复run不新增工具次数 |
| 真实模型 | 成功轮2次API调用、2873 token；csv_inspect → prepare_tabular_experiment，原生ID与返回一致 |
| 本轮累计模型用量 | 包含首次失败，共6次API调用、9937 token；金额未配置 |
| 真实终端 | 原CMD入口完成 `/design independent_design.json`、`/confirm`、报告输出、模型回看与退出；离线0次模型调用 |

预测测试评价成功提交一次；如果纯本地工具在返回持久化前崩溃，可能重新计算，不宣称任意崩溃点都具备物理恰好一次语义。已落盘工具结果与已完成节点不会被重复计算。

首次真实模型验收发现：模型补写的随机化说明被正确拒绝；随后合法的样本依据因句末紧接英文参数被误判缺失。已修复自由文本与标识符的边界区别、补充schema说明并新增回归；失败会话、4次调用和7064 token完整保留，未产生实验。成功轮另用2次调用，未隐去失败成本。

验收数据是单独生成的合成文件，未读取用户作业或论文数据。一个在线合成任务与三个本地场景，不代表已经证明跨领域泛化准确率。

## 证据与复核

- `verification.json`：最终逐项检查、用量、源文件哈希。
- `tests.log`：252项最终完整回归；不使用在线模型。
- `offline_verification.json`、`offline_sessions/`：三种设计及跨进程恢复、数值重算、预算记录。
- `live_verification.json`、`live_sessions/`：真实原生工具调用、宿主校验、实验与报告。
- `live_initial_failure_review.json`、`live_session.json`：首次失败与修复说明；`live_retry_session.json` 指向成功轮。
- `terminal_acceptance.json`：实际CMD启动及本地终端输入、会话位置；`terminal_replay.txt`为保存状态的文本展示重放，不是PTY原始录像。
- `source_snapshot/`：本轮最终相关源码、测试、文档及原入口快照。
- `../../examples/g2/`：合成CSV与可直接使用的设计JSON。

在 `RUT_Science` 目录复核已保存结果，不产生新在线调用：

```powershell
& '.\.venv\Scripts\python.exe' -X utf8 scripts/verify_g2_delivery.py
```

脚本首次执行会生成尚不存在的演示文件、执行小型离线验收；已有结果则重核，不重复在线请求。`--live`会显式请求一次有预算上限的在线验收，本轮已保存成功记录时复用。存在未完成在线会话时脚本拒绝自动重发，先检查原输出。

后续建议进入G3前先盘点CViT的训练配置、数据、GPU预算与进程对账接口；不要把源码读取或统计工具接入当作GPU训练已可执行。
