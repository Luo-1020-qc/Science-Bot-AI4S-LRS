# 科研对话课程：追问 → 论文证据 → 自标注多轮对话

本目录实现独立的数据准备、监督候选训练、SFT样本导出和人工标注导入流程。当前首先使用 ClariQ；ClarQ 提供可选本地导入器；QASPER 用于证据段落排序及有证据的回答样本。原在线 Agent、API 提供者、Question tool、需求匹配器和 PPO 权重均未替换。

实际完成的是两个独立阶段的小模型训练，**不是同一个大语言模型的连续微调**。已导出的分阶段SFT样本作为历史准备制品保留；当前按[Harness主线计划](../../docs/HARNESS_PLANNING.md#下一阶段只训练harness)先做自然输入到实验设计的完整回合验收，再训练宿主决策，不开展LLM微调。第三阶段当前没有通过审核的科研多轮对话，已生成65份待标注任务；没有自动制造人工标签。

## 本轮数据与结果

| 数据 | 训练 | 开发 | 测试 | 分区单位 |
|---|---:|---:|---:|---|
| ClariQ 原始单轮记录 | 9,176 | 2,313 | 4,499 | 官方 topic |
| QASPER 问题 | 2,593 | 1,005 | 1,451 | 官方 paper |
| QASPER 论文 | 888 | 281 | 416 | 同一论文不跨区 |
| 第一步 SFT 去重问题样本 | 2,144 | 594 | 837 | 同官方分区 |
| 第二步 SFT 回答/证据标注 | 2,513 | 1,663 | 3,368 | 同官方分区，保留多标注 |

ClariQ 有187/50/61个主题；测试主题260有两种初始请求措辞，因此测试包含62种请求。两种措辞保留在同一个主题分区。第一步不把私有 facet 或后续用户回答输入提问模型，也不把上游原始问题伪装成已标注的选择题。

QASPER 保留所有5,049个问题及其无法回答、是/否、抽取式、自由回答和替代标注。段落按原文定位；无法精确对应的证据保留为未对齐项，不默认当负例。排序评估只覆盖至少有一份完整对齐且可回答标注的问题：训练2,172、开发901、测试1,337。SFT 导出略过449份无法完整对齐的标注；无法回答的标注保留。替代答案带 `annotation_weight`，同一问题不会因为标注更多而被默认赋予更高训练权重；后续训练器需消费该权重。

固定超参数的一轮诊断如下，不能解释为科研追问质量或用户理解提升：

| 留出诊断 | 对照 | 训练候选 | 结论 |
|---|---:|---:|---|
| ClariQ 问题首位命中，54种需澄清请求 | BM25 48/54 | 49/54 | 只多命中1条，未证明普遍改善 |
| ClariQ 原始四类澄清需求准确率，62种请求 | 训练集多数类 32/62 | 23/62 | 低于对照 |
| QASPER 证据 Recall@5，1,337个可对齐问题 | BM25 48.32% | 28.35% | 低于对照 |

三个候选均未部署。开发集上，问题排序首位命中与BM25持平而Recall@5更低；需求分类38%低于多数类42%；证据Recall@5为25.04%，低于BM25的44.94%。本轮没有查看测试结果后调参重跑。完整结果、训练参数、来源和决定见 [evidence/results.json](evidence/results.json)、[训练清单](evidence/public_run_manifest.json)和[部署决定](evidence/deployment_decision.json)。

训练使用固定16项词汇/段落特征的成对逻辑回归，以及512维哈希请求特征的四类分类器。它们验证真实数据上的训练链路，不具有大模型语义能力；ClariQ 的题库在训练与评测时均已知。QASPER 指标是自定义段落排序诊断，不是官方完整问答得分；未训练答案生成或无法回答分类头。模型API调用0，大模型参数更新0，真实科学实验0。

## 队友数据是否符合要求

已审核用户指定的 `Training_Data/coverage_tool_delivery_2026-10-29/coverage-tool`，只读取和核对，未执行队友脚本或改动源文件：

- 65个场景，371条候选访谈问题，424条检查项。
- 65个JSON均与索引哈希相符，65组 YAML/JSON 内容一致。
- 含对话轮次的记录0，含人工审核元数据的记录0，含证据定位的记录0。
- `executable: true` 共53项，是上游能力声明；本次未将其计为已执行、已支持或已验证。

**可用作场景、问题和审阅清单的种子，尚不符合已审核科研多轮对话的训练要求。** 来源仍是“骨架聚类表”等需求说明，不能充当论文证据。原始审计及全部源文件哈希见[队友数据审计](evidence/teammate_audit.json)。

65份待标注记录在[本地待标注队列](../../.local/scientific_dialogue_v1/annotation_001/pending.jsonl)。这些记录没有生成用户回答，默认未授权训练且未审核。同一交付包共用一个来源组，不能随机拆成训练和测试来报告泛化。独立评测仍需另收集研究/论文来源不同的对话。

## 人工标注流程

1. 从待标注队列选自己熟悉的场景。`seed` 内的问题和检查项只是候选素材，根据本轮用户回答决定是否提问。结构参考[空模板](annotation/template.json)和[不可训练的合成演示](annotation/example_NOT_TRAINING.json)。
2. 收集获得训练同意且已脱敏的真实对话，或由研究者明确创作示范。至少保留两次用户—助手交互，建议覆盖3–6轮；逐条记录真实回答、纠正、暂不确定或补充内容。模型起草后人审的数据须标为 `model_generated_human_reviewed`，不能改称真人采集。
3. 给每个助手消息标注 `decisions`。消息索引从0开始；追问需声明目标字段、依据哪些此前用户消息，并给2–4个相关且可区分的拟议选项，另含“暂不确定”和“其他”。提议不等于用户事实，不能用用户后续答案生成前一轮的问题。
4. `plan_declarations` 中区分 `declared`、`proposed` 和 `unknown`。声明值必须能逐字对应已记录的用户话语；用户明确不知道时记为unknown且值为null，尚未回答或未提及的字段留空。若引用论文，记录来源ID、段落/页码、引文、引文SHA-256和原文快照SHA-256。审核者必须打开原文核对：导入器只检查引用存在性和哈希格式/引文哈希，不能替人确认外部原文或审阅者身份。
5. 研究者审核追问质量和计划可检验性，填写1–5分、审核人、带时区时间及理由。追问质量按是否解决会改变设计的歧义、是否重复、选项是否遗漏或诱导判分；可检验性按实验单位、主要对比、指标、未知及停止条件能否核查判分。低质量样本先退回修改，不通过“填完字段”自动获得高分。
6. 研究者理解仅在有真实前后复述时标为 `assessed`，记录原话；未测量时保持 `not_assessed`。记录前后复述并不能单独证明改善，后续仍需独立盲评。不能由“用户点了确认”推断理解。
7. 在新JSONL中保存完成的标注，通过下面的 `import-reviewed` 导入。来源组稳定散列为80/10/10分区；同一来源组、相同初始请求或论文不得跨区。导入保留原标注与来源，另导出不包含审核分数、身份或未来事实的聊天SFT文件。小批次可能没有开发/测试样本，此时不能报告对应指标。

元数据验证不能证明人工审核真实发生。先从材料/化学场景做少量双人审阅、记录分歧，再扩展到其余场景；其余领域需要相应领域审核。程序不会自动把现有会话或论文文件加入数据集。

## 命令

在项目根目录运行，使用现有虚拟环境；训练另需已安装的NumPy，不下载模型。所有输出使用新目录，已存在即拒绝覆盖。原始数据、含论文全文的SFT、候选参数及待审对话保存在被Git忽略的 `.local/`，本目录只保留源码、空模板、合成演示及聚合证据。

```powershell
$py = '.\RUT_Science\.venv\Scripts\python.exe'
$entry = 'Training_Data/scientific_dialogue_v1/curriculum.py'

# 核对本轮已保存的字节、留出指标和原项目文件；不调用网络或模型
& $py -B scripts/verify_scientific_curriculum.py

# 新一轮数据准备与训练；不要复用已有输出目录
& $py -u -B $entry fetch --output .local/scientific_dialogue_replay/raw
& $py -B $entry prepare --raw .local/scientific_dialogue_replay/raw --output .local/scientific_dialogue_replay/data
& $py -u -B $entry train --data .local/scientific_dialogue_replay/data --output .local/scientific_dialogue_replay/run
& $py -B $entry export-sft --data .local/scientific_dialogue_replay/data --output .local/scientific_dialogue_replay/sft
& $py -B $entry verify --data .local/scientific_dialogue_replay/data --run .local/scientific_dialogue_replay/run

# 真实标注完成后，显式选择JSONL导入；待审队列会被拒绝
& $py -B $entry import-reviewed --input .local/reviewed_dialogues.jsonl --output .local/scientific_dialogue_reviewed_001

# 单独重跑本目录的离线测试
& $py -B -m unittest discover -s Training_Data/scientific_dialogue_v1/tests -v
```

本轮实际运行是 `.local/scientific_dialogue_v1/run_002`；`run_001` 因原始章节名为null而中断，没有完整结果或完成清单，保留在本地。修正空章节处理后运行002完成；未改动已完成候选参数来制造提升。

QASPER 解包仅在内存中读取指定JSON，不释放路径或执行上游评测脚本。训练只用train，开发/测试不参与梯度或选模；旧的训练文件和清单不改写。首次下载记录精确字节哈希，后续准备拒绝内容变更。ClarQ 的数据在作者Google Drive，当前未下载或混入本轮训练；可显式使用 `import-clarq --train <train.json> --test <test.json> --output <新目录>`，按上下文文本分组并精确查重。其 `answer` 是原帖最终答案，不能当作澄清后的用户回复。未实现语义近重复识别，正式扩充前仍须按原始帖子/论文核对来源。

## 来源、许可与验证边界

- [ClariQ 官方仓库](https://github.com/aliannejadi/ClariQ)：固定提交46885a5；该仓库未明确给出数据许可证，不冒用其他届ConvAI许可。本轮限本地研究候选，保留来源；原文和候选权重不自动对外分发，公开前需核对上游条件。
- [ClarQ 作者仓库](https://github.com/vaibhav4595/ClarQ)：固定提交cb6c6ba；作者声明CC BY 4.0，来源为自监督筛选的StackExchange帖子—评论，仍须保留原始来源署名，不等于专家问题标注。
- [QASPER 官方数据卡](https://huggingface.co/datasets/allenai/qasper)：v0.3原始JSON下载地址取自官方加载器，数据卡声明CC BY 4.0；保留论文与数据集署名。当前主要为英文NLP论文，不代表中文材料、PDE或真实科研多轮对话。

精确来源、获取时间、许可证说明及SHA-256见[数据清单](evidence/public_data_manifest.json)，训练样本清单见[SFT清单](evidence/public_sft_manifest.json)。28项新增测试通过，逐项指标独立重算通过，并核对2,462个既有运行、模型、研究、v2和队友文件未变；见[本轮验证](evidence/verification.json)。

原全仓 `scripts/check_repository.py` 在本轮修改前即因 `Training_Data_Darcy_CViT` 已改名而文档/审计仍引用旧路径失败。本轮保留历史清单，不伪报全仓通过；新增管线使用上述独立验证。目录迁移需要另设授权链处理。
