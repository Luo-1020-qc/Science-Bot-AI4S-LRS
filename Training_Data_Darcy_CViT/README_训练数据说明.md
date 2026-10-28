# Darcy与CViT：Harness训练数据入口

当前版本为 **v2 / `tool_harness_rl_v2`**（2026-10-28）。下一步应由专家扩充独立来源和有效决策案例，再进行训练与独立评测。数据集训练的是研究工具的选择、修订、复核和停止策略。

- **[RL训练数据专家交接文档](RL训练数据_专家交接文档.md)**：可直接发给专家，包含分工、字段说明、DOE审阅、标注与验收要求。
- **[可直接运行的RL示例批次](v2/sample_batch_001/README.md)**：3个合成任务、30个参考决策和96步实际PPO采样，包含独立训练与核验命令；不计入真人专家标签。
- [v2使用说明与RL边界](v2/README_可训练数据集.md)
- [专家扩展数据库交接手册](v2/专家扩展数据库_交接手册.md)
- [新版Darcy完整工具轨迹](v2/examples/darcy_full_example.json)
- [新版CViT完整工具轨迹](v2/examples/cvit_full_example.json)
- [版本入口配置](current_dataset.json) / [交付核验](v2/delivery_verification.json)

v2包含12个任务、134个参考决策、86条BC参考标签和31条待审决策。已另外进行64步CPU on-policy采样与1次PPO批次更新，验证RL链路能运行；真人专家标签仍为0，尚无泛化提升证据。静态参考轨迹的概率与value保留为null，不能直接冒充PPO数据。

在项目根目录执行当前版本校验：

```powershell
& '.\RUT_Science\.venv\Scripts\python.exe' -B 'Training_Data_Darcy_CViT/validate_current.py' --tests
```

原版完整快照保存在[v1](v1/README_训练数据说明.md)。本目录原有`examples/`、`manifest.json`和`validate.py`保留v1兼容行为；新增与专家交接请使用上面的v2入口。主Science Bot入口未改动。

---

## 以下为v1历史说明

下文“没有训练任何策略”等表述仅描述v1，不包括v2的CPU机械验证。

日期：2026-10-28。这个独立目录用来解释和校验下一轮训练数据结构，**没有训练任何策略，没有读取真实Darcy数组，没有训练CViT，也没有修改当前science Bot入口。**

先打开这两份完整例子：

- [Darcy任务与完整轨迹](examples/darcy_full_example.json)
- [CViT任务与完整轨迹](examples/cvit_full_example.json)

数据训练的是“如何询问、检查、设计、修正、核对作业、合理停止”，不是用系数场训练压力场预测器。真实Darcy/CViT模型的数据仍需独立准备。

## 1. 数据文件夹的结构

```text
Training_Data_Darcy_CViT/
├── README_训练数据说明.md
├── 字段与训练流程.md
├── manifest.json                 # 版本、来源、划分与逐文件SHA-256
├── tasks/
│   ├── train.jsonl               # 8个训练任务
│   ├── development.jsonl         # 2个开发示例
│   └── evaluation_example.jsonl  # 2个公开评价示例，不是盲测
├── episodes/                     # 每行一个完整回合：观察→动作→反馈→新观察
├── labels/
│   ├── bc_train.jsonl            # 35条训练决策参考标签
│   └── preferences_train.jsonl   # 4条同一观察下的方案优劣参考对
├── evaluator_only/               # 模拟器/评测器使用的场景与预期，不能输入策略
├── review/pending.jsonl          # 12条待审；专家字段为空
├── examples/                     # 两份适合人工阅读的展开JSON
├── schemas/                      # Task、Transition、未来PPO rollout的JSON Schema
├── reference_copy/               # 现有项目协议的参考副本，不导入执行
├── dataset_lib.py · schemas.py   # 本目录格式、示例评分与语义校验
├── build_examples.py             # 首次构建；已有manifest时拒绝覆盖
├── validate.py · tests/          # 本地校验及反例测试
└── validation.json               # 当前校验结果
```

