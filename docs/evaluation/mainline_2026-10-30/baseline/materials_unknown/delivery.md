# 科研任务计划

版本：13；状态：draft_with_open_questions。

本文件是待复核的规划契约，不是实验完成证明，也不授权真实工具执行。

## 已声明的边界与设计

### 研究问题

我想预测新合金样品的室温屈服强度，帮我设计评估，先厘清适用范围和数据划分。

来源状态：declared；原文：我想预测新合金样品的室温屈服强度，帮我设计评估，先厘清适用范围和数据划分。

### 研究目的

prediction

来源状态：declared；原文：研究目的：prediction

### 待检验命题

尚未明确

来源状态：missing；原文：未提供

### 研究边界

仅预测 synthetic_alloy_v1 声明成分范围内的新合金样品室温屈服强度；不外推其他工艺

来源状态：declared；原文：研究边界：仅预测 synthetic_alloy_v1 声明成分范围内的新合金样品室温屈服强度；不外推其他工艺。

### 本轮不回答的问题

不将预测相关性解释为成分因果作用，不外推新工艺或真实材料性能

来源状态：declared；原文：本轮不回答的问题：不将预测相关性解释为成分因果作用，不外推新工艺或真实材料性能。

### 实验与推断单位

同一合金批次内测量相关；以完整批次为隔离、重采样与推断单位，技术重复先按样品汇总

来源状态：declared；原文：实验与推断单位：同一合金批次内测量相关；以完整批次为隔离、重采样与推断单位，技术重复先按样品汇总。

### 因素与对比

尚未明确

来源状态：missing；原文：未提供

### 设计结构

prediction

来源状态：declared；原文：设计结构：prediction

### 主要响应与测量

先按样品汇总屈服强度误差，再报告各独立批次 MAE 的均值，越低越好；量纲为 MPa

来源状态：declared；原文：主要响应与测量：先按样品汇总屈服强度误差，再报告各独立批次 MAE 的均值，越低越好；量纲为 MPa。

### 基线与公平比较

均值预测与线性回归为基线，候选树模型共享相同批次划分、特征和调参预算

来源状态：declared；原文：基线与公平比较：均值预测与线性回归为基线，候选树模型共享相同批次划分、特征和调参预算。

### 数据与证据来源

工程诊断用 synthetic_alloy_v1；按合金批次分组隔离训练、验证和最终测试，防止技术重复泄漏

来源状态：declared；原文：数据与证据来源：工程诊断用 synthetic_alloy_v1；按合金批次分组隔离训练、验证和最终测试，防止技术重复泄漏。

### 样本与重复依据

尚未明确

来源状态：missing；原文：未提供

### 分配与偏差控制

尚未明确

来源状态：missing；原文：未提供

### 分析与不确定性

验证集仅选择超参数，冻结后只评一次最终测试；以批次为单位 bootstrap 报告 MAE 差与不确定区间

来源状态：declared；原文：分析与不确定性：验证集仅选择超参数，冻结后只评一次最终测试；以批次为单位 bootstrap 报告 MAE 差与不确定区间。

### 验收和停止规则

逐项交付最终测试误差、批次区间、基线和失败日志；阴性或不确定结果照样报告；批次无法隔离或4小时上限即停止

来源状态：declared；原文：验收和停止规则：逐项交付最终测试误差、批次区间、基线和失败日志；阴性或不确定结果照样报告；批次无法隔离或4小时上限即停止。

### 资源边界

仅规划，后续先导最多8次拟合、4小时上限；本轮不执行实验

来源状态：declared；原文：资源边界：仅规划，后续先导最多8次拟合、4小时上限；本轮不执行实验。

### 风险与未决条件

缺失批次标识、量纲不一致或样本跨划分泄漏时停止交还研究者核实

来源状态：declared；原文：风险与未决条件：缺失批次标识、量纲不一致或样本跨划分泄漏时停止交还研究者核实。

### 复现记录

保存批次划分、数据版本、代码版本、种子、配置和全部失败记录

来源状态：declared；原文：复现记录：保存批次划分、数据版本、代码版本、种子、配置和全部失败记录。

### 人类职责

学生确认预测范围，材料负责人复核批次和量纲，研究者负责结论与执行授权

来源状态：declared；原文：人类职责：学生确认预测范围，材料负责人复核批次和量纲，研究者负责结论与执行授权。

### 交付物

预测评估设计、防泄漏清单、基线对照与验收表、复现记录模板

来源状态：declared；原文：交付物：预测评估设计、防泄漏清单、基线对照与验收表、复现记录模板。

## 显式选择的论文证据

synthetic_methods.md:L1-L1#825f61b779b2ebead7f114ab762bb29e278b1ac6a9add0ef4a8f5b5277123d3c

选定时的原文快照，未经科学事实验证；workspace_id=20483d7d068b4129968240ec4d634500

> 合成文献片段，仅工程诊断：该示例不提供方差、样本量或统计功效依据。引用此片段不能填补未知数值。

拟议获取步骤（尚未执行）：样本与重复依据 · 先查找已有先导记录，再请方法负责人核实单位与样本依据。

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

- [blocked] 样本与重复依据：样本量、重复数及其依据是什么？没有方差依据时是否先做先导？
- [blocked] 样本与重复依据：用户明确尚不知道；应先规划获取证据的步骤。

## 决策与修订记录

