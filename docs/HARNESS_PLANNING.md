# 科研规划指南

主线：自然语言科研想法 → 有针对性的选项澄清 → 用户选择的证据 → 可检验、可解释的实验设计。研究者复核方法、结论边界和责任；工具操作见[使用说明](USAGE.md)，安装与检查见[复现说明](REPRODUCIBILITY.md)。

## 从模糊目标开始

启动后直接描述目标，或输入：

```text
/plan start 我想比较CViT和FNO，但还没明确评估方式。先澄清边界，不要直接训练。
```

每次默认展示一条简短问题和选项，可点击、输入编号、暂不确定或自由补充，也可一次回答多个字段。API模式使用原模型整理自然语言并提议选项，宿主校验后展示；离线使用字段语法和上下文候选。无依据的数字或占位边界不能通过检查，选项在用户选择前不写入账本。

动态提议失败时回退模板；冲突与过期依赖由宿主优先处理。理由和原始引用保留内部，需要时用 `/plan explain scope` 查看。默认共享12次模型请求，普通自然语言回合最多两次；查看、解释和导出不追加动态请求。

## 规划与交付命令

| 输入 | 作用 |
|---|---|
| `/plan start <目标>`、`/plan new <目标>` | 建立新规划，保留旧快照 |
| `/plan map`、`/plan draft`、`/plan review` | 查看地图、实验设计与步骤、阻断项 |
| `/plan accept scope` | 确认展示的理解或重新核对声明 |
| `/plan revise resources: 最多6次运行、3小时上限` | 更正声明并传播依赖影响 |
| `/plan explain experimental_unit`、`/plan decisions` | 查看概念解释或决策历史 |
| `/plan understanding`、`/plan reflect 我的理解是…` | 复述讨论与保存理解、疑问、异议 |
| `/plan approve <当前内容哈希>` | 确认已复核的规划版本 |
| `/plan handoff`、`/plan export` | 输出确认版本的交接，或导出JSON/Markdown |
| `/plan pause`、`/plan resume` | 暂停、继续 |

澄清完成时直接展开实验设计草案。浏览器研究计划/交付中心及终端 `/report` 随时显示当前内容，`/deliver` 导出HTML、Markdown、JSON。草案可保留未知、查证步骤和能力缺口；规划确认不启动实验。

## 状态与未知

| 状态 | 含义 |
|---|---|
| declared | 用户的规划声明，尚未验证为外部事实 |
| proposed | 模型提议或改写，待用户确认 |
| unknown | 用户明确未知，不用默认值填补 |
| conflict / stale | 声明冲突或依赖改变，须重新核对 |

关键修订使旧确认失效；改变研究目的或设计会重查实验单位、基线等依赖。计划保存原文、来源、决定和快照。声明完整不自动证明独立性、功效、因果识别或结论。

```text
/plan sampling: 未知
先查找已有先导记录，并请导师核实是否适用。
```

第二行记录为未执行的证据获取步骤，原字段仍未知。已有查证计划后等待依据；取得依据再用 `sampling: …` 更新。需要该依据的最终确认仍被阻断。

20类声明覆盖问题、目的、命题、范围、排除项、单位、因素、设计、指标、基线、来源、样本、分配、分析、验收、资源、风险、复现、责任和交付。要求随比较、预测、因果、探索、复现目的变化；11节点计划明确依赖、输入、产物、验收、责任及 implemented/mock/manual 能力，均从未执行开始。

确认后可显式输入 `/tools chat 按当前规划检查缺失参数，只做离线演练`，将已确认且无阻断的声明交给原工具规划器。实际数据、参数与执行权限仍按各工具核实。

## 显式选择论文片段

用 `-Workspace` 绑定包含文件的项目，再输入：

```text
/plan evidence add {"path":"papers/method.md","start_line":20,"end_line":65,"share_with_model":true}
/plan evidence add {"path":"papers/paper.pdf","start_page":1,"end_page":3,"share_with_model":true}
/plan evidence list
/plan evidence show <编号>
/plan evidence understand <PDF片段编号>
/plan evidence remove <编号>
```