JSONL每行是一个独立JSON对象，便于流式读取。`examples/`中的JSON是同一数据的展开副本，适合从IDE阅读。

## 2. 为什么分成Task、Observation、Episode和Label

| 层 | 保存什么 | 谁能看到 |
|---|---|---|
| Task envelope | 任务ID、来源分组、训练分区、数据血缘、初始观察 | 数据加载器与评测器；整包不能直接喂给策略 |
| Observation | 已到达的用户消息、已知事实、未知项、证据、草案、权限、预算、作业与历史 | 当前策略 |
| Action | 结构化动作名称和参数 | 策略提出，宿主核验 |
| Feedback | 工具/用户已返回的信息、阻断代码、来源 | 动作完成后进入下一观察；不能提前放入当前观察 |
| Episode | 每步前后观察、动作、反馈、奖励与终止标志 | 训练采样器与离线审计 |
| BC label | 某个训练观察对应的推荐动作及标签来源 | 监督训练器；不加入策略观察 |
| Evaluator-only | 场景标签、脚本反馈规则和预期分类 | 模拟器与评测器 |

`scenario_for_curator_only`、`policy_split`、`root_group`、预期答案、后续用户事实均不能成为策略特征。已有用户消息和工具证据可以进入观察，精确任务ID和数据哈希通常只用于宿主身份校验，避免学习记住身份的捷径。

动作包括：`ask`、`inspect_mock`、`propose_design`、`check_design_mock`、`revise_design`、`reconcile_job_mock`、`resume_job_mock`、`stop_with_evidence`、`submit_for_review`。所有工具名在本目录里都是示例动作，未注册为真实工具。

## 3. Darcy例子：学习识别实验单位并设计比较

用户需求：为Darcy压力场设计mean_field与ridge_field的比较，先弄清独立重复来源，本次只设计。

参考轨迹：

```text
ask(experimental_unit)
→ 用户说明：12个独立合成数据实现，各实现中运行两种预测器
→ inspect_mock：只返回训练/验证/测试不重叠等合成元数据
→ propose_design：以数据实现为区组、两种预测器为处理
→ check_design_mock
→ submit_for_review：保留待核实假设，不执行实验
```

关键区别：

- 同一个压力场上的1000个网格点是测量位置，不能直接算1000次独立方法比较。
- 固定数据上的确定性mean/ridge反复运行，不会凭空增加科学重复。
- 本例的独立性来自**假定独立生成的合成数据实现**，并非本目录实际生成或验证了这些数组。
- 每个数据实现内两种预测器配对比较；例子展示12区组、24个拟合/评价单元的结构，不声称该数量已满足真实功效。

`pseudoreplication`案例故意保留把网格点当重复的坏提案；收到`pseudo_replication`反馈后修正。坏提案保留在轨迹中，排除出BC推荐标签，并另存一个优劣方案参考对。

## 4. CViT例子：学习交互、随机化、作业身份和停止

主例需求：设计“架构×学习率”的2×2实验，考虑交互、区组、重复和验收。

| 要素 | 示例声明 |
|---|---|
| 因素A | baseline_small / candidate_small架构标签 |
| 因素B | 学习率0.0001 / 0.0003 |
| 区组 | 6个独立合成数据实现 |
| 每区组每组合 | 2次分别分配随机流的训练运行 |
| 计划运行 | 6 × 4 × 2 = 48；只是设计数量 |
| 响应 | 每个训练运行在固定测试场上的平均相对L2 |
| 分析 | 两个主效应、架构×学习率交互和数据实现区组 |
| 主要对比 | 平均于两个学习率的架构效应，事先声明 |
| 验收 | 协议完整、身份/资源匹配；科学效应、区间和实际重要性另行评价 |

轨迹先提出遗漏交互的方案，模拟检查返回`missing_interaction`，再修订完整模型。它是手写的参考教学轨迹，不代表现有PPO自动学会了修复。

每次独立训练可帮助研究**给定数据条件下的训练随机性**；同一测试场的许多样本不是许多次架构重复。数据实现的区组作用与条件残差独立性仍是声明。要推广到更多物理分布，还需要独立数据来源与分布留出。

