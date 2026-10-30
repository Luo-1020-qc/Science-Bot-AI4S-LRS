# 统一使用说明

安装与迁移见[复现说明](REPRODUCIBILITY.md)，持续规划与论文证据见[规划指南](HARNESS_PLANNING.md)，代码和研究资源见[架构](ARCHITECTURE.md)。

## 启动与工作区

根目录运行 science-bot.cmd，默认API模式；加 -Backend offline 不调用模型。使用 -Workspace 'D:\my-project' 绑定已存在的目录。文件列表不等于内容读取授权；读取前需明确选择文件，密钥、依赖、越界路径和二进制文件不能作为普通上下文读取。

会话、任务、模型提议和工具证据分开保存。输出、会话及虚拟环境由Git忽略；历史输出不代表当前默认策略。

## 两套入口示例

| 形式 | 直接浏览 | 可交互启动 |
|---|---|---|
| 终端 | [终端预览](../examples/interfaces/terminal.html) | `.\science-bot.cmd -Example` |
| 本地浏览器 | [工作台预览](../examples/interfaces/browser.html) | `.\science-bot-web.cmd -Example` |

两者共用同一个合成研究：比较线性候选模型与非线性基线，保留待确认命题及未知的样本依据。示例只验证规划交互，不代表任何论文结论。静态浏览器预览可切换页面，修改需进入启动器创建的本地会话。

浏览器工作台和HTML交付阅读版现为红色/酒红主题，配像素等宽 `Science-Bot` 字标与机器人图标。已有页面可刷新；重启服务后新导出也使用当前配色。样式修改和验收范围见[记录](integration/branding_2026-10-29/README.md)。

左侧“最近研究”中，每条研究或对话右侧都有“删除”按钮。确认后清除该整段会话的计划、聊天、会话内导出和本地请求缓存，无法撤销；原始项目文件保留。删除当前会话后自动切换到其他研究，没有剩余会话时回到空白状态。处理中或运行中的会话须先等待或停止；删除未完成时可在原条目重试。静态预览不连接私有历史，使用浏览器启动器才能管理会话。升级后请重启本地服务并刷新页面。

终端示例依次输入：

```text
/plan accept hypothesis
/plan sampling: 固定预算先导；先核实独立性与测量流程，不宣称功效保证。
/plan review
/report
/deliver
```

浏览器示例先在右侧确认命题，再点击“填入先导示例”并发送，进入研究计划复核；确认当前版本和导出交付均由用户点击。也可以直接导出保留缺口的草案。交付中心提供 HTML 阅读版、Markdown 和 JSON，显示内容版本、确认状态与未解决项；[合成交付预览](../examples/interfaces/delivery.html)可直接打开或打印。

日常使用运行 `.\science-bot-web.cmd`，或加 `-Backend offline`；`-Workspace 'D:\my-project'`、`-Model <模型ID>` 与终端一致。浏览器服务仅监听本机，默认端口8765，可用 `-Port 8766` 更换。启动器打开的页面带本地访问凭据，刷新后如失去连接应重新运行启动器；直接输入公开地址只显示合成预览。`-NoBrowser` 用于无浏览器的服务检查。终端通过 `-Resume` 恢复，浏览器通过左侧最近会话恢复。

