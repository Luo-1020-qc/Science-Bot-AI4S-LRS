# 科研任务计划

版本：14；状态：reviewable_plan。

本文件是待复核的规划契约，不是实验完成证明，也不授权真实工具执行。

## 已声明的边界与设计

### 研究问题

在声明的合成数据范围内比较CViT与FNO误差，决定是否值得追加验证。

来源状态：declared；原文："research_question": "在声明的合成数据范围内比较CViT与FNO误差，决定是否值得追加验证。"

### 研究目的

comparison

来源状态：declared；原文：我想比较CViT和FNO

### 待检验命题

候选减基线的relative_l2均值差至少下降0.01。

来源状态：declared；原文："hypothesis": "候选减基线的relative_l2均值差至少下降0.01。"

### 研究边界

只限声明的合成数据版本与固定计算预算，不推广到其他PDE或真实样本。

来源状态：declared；原文："scope": "只限声明的合成数据版本与固定计算预算，不推广到其他PDE或真实样本。"

### 本轮不回答的问题

不宣称广泛泛化或因果机制，也不把本次规划当真实训练结果。

来源状态：declared；原文："exclusions": "不宣称广泛泛化或因果机制，也不把本次规划当真实训练结果。"

### 实验与推断单位

一次独立分配的合成训练运行作为实验单位，共享数据与独立性需研究者复核；不把网格点当重复。

来源状态：declared；原文："experimental_unit": "一次独立分配的合成训练运行作为实验单位，共享数据与独立性需研究者复核；不把网格点当重复。"

### 因素与对比

模型两个水平FNO与CViT，主要对比候选减基线；其余训练配置预先固定。

来源状态：declared；原文："factors": "模型两个水平FNO与CViT，主要对比候选减基线；其余训练配置预先固定。"

### 设计结构

crd

来源状态：declared；原文："design": "crd"

### 主要响应与测量

主要指标relative_l2，越低越好，按每个独立运行汇总误差。

来源状态：declared；原文："outcomes": "主要指标relative_l2，越低越好，按每个独立运行汇总误差。"

### 基线与公平比较

FNO与候选使用同一数据版本、固定预算和评价协议。

来源状态：declared；原文："baseline": "FNO与候选使用同一数据版本、固定预算和评价协议。"

### 数据与证据来源

仅为合成示例mock://planning-demo，不读取真实数据。正式执行另核实训练/验证/测试版本和泄漏。

来源状态：declared；原文："data_source": "仅为合成示例mock://planning-demo，不读取真实数据。正式执行另核实训练/验证/测试版本和泄漏。"

### 样本与重复依据

先做先导再确定训练重复数和方差依据；当前不宣称正式功效保证。

来源状态：declared；原文："sampling": "先做先导再确定训练重复数和方差依据；当前不宣称正式功效保证。"

### 分配与偏差控制

独立运行分配顺序抽签随机化，记录seed与实际顺序，执行前复核独立性。

来源状态：declared；原文："randomization": "独立运行分配顺序抽签随机化，记录seed与实际顺序，执行前复核独立性。"

### 分析与不确定性

估计候选减基线均值差并报告95%置信区间；先导后核对模型与误差假设。

来源状态：declared；原文："analysis": "估计候选减基线均值差并报告95%置信区间；先导后核对模型与误差假设。"

### 验收和停止规则

检查所有预定交付；实际意义阈值0.01，报告效应与区间；阴性和不确定结果也交付，预算耗尽或关键依据缺失时停止。

来源状态：declared；原文："acceptance": "检查所有预定交付；实际意义阈值0.01，报告效应与区间；阴性和不确定结果也交付，预算耗尽或关键依据缺失时停止。"

### 资源边界

先导最多8次运行、4小时上限；正式预算由研究者另定，不由Agent增加。

来源状态：declared；原文："resources": "先导最多8次运行、4小时上限；正式预算由研究者另定，不由Agent增加。"

### 风险与未决条件

共享数据、独立性与模型假设未验证，先导失败时人工复核停止。

来源状态：declared；原文："risks": "共享数据、独立性与模型假设未验证，先导失败时人工复核停止。"

### 复现记录

记录数据hash、代码git版本、seed、配置、日志与方案偏离。

来源状态：declared；原文："reproducibility": "记录数据hash、代码git版本、seed、配置、日志与方案偏离。"

### 人类职责

研究者确认边界和方法，学生负责执行，导师复核并批准结论。

来源状态：declared；原文："human_roles": "研究者确认边界和方法，学生负责执行，导师复核并批准结论。"

### 交付物

完整可复现的先导方案、区间表模板、决策记录与局限说明。