其他CViT训练案例：

- `existing_job`：核对并复用匹配的已有模拟作业，不重复启动。
- `unknown_variance`：先询问方差来源，用户明确无法提供后停止本次有功效保证的样本量承诺；不把它扩大为“任何设计都做不了”。
- `data_changed`：旧输入身份使旧方案无效，修订后重新审阅。
- `mock_oom`：观察到OOM后保留失败依据，停止当前模拟，不虚构完成结果。

所有科学指标仍为`null`，没有真实训练或GPU资源测量。

## 5. 两种划分必须同时保存

**策略任务划分**控制Agent泛化评价：

```text
source_A → train：8任务
source_B → development：2任务
source_C → evaluation_example：2任务
```

本例让Darcy和CViT的共同底层Darcy来源留在同一分区。不能把同一数据实现的Darcy版本放训练、CViT版本放测试，然后当作独立泛化。

**实验内部划分**控制科学模型选择：

```text
mock://source_A/darcy/train       → 拟合与训练集预处理
mock://source_A/darcy/validation  → 选择模型/超参数/checkpoint
mock://source_A/darcy/test        → 方案与选择锁定后的最终评价
```

两个划分层级的“train/test”不是同一个意思。字段`policy_split`和`data_lineage.within_experiment_partition`分别记录。

这些来源身份只是本例的合成分组，不证明真实世界样本独立。12个任务及其答案都已公开，三分区还共享模板，**盲测任务数为0**。真正训练时应按真实来源/数据版本/任务生成祖先聚类划分，再另建未公开的最终集。

## 6. 这些文件如何用于训练

**BC：**读取`labels/bc_train.jsonl`，以`observation`为输入、`target_action`为目标。当前35条只是脚本参考，不是专家标签。应先人工审阅，再扩展任务；原始坏提案不能当作正确动作模仿。

**偏好训练：**`preferences_train.jsonl`保存同一观察下较优/较差提案。当前4对来自脚本纠错，不是真人偏好，不能据此声称已经进行了RLHF。它们也不自动适配某个具体语言模型训练API。

**DAgger：**未来让当前策略运行训练场景，采集它真正到达的新状态，再标注或审阅推荐动作。不能只复制这里的成功参考轨迹并称为DAgger。

**PPO：**复用任务接口和环境规则，使用当前策略重新采样。每步记录真实的行为策略log probability、critic value、奖励、下一状态与终止/截断，冻结这一批行为策略身份后进行PPO更新。参考轨迹没有这些值，所以本例统一设置为`null`、`ppo_eligible=false`。

`schemas/ppo_rollout.schema.json`说明未来采样需要的字段。不能补造old_log_probability，也不能反复将静态专家示范作为PPO的新on-policy数据。时间上限截断和真正终止应区分，计算GAE时的bootstrap规则要与训练实现一致。

本目录奖励只是演示：正确的当前协议终局+10、错误终局−10，小额步骤成本0.02；发现缺项或修复可获得小额反馈。这里的`check_design_mock`是脚本反馈，**不是G2.4固定验收器**，没有实际计算功效，也不证明DOE科学合理性。接入正式训练时应统一奖励与开发/最终验收版本，接通受支持的DOE verifier，再做专家校准。

## 7. 使用与校验

在项目根目录运行：

```powershell
& '.\RUT_Science\.venv\Scripts\python.exe' -B 'Training_Data_Darcy_CViT/validate.py' --tests
```

当前结果：12任务、12回合、61步骤、35条BC参考、4对偏好参考、12条待审，10项测试通过。检查文件哈希、来源分组、科学数据分区、观察字段、状态链、停止证据、奖励一致性、标签来源及终止边界。结果见 [validation.json](validation.json)。

schema见`schemas/`；逐字段例子与后续收集流程见 [字段与训练流程](字段与训练流程.md)。本例采用新教学协议`harness_examples_v1`，**不能直接交给现有G2.2/G2.3加载器或 `/doe validate`**；需要单独适配动作、特征与DOE契约后才能训练，不覆盖现有模型或任务库。
