# science Bot 研究接口上线

日期：2026-10-27。G2.2、G2.3、G2.4现在可以通过原 `science-bot.cmd` 对话和现有HTTP消息接口使用。重启已打开的science Bot进程后生效。旧入口、默认规则访谈和原G1/G2/G2.1功能保留。

本次“上线”指本地应用接入：研究状态、历史结果、完整性检查、开发场景模拟、冻结策略推理、DOE检查、审阅副本导出与已审记录验证。正式训练、重新选模、封存评测和真实CViT执行仍使用独立研究流程，不作为聊天动作。

## 启动与第一组输入

在 `LangGraph_RL_Agent` 根目录启动：

```powershell
.\science-bot.cmd
# 研究功能也能完全离线运行
.\science-bot.cmd -Backend offline
```

随后在聊天框逐条输入：

```text
/research
/doe demo
/doe report
/research simulate g2_3
/research results g2_3
```

`/doe demo`展示一个2×2全因子草案遗漏交互模型、收到反馈后修复的过程，最终显示计划单位、自由度、条件名义功效和未验证假设。它是脚本演示，不能解释为策略自动学会了修复。

支持明确的自然语言快捷请求，如“运行DOE演示”“运行CViT模拟”“查看G2.3研究结果”。复杂参数使用下列命令。解释性或否定请求不授权研究模拟。

## 可用命令

| 输入 | 行为 |
|---|---|
| `/research status` | 接口范围、默认策略和最新结果位置 |
| `/research results g2_2` | G2.2冻结基准结果与标签来源 |
| `/research results g2_3` | G2.3公开证据严格评分与独立修订试验摘要 |
| `/research results g2_4` | DOE开发诊断、待审数量与限制 |
| `/research verify g2_4` | 实时核对注册的研究源码、模型和依赖制品；不复用旧校验结果 |
| `/research simulate g2_2 --policy bc --seed 37` | 指定冻结BC在一个表格开发案例中推理 |
| `/research simulate g2_3 --policy bc_ppo --seed 37` | 指定冻结BC＋PPO在CViT开发模拟中推理 |
| `/research compare g2_3 --seed 37` | 同一场景下比较规则、BC、BC＋PPO、从零PPO和修订试验两种策略 |
| `/doe template crd_two_arm` | 生成合成两处理CRD模板及检查结果 |
| `/doe template rcbd_two_arm` | 生成合成两处理RCBD模板及检查结果 |
| `/doe template factorial_2x2` | 生成合成2×2全因子模板及检查结果 |
| `/doe status` | 研究状态及最近DOE检查摘要 |
| `/doe report` | 最近DOE结果；不受其他研究结果切换影响 |
| `/doe recheck` | 重新读取上次选定输入并检查；内联/模板输入复核已保存内容 |

study可写 `g2_2/g2_3/g2_4` 或 `G2.2/G2.3/G2.4`。冻结训练seed只接受21、37、59。G2.3可选策略：`rule/bc/bc_ppo/ppo_scratch/feedback_baseline/feedback_ppo`；G2.2支持`rule/bc`。

模拟默认规则策略。G2.2默认场景`ordinary_comparison`；G2.3默认域`cvit`、场景`existing_running`。可通过`--domain tabular`和`--scenario ordinary_comparison`选择表格开发模拟。未知场景返回可用的开发场景列表，没有封存场景入口。

G2.3的学习策略保留其失败行为，严格成功必须满足公开停止证据；界面不会把提前停止或旧宽松成功分当成改进。策略推理使用冻结JSON参数的CPU actor前向计算，不载入pickle，不运行优化器、GPU或正式训练。单个开发案例比较不用于选模，也不是新的盲测。

## 检查实际DOE草案

先绑定需求与草案所在的已有项目：

```powershell
.\science-bot.cmd -Workspace "D:\my-project"
```

在聊天中输入：

```text
/doe validate "request.json" "contract.json"
```

两个文件通过现有工作区策略读取，记录相对路径、SHA-256和字节数，读取总量受会话预算约束。文件修改后使用`/doe recheck`会重新读取并生成新的证据；原结果仍保留。

也可显式提交 `/doe validate {"request":{...},"contract":{...}}`。JSON须满足G2.4闭合schema，包含字段来源和正确request哈希；模板返回的request/contract文件可作为结构参考。自然语言访谈仍沿用G2.1，尚未实现自动填充全部DOE协议的全新访谈器。

首批仅支持同方差正态固定效应模型下的两处理CRD、两处理RCBD及2×2全因子。随机化、矩阵秩、可估计性、自由度、主要对比、名义功效和预算进入固定验收。通过意味着`ready_for_review`；科学假设仍未验证，`scientific_success=null`，不会产生可执行草案或真实结果。

极端方差/非中心参数可能造成冻结统计实现返回非有限诊断。在线桥接遇到这种情况会返回阻断，不输出NaN或将其当作通过；更改sigma、alpha、主要对比仍需与原始来源一致。

## 审阅接口

```text
/research review-export g2_2
/doe review-export
```

分别导出72条和42条待审记录的副本到当前会话研究结果目录，文件名`pending_review_copy.jsonl`。原研究队列、训练标签和权重不变。

审阅者应在绑定项目中另存需要审阅的一批记录，填写相应协议要求的结论、理由、身份和带时区时间，然后输入：

```text
/research review-import g2_2 reviewed_g22.jsonl
/doe review-import reviewed_doe.jsonl
```

导入只验证训练分区、源文件、上下文哈希、合法字段和审阅声明，并将验证后的记录保存在当前会话；拒绝pending、重复或篡改记录。单批文件受工作区读取预算限制，宜分批审阅。身份是外部声明，不自动证明专家资质。没有自动训练、替换规则或修改冻结基准。测试中的synthetic审阅夹具不计为真人标签。

## 状态、报告与边界

结果保存到当前会话 `research/<请求哈希前16位>/result.json`，完整请求身份保留在结果与缓存中并逐次核对，短目录用于避免Windows长路径问题。DOE同时保存`request.json`、`contract.json`和`validation.json`。`/status`展示研究状态，`/report`展示最近研究报告；`/doe report`专门展示最近DOE报告。

重复请求复用已保存结果，不重复消耗宿主工具次数；实时`verify`每次重新核对。恢复会话会检查最新结果哈希，篡改结果会被拒绝。研究操作使用共享宿主工具次数和文件读取预算，不需要DeepSeek请求。

`/confirm`和真实作业`/resume`不能执行研究报告。CViT模拟中的确认、启动、OOM和恢复只发生在内存里，已有作业对账和恢复经过演示；`metric=null`，真实GPU/工具执行数为0。

研究进程独立加载各轮同名`lab`包，避免包串用；进程只读，阻止写文件、网络、外部进程及真实Agent/CViT导入，也禁止读取本地API密钥。审计钩子用于防止受信研究代码意外越界，不是对抗恶意程序的OS沙箱。

HTTP沿用受本地令牌保护的 `POST /v1/sessions/<id>/messages`，消息正文使用上述命令，仍需`Idempotency-Key`；状态与报告沿用现有GET路由。无需新增服务器端口。

交付与验收：[本轮交付](../delivery/research_online_update/README_本轮交付.md)。G2.4原隔离验收和之前迁移的“源码未变化”证明保留其历史范围；此次明确修改的6个宿主源码另有清单，冻结研究源码和权重不变。