来源状态：declared；原文："deliverable": "完整可复现的先导方案、区间表模板、决策记录与局限说明。"

## 步骤、依赖与验收

### boundaries：明确要回答的问题和不能外推的边界

依赖：无

输入：research_question、objective_type、scope、exclusions

输出：问题与边界契约

验收：研究者用自己的话确认问题、范围和排除项；模型建议保持待确认身份。

责任：研究者与Agent协作

能力：implemented；尚未执行。

### evidence_inventory：区分已知声明、实际证据和未决信息

依赖：boundaries

输入：data_source、experimental_unit、risks

输出：证据来源清单、未决问题清单

验收：每项关键事实有来源或明确未知；真实单位独立性与测量质量需外部核实。

责任：研究者提供与核实，Agent整理

能力：manual；尚未执行。

### design：选择能检验命题的设计并说明合理替代方案

依赖：evidence_inventory

输入：hypothesis、factors、design、baseline、sampling、randomization

输出：实验分配与分析单位说明、样本/先导依据、方案候选与取舍

验收：对比可估计；单位、重复、区组和随机化关系明确；未知功效条件不能被默认值替代。

责任：研究者选择，方法专家复核

能力：manual；尚未执行。

### acceptance：预先锁定分析、验收和停止规则

依赖：design

输入：outcomes、analysis、acceptance、resources

输出：主要指标与对比、分析及不确定性规则、验收/停止检查表

验收：区分能否检验命题与证据是否支持；预设阴性和不确定结果处理，禁止按结果改阈值。

责任：研究者确认，Agent检查声明完整性

能力：implemented；尚未执行。

### human_review：在执行前复核假设、可行性与责任

依赖：acceptance

输入：human_roles、risks、reproducibility

输出：人工复核记录、批准版本或修订理由

验收：逐项检查来源、统计/领域假设、资源及工具能力；修订关键事实后原确认失效。

责任：指定的人类复核者

能力：manual；尚未执行。

### preregister：冻结当前计划及其验收规则

依赖：human_review

输入：完整计划、人工确认记录

输出：带版本和来源的计划快照

验收：确认绑定当前版本，计划变更重新复核；计划确认不等于真实工具执行授权。

责任：研究者确认，宿主保存

能力：implemented；尚未执行。

### mock_rehearsal：可选：演练受支持工具闭环，不制造实测证据

依赖：preregister

输入：明确受支持的设计映射

输出：模拟工具轨迹、能力缺口清单

验收：仅显式进入详细工具库后运行；模拟输出明确标记，不能当作真实实验结论。

责任：Agent在宿主约束内

能力：mock；尚未执行。

### execute：按锁定计划采集数据或执行研究步骤

依赖：preregister

输入：人工授权、真实环境与数据、冻结计划

输出：原始观测、实际分配与偏离记录、失败和资源记录

验收：真实任务由人类或另行接入的受限执行器完成；不能因已有工具契约而宣称已经执行。

责任：人类研究者/单独授权的执行器

能力：manual；尚未执行。

### analyze：依据预先声明的方法分析结果并检查偏离

依赖：execute

输入：真实观测与版本、冻结分析规则

输出：估计量与不确定性、诊断和偏离说明

验收：不把技术重复当独立样本；不反复选方法直到显著；自动分析须先核对具体工具支持范围。

责任：研究者负责，Agent可辅助解释

能力：manual；尚未执行。

### claim_review：判断证据支持什么，以及仍不能判断什么

依赖：analyze

输入：命题、分析输出、假设与外推限制

输出：支持/不支持/不确定的结论、限制与替代解释

验收：设计可检验不等于结果支持；阴性、反向及不确定结果同样记录，因果与泛化不超出证据。

责任：人类研究者作最终判断

能力：manual；尚未执行。

### report：交付可追踪报告并选择下一步

依赖：claim_review

输入：deliverable、reproducibility、全程决策与偏离记录

输出：研究报告与复现清单、下一步或停止理由

验收：交付包含边界、设计选择、关键证据、局限、负结果和人类职责；新问题另开版本，不事后重写原验收。

责任：研究者签署，Agent整理

能力：manual；尚未执行。

## 未决问题与复核提醒

- [needs_review] 样本与重复依据：本计划不自动计算或证明功效；参数来源和计算须单独复核。

## 决策与修订记录