证据页支持工作区内PDF、Markdown和TXT。填相对路径及物理PDF页码或文本行号，默认仅本地展示。勾选允许模型使用后保存，再点“让LLM理解所选页”，获得带原文与页码的论文解读；扫描件需先OCR。范围、预算和命令见[论文证据](HARNESS_PLANNING.md#显式选择论文片段)。改动规划后旧确认失效，规划确认不授予实际实验权限。

## 常用交互

科研规划默认提供一个当前问题和上下文选项，浏览器直接点击，终端输入编号；也可选择暂不确定或自行补充。默认不展示内部追问理由或原始引用。需要看解释或来源时使用 `/plan explain <字段>` 或证据页面。已有会话可继续回答，或输入 `/plan resume` 获取当前选项。

| 输入 | 用途 |
|---|---|
| /home、/status、/model-output、/report | 查看入口、状态、模型提议或交付概览 |
| /deliver | 导出当前规划的 HTML／Markdown／JSON，允许保留缺口的草案 |
| /plan start <目标> | 从模糊目标开始澄清 |
| /plan question / /plan question trained | 启用逐项边界问答；后者显式选择合成训练候选 |
| /plan question history / export / off | 查看、导出待审训练观察或关闭工具模式 |
| /plan map、/plan draft、/plan review | 查看全貌、步骤或阻断项 |
| /plan revise <字段>: <内容> / /plan export | 明确修订或导出；完整命令见规划指南 |
| /tools list、/tools status | 查看详细工具及会话引用 |
| /tools call <工具名> <JSON> | 无需模型调用已实现离线工具 |
| /tools chat <任务> | API规划并调用离线工具，消耗共享预算 |
| /research status、/research results g2_3 | 查看范围或冻结研究结果 |
| /research simulate g2_3 --policy bc_ppo --seed 37 | 显式冻结策略开发模拟 |
| /research compare g2_3 --seed 37 | 同场景比较规则与研究策略 |
| /research verify g2_4 | 核对冻结DOE制品 |
| /doe demo、/doe report、/doe recheck | 脚本演示、最近证据或重查所选输入 |
| /doe template factorial_2x2 | 查看合成2×2协议模板 |

研究种子仅当前注册的21、37、59。G2.2可选rule/bc；G2.3可选rule/bc/bc_ppo/ppo_scratch/feedback_baseline/feedback_ppo。没有聊天重训或封存评测入口。

## CSV任务与设计访谈

显式选择CSV后，可检查列、类型与缺失，再确定问题、响应、因素、实验单位、来源、分配/抽样依据和缺失处理。当前支持独立组Welch、按单位ID匹配的配对比较，以及固定划分的均值/OLS预测。

准备方案不等于执行，宿主确认后才运行。时间、聚类和复杂因果任务不能默认当独立行；默认访谈为rule，保存BC参数不表示它优于规则。新规划确认不能代替旧CSV草案确认。

## 详细离线工具

45项契约中20项已实现并接入同一ToolRegistry；其余仍为待实现、已有能力引用、人审或真实执行禁用。普通咨询或提到工具名称不会自动授权工具集合。

```text
/tools list
/tools status
/tools call project_create {"title":"方法比较","objective":"仅离线模拟，检查方案与结论闭环"}
```

后续参数使用实际返回的project_ref、plan_ref等64位引用。制品保存在当前会话tool_library/objects，不接受任意路径，也不能跨会话直接复用。/tools call 不调用模型。

API模式下可输入：

```text
/tools chat 建立一个合成离线比较示例，完成方案复核、对齐、冻结、工作流核验、对账、模拟、分析和报告。不要把合成参数当先导依据，缺信息时提问。
```

也支持“使用详细工具库：…”前缀。原GeneralProvider、API配置及共享请求/token预算保持不变。新会话默认工具上限40；旧会话不自动提额。

- 执行经过参数、同会话制品、幂等key、预算及固定verifier检查。
- plan_patch产生新版本并清除旧活动复核/冻结引用；问题通过review_resolve处理。
- job_run_mock的scenario由宿主绑定。首次工具调用前可显式 /tools scenario benefit 或 harm 设置夹具；情景不会进入模型上下文。
- report_build要求工作流已核验、作业已对账并处理下一步；/report读取结果。
- API最终回答引用当轮实际evidence_ref；跨进程恢复检查制品哈希。模拟输出不能称为真实实验结果。

训练宿主可复用同一执行器：

```python
from rut_science.science_bot.general.conversation import GeneralSession

session = GeneralSession.create("path/to/sessions", backend="offline",
                                limits={"tool_calls": 80})
result = session.execute_library_tool(
    "project_create",
    {"title": "example", "objective": "offline tools only"},
    key="episode_001_step_000",
)
```

23个v2候选动作不等于20个工具名称。观察、mask、奖励、采样和权重仍按原研究协议保留；此入口不代表LLM已获得RL提升。契约与独立CLI见[详细工具库](../Research_Tool_Library/README_详细工具库.md)，源码接入与验证见[原工具接入记录](integration/tool_library_2026-10-28/README.md)。

## DOE协议检查

将需求与合同JSON放在绑定项目中，输入：

```text
/doe validate "request.json" "contract.json"
```

需满足G2.4闭合Schema、来源与哈希。支持两处理CRD、两处理RCBD和2×2固定效应设计，检查顺序、设计矩阵、可估计性、自由度、主要比较、条件名义功效及预算。

通过只表示可审阅，不证明真实独立性、分配过程、假设成立或科学成功。自然语言规划不会自动填写全部DOE参数；真实Darcy拟合、CViT/GPU训练、shell及源码编辑不属于详细离线工具集合。

## 专家审阅与训练数据

/research review-export g2_2 或 /doe review-export 导出待审副本，原队列与权重保留。真实审阅按协议导入版本、身份、理由与带时区时间，导入不自动训练。

新增任务和决策使用[专家交接](../Training_Data/RL训练数据_专家交接文档.md)及[v2协议](../Training_Data/v2/README_可训练数据集.md)。静态示范不能补造log probability作为PPO数据；正式采样、更新与独立评价须另有版本化证据。