- Markdown/TXT最多128 KiB，每段最多120行、6000字节。PDF最多16 MiB，每次选择1–12个物理PDF页，提取文字最多18000字节。最多6个片段，总计18000字节，同时遵守会话读取预算；超限要求分段，不静默截断。
- `share_with_model` 默认false，仅本地展示；显式true才用于模型澄清，移除后停止使用。不会自动读取IDE标签、父目录或文献中的链接。
- 保存选定时原文、路径、行号、文件与片段哈希。再次添加同一路径/范围才刷新；来源改变撤销旧确认并标记相关声明待重查。出处可追踪仍需核实适用性。

文字型PDF由隔离进程提取；扫描/图片页缺少可靠文字时需先OCR。页码按PDF文件中的物理顺序编号，引用显示为 `文件:P1-P3#哈希`。公式、图表与复杂排版需对照原文。

在API模式下，勾选允许模型使用所选内容，再点击“让LLM理解所选页”或使用 `understand` 命令。解读覆盖研究问题、方法、数据、结果、局限和复现信息，每条要点附原文与页码；未通过结构、引用或数值校验的要点不采用，并记录数量。结果标为模型提议，未自动写入实验声明；解释是否忠实仍需研究者审核。重复查看已保存解读不新增模型请求，解读也随规划导出。

## Question tool

自动澄清保持默认；需要记录字段问答过程时使用：

| 命令 | 用途 |
|---|---|
| `/plan question`、`/plan question rule` | 启用规则字段顺序 |
| `/plan question trained` | 显式试用合成训练的字段排序候选 |
| `/plan question history`、`/plan question export` | 查看过程、导出脱敏待审观察 |
| `/plan question off` | 关闭工具模式 |

工具只读，在合法候选内选字段；冲突/过期优先，同一版本未回答的问题复用。新选择计入工具预算，异常回退模板。观察标记为 `unreviewed_user_observation`、`ppo_eligible=false`，用户应答或点击不自动成为专家标签。

现有[字段排序候选](../RUT_Science/research/question_tool_v1/README.md)未默认启用；[上下文选项匹配器](../RUT_Science/research/context_choices_v1/README.md)用于离线/降级。二者未修改DeepSeek参数，合成课程一致性不等于真人问题质量。

## 下一阶段：只训练Harness

当前P0路径核验、P1十个案例、P2离线规则闭环与直接设计展示已完成。结果为8个完整设计、2个保留样本未知的阻断草案，见[主线报告](evaluation/mainline_2026-10-30/REPORT.md)。10例共享两个合成来源，仅作开发诊断；后续回答采用显式字段/选项，真人质量与理解尚未评估。

| 下一步 | 产物与条件 |
|---|---|
| 人工校准 | 按[评分表](evaluation/mainline_2026-10-30/RUBRIC.md)审阅问题、选项、关键遗漏和计划可检验性；记录实际前后复述及误解，未测项保持空值 |
| P3：一个决策入口 | 审核约50–100个主线状态，训练“下一项边界/证据获取问题排序”；只在合法候选内选择，停止、权限、冲突优先和确认由规则负责 |
| P4：固定条件对照 | 相同模型、候选表达、预算与回答机制下比较完整回合、遗漏、重复、成本和盲评设计；最终评价另取独立研究来源 |

50–100只是首轮建议规模。模型、数据和权重另设版本，同一研究/论文/对话及改写保持同区；评估和策略均不能读取未来答案或隐藏证据。多字段回答、纠正、明确未知和目标变化继续作为核心覆盖。

ClariQ/可选ClarQ辅助追问，QASPER辅助证据，见[数据课程与负结果](../Training_Data/scientific_dialogue_v1/README.md)。搜索意图明确不等于实验边界完整，论文无法回答不等于研究应停止。65个场景壳只作素材；[31条工具动作候选](../Training_Data/expert_batches_inbox_2026-10-30/review/REPORT.md)属于旁支，不能替代主线对话标签。

当前不做LLM微调、不扩展旧PPO，也不接入真实GPU训练。旧工具PPO的38/50低于规则/BC的50/50，见[正式负结果](../Training_Data/v2/synthetic_batch_050/formal_2026_10_29/README_训练结果.md)。没有清晰收益时继续使用规则。此前动态问题评估与人工材料保留在[历史报告](evaluation/dynamic_clarification_2026-10-29/REPORT.md)。