- {'turn': 1, 'type': 'intake', 'changes': [{'field': 'research_question', 'kind': 'added', 'before': None, 'after': '我想预测新合金样品的室温屈服强度，帮我设计评估，先厘清适用范围和数据划分。'}]}
- {'turn': 2, 'type': 'intake', 'changes': [{'field': 'objective_type', 'kind': 'added', 'before': None, 'after': 'prediction'}, {'field': 'scope', 'kind': 'added', 'before': None, 'after': '仅预测 synthetic_alloy_v1 声明成分范围内的新合金样品室温屈服强度；不外推其他工艺'}, {'field': 'exclusions', 'kind': 'added', 'before': None, 'after': '不将预测相关性解释为成分因果作用，不外推新工艺或真实材料性能'}]}
- {'turn': 3, 'type': 'intake', 'changes': [{'field': 'experimental_unit', 'kind': 'added', 'before': None, 'after': '同一合金批次内测量相关；以完整批次为隔离、重采样与推断单位，技术重复先按样品汇总'}, {'field': 'design', 'kind': 'added', 'before': None, 'after': 'prediction'}, {'field': 'baseline', 'kind': 'added', 'before': None, 'after': '均值预测与线性回归为基线，候选树模型共享相同批次划分、特征和调参预算'}]}
- {'turn': 4, 'type': 'intake', 'changes': [{'field': 'outcomes', 'kind': 'added', 'before': None, 'after': '先按样品汇总屈服强度误差，再报告各独立批次 MAE 的均值，越低越好；量纲为 MPa'}, {'field': 'analysis', 'kind': 'added', 'before': None, 'after': '验证集仅选择超参数，冻结后只评一次最终测试；以批次为单位 bootstrap 报告 MAE 差与不确定区间'}, {'field': 'acceptance', 'kind': 'added', 'before': None, 'after': '逐项交付最终测试误差、批次区间、基线和失败日志；阴性或不确定结果照样报告；批次无法隔离或4小时上限即停止'}]}
- {'turn': 5, 'type': 'intake', 'changes': [{'field': 'data_source', 'kind': 'added', 'before': None, 'after': '工程诊断用 synthetic_alloy_v1；按合金批次分组隔离训练、验证和最终测试，防止技术重复泄漏'}, {'field': 'sampling', 'kind': 'unknown', 'before': None, 'after': None}]}
- {'turn': 6, 'type': 'evidence_acquisition_step', 'field': 'sampling', 'text': '先查找已有先导记录，再请方法负责人核实单位与样本依据。'}
- 已选论文片段：synthetic_methods.md:L1-L1#825f61b779b2ebead7f114ab762bb29e278b1ac6a9add0ef4a8f5b5277123d3c
- {'turn': 8, 'type': 'revise', 'changes': [{'field': 'scope', 'kind': 'revised', 'before': '仅预测 synthetic_alloy_v1 声明成分范围内的新合金样品室温屈服强度；不外推其他工艺', 'after': '仅预测 synthetic_alloy_v1 声明成分范围内的新合金样品室温屈服强度；不外推其他工艺'}]}
- {'turn': 9, 'type': 'revise', 'changes': [{'field': 'baseline', 'kind': 'revised', 'before': '均值预测与线性回归为基线，候选树模型共享相同批次划分、特征和调参预算', 'after': '均值预测与线性回归为基线，候选树模型共享相同批次划分、特征和调参预算'}]}
- {'turn': 10, 'type': 'revise', 'changes': [{'field': 'outcomes', 'kind': 'revised', 'before': '先按样品汇总屈服强度误差，再报告各独立批次 MAE 的均值，越低越好；量纲为 MPa', 'after': '先按样品汇总屈服强度误差，再报告各独立批次 MAE 的均值，越低越好；量纲为 MPa'}, {'field': 'analysis', 'kind': 'revised', 'before': '验证集仅选择超参数，冻结后只评一次最终测试；以批次为单位 bootstrap 报告 MAE 差与不确定区间', 'after': '验证集仅选择超参数，冻结后只评一次最终测试；以批次为单位 bootstrap 报告 MAE 差与不确定区间'}, {'field': 'acceptance', 'kind': 'revised', 'before': '逐项交付最终测试误差、批次区间、基线和失败日志；阴性或不确定结果照样报告；批次无法隔离或4小时上限即停止', 'after': '逐项交付最终测试误差、批次区间、基线和失败日志；阴性或不确定结果照样报告；批次无法隔离或4小时上限即停止'}]}
- {'turn': 11, 'type': 'intake', 'changes': [{'field': 'resources', 'kind': 'added', 'before': None, 'after': '仅规划，后续先导最多8次拟合、4小时上限；本轮不执行实验'}, {'field': 'risks', 'kind': 'added', 'before': None, 'after': '缺失批次标识、量纲不一致或样本跨划分泄漏时停止交还研究者核实'}, {'field': 'reproducibility', 'kind': 'added', 'before': None, 'after': '保存批次划分、数据版本、代码版本、种子、配置和全部失败记录'}, {'field': 'human_roles', 'kind': 'added', 'before': None, 'after': '学生确认预测范围，材料负责人复核批次和量纲，研究者负责结论与执行授权'}, {'field': 'deliverable', 'kind': 'added', 'before': None, 'after': '预测评估设计、防泄漏清单、基线对照与验收表、复现记录模板'}]}

## 人类认知检查

- 我们要回答什么，不准备声称什么？
- 为什么选择当前设计，合理替代方案是什么？
- 什么结果会改变判断，哪些未知仍未解决？
- 谁负责执行、核实证据及批准最终结论？
- 何时停止、修订或交还人工判断？