- {'turn': 1, 'type': 'intake', 'changes': [{'field': 'research_question', 'kind': 'added', 'before': None, 'after': '比较CViT和FNO，判断是否值得继续投入'}, {'field': 'objective_type', 'kind': 'added', 'before': None, 'after': 'comparison'}, {'field': 'factors', 'kind': 'added', 'before': None, 'after': '模型/方法：CViT 与 FNO'}, {'field': 'data_source', 'kind': 'added', 'before': None, 'after': '目前只有一个小数据集'}, {'field': 'reproducibility', 'kind': 'added', 'before': None, 'after': '希望结果可复现'}, {'field': 'analysis', 'kind': 'unknown', 'before': None, 'after': None}]}
- {'turn': 2, 'type': 'human_restatement', 'fields': ['research_question', 'factors'], 'meaning': '用户确认自己计划中的声明；未验证科学事实'}
- {'turn': 3, 'type': 'revise', 'changes': [{'field': 'research_question', 'kind': 'revised', 'before': '比较CViT和FNO，判断是否值得继续投入', 'after': '在声明的合成数据范围内比较CViT与FNO误差，决定是否值得追加验证。'}, {'field': 'hypothesis', 'kind': 'added', 'before': None, 'after': '候选减基线的relative_l2均值差至少下降0.01。'}, {'field': 'scope', 'kind': 'added', 'before': None, 'after': '只限声明的合成数据版本与固定计算预算，不推广到其他PDE或真实样本。'}, {'field': 'exclusions', 'kind': 'added', 'before': None, 'after': '不宣称广泛泛化或因果机制，也不把本次规划当真实训练结果。'}]}
- {'turn': 4, 'type': 'revise', 'changes': [{'field': 'experimental_unit', 'kind': 'added', 'before': None, 'after': '一次独立分配的合成训练运行作为实验单位，共享数据与独立性需研究者复核；不把网格点当重复。'}, {'field': 'factors', 'kind': 'revised', 'before': '模型/方法：CViT 与 FNO', 'after': '模型两个水平FNO与CViT，主要对比候选减基线；其余训练配置预先固定。'}, {'field': 'design', 'kind': 'added', 'before': None, 'after': 'crd'}, {'field': 'outcomes', 'kind': 'added', 'before': None, 'after': '主要指标relative_l2，越低越好，按每个独立运行汇总误差。'}, {'field': 'baseline', 'kind': 'added', 'before': None, 'after': 'FNO与候选使用同一数据版本、固定预算和评价协议。'}]}
- {'turn': 5, 'type': 'revise', 'changes': [{'field': 'data_source', 'kind': 'revised', 'before': '目前只有一个小数据集', 'after': '仅为合成示例mock://planning-demo，不读取真实数据。正式执行另核实训练/验证/测试版本和泄漏。'}, {'field': 'sampling', 'kind': 'added', 'before': None, 'after': '先做先导再确定训练重复数和方差依据；当前不宣称正式功效保证。'}, {'field': 'randomization', 'kind': 'added', 'before': None, 'after': '独立运行分配顺序抽签随机化，记录seed与实际顺序，执行前复核独立性。'}, {'field': 'analysis', 'kind': 'added', 'before': None, 'after': '估计候选减基线均值差并报告95%置信区间；先导后核对模型与误差假设。'}, {'field': 'acceptance', 'kind': 'added', 'before': None, 'after': '检查所有预定交付；实际意义阈值0.01，报告效应与区间；阴性和不确定结果也交付，预算耗尽或关键依据缺失时停止。'}]}
- {'turn': 6, 'type': 'revise', 'changes': [{'field': 'resources', 'kind': 'added', 'before': None, 'after': '先导最多8次运行、4小时上限；正式预算由研究者另定，不由Agent增加。'}, {'field': 'risks', 'kind': 'added', 'before': None, 'after': '共享数据、独立性与模型假设未验证，先导失败时人工复核停止。'}, {'field': 'reproducibility', 'kind': 'revised', 'before': '希望结果可复现', 'after': '记录数据hash、代码git版本、seed、配置、日志与方案偏离。'}, {'field': 'human_roles', 'kind': 'added', 'before': None, 'after': '研究者确认边界和方法，学生负责执行，导师复核并批准结论。'}, {'field': 'deliverable', 'kind': 'added', 'before': None, 'after': '完整可复现的先导方案、区间表模板、决策记录与局限说明。'}]}
- {'turn': 8, 'type': 'human_restatement', 'fields': ['scope'], 'meaning': '用户确认自己计划中的声明；未验证科学事实'}
- {'turn': 12, 'type': 'human_plan_approval', 'contract_hash': 'f8b9add04155a4eaffb6453aa8b896ae694bf6b64dccba28700a88d3892f3203'}

## 人类认知检查

- 我们要回答什么，不准备声称什么？
- 为什么选择当前设计，合理替代方案是什么？
- 什么结果会改变判断，哪些未知仍未解决？
- 谁负责执行、核实证据及批准最终结论？
- 何时停止、修订或交还人工判断？
