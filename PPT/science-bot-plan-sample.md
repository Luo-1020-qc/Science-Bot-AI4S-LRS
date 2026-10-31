# 科研任务计划

版本：22；状态：reviewable_plan。

本文件是待复核的规划契约，不是实验完成证明，也不授权真实工具执行。

声明状态：已齐全；方法状态：待人工复核，尚未验证科学有效性。

## 实验设计初稿

实验设计草案（规划，尚未执行）
声明状态：已齐全；方法状态：待人工复核，尚未验证科学有效性。
本轮未取得有效的模型实验初稿，已保留字段与模板路径；可用 /plan synthesize refresh 重试。

问题与结论边界
- 研究问题：比较模型甲乙在合成二维场上的误差与耗时
- 研究目的：比较
- 待检验命题：检验限定条件下候选与基线的主要响应差异，允许没有差异或反向结果。
- 研究边界：合成二维场上的比较
- 本轮不回答的问题：本轮不声称未测试对象、数据分布或条件下仍有效。

实验设计与主要对比
- 设计结构：独立随机分配
- 实验与推断单位：每个独立研究对象作为推断单位，同一对象的多次测量先在对象内汇总。
- 因素与对比：模型（甲、乙）
- 基线与公平比较：选择研究者确认的基线，使用相同数据划分、预算和评估流程，保留所有结果。

数据、样本与分配
- 数据与证据来源：由研究者明确选择已有数据，登记来源与版本；训练、验证和最终测试分别使用，按对象隔离以防泄漏。
- 样本与重复依据：先做先导核实方差、独立性与测量流程，不宣称功效保证，后续再确定样本与重复。
- 分配与偏差控制：按独立单位实施并记录随机分配和运行顺序，保留种子与分配日志。

指标与分析
- 主要响应与测量：按独立单位汇总预测误差均值，越低越好；成本作为辅助指标。
- 分析与不确定性：估计独立单位层面的候选与基线差异，报告区间或其他不确定性，并保留阴性结果。

验收、阴性结果与停止
- 验收和停止规则：逐项核对数据、配置、全部结果与可复现记录；不支持或不确定结果也交付，预算达到上限即停止。
- 资源边界：最多2小时
- 风险与未决条件：优先核查数据泄漏、共享对象与独立性假设；证据不足时停止并交还研究者判断。

复现、交付与责任
- 复现记录：保存代码和数据版本、配置、种子、运行日志、失败及阴性结果。
- 交付物：实验初稿（仅规划）
- 人类职责：研究者负责确认边界、复核方案和结论；执行人员及授权在实际作业前明确。

待核对事项
- 样本与重复依据：本计划不自动计算或证明功效；参数来源和计算须单独复核。

已显式选择 0 个来源片段；声明和出处仍需核实。
核对下列设计、方法假设与责任，再决定是否确认当前版本。

## 已声明的边界与设计

### 研究问题

比较模型甲乙在合成二维场上的误差与耗时

来源状态：declared；原文：比较模型甲乙在合成二维场上的误差与耗时

### 研究目的

comparison

来源状态：declared；原文：比较模型甲乙在合成二维场上的误差与耗时

### 待检验命题

检验限定条件下候选与基线的主要响应差异，允许没有差异或反向结果。

来源状态：declared；原文：用户选择：比较候选与基线的差异

### 研究边界

合成二维场上的比较

来源状态：declared；原文：在合成二维场上

### 本轮不回答的问题

本轮不声称未测试对象、数据分布或条件下仍有效。

来源状态：declared；原文：用户选择：不做未测试条件下的外推

### 实验与推断单位

每个独立研究对象作为推断单位，同一对象的多次测量先在对象内汇总。

来源状态：declared；原文：用户选择：按独立对象汇总

### 因素与对比

模型（甲、乙）

来源状态：declared；原文：比较模型甲乙

### 设计结构

crd

来源状态：declared；原文：用户选择：独立随机分配

### 主要响应与测量

按独立单位汇总预测误差均值，越低越好；成本作为辅助指标。

来源状态：declared；原文：用户选择：以预测误差为主

### 基线与公平比较

选择研究者确认的基线，使用相同数据划分、预算和评估流程，保留所有结果。

来源状态：declared；原文：用户选择：使用同数据、同预算的基线

### 数据与证据来源

由研究者明确选择已有数据，登记来源与版本；训练、验证和最终测试分别使用，按对象隔离以防泄漏。

来源状态：declared；原文：用户选择：使用已有数据并登记版本

### 样本与重复依据

先做先导核实方差、独立性与测量流程，不宣称功效保证，后续再确定样本与重复。

来源状态：declared；原文：用户选择：先做先导获取依据

### 分配与偏差控制

按独立单位实施并记录随机分配和运行顺序，保留种子与分配日志。

来源状态：declared；原文：用户选择：记录实际分配过程

### 分析与不确定性

估计独立单位层面的候选与基线差异，报告区间或其他不确定性，并保留阴性结果。

来源状态：declared；原文：用户选择：比较单位层面的差异与区间

### 验收和停止规则

逐项核对数据、配置、全部结果与可复现记录；不支持或不确定结果也交付，预算达到上限即停止。

来源状态：declared；原文：用户选择：按产物完整性验收

### 资源边界

最多2小时

来源状态：declared；原文：最多2小时

### 风险与未决条件

优先核查数据泄漏、共享对象与独立性假设；证据不足时停止并交还研究者判断。

来源状态：declared；原文：用户选择：重点检查数据与独立性

### 复现记录

保存代码和数据版本、配置、种子、运行日志、失败及阴性结果。

来源状态：declared；原文：用户选择：保存版本、配置与全部结果

### 人类职责

研究者负责确认边界、复核方案和结论；执行人员及授权在实际作业前明确。

来源状态：declared；原文：用户选择：由我确认边界和结论

### 交付物

实验初稿（仅规划）

来源状态：declared；原文：请先给实验初稿，只规划

## 显式选择的论文证据

尚未选择；不从论文名字或IDE标签推断内容。

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

- {'turn': 1, 'type': 'intake', 'changes': [{'field': 'research_question', 'kind': 'added', 'before': None, 'after': '比较模型甲乙在合成二维场上的误差与耗时'}, {'field': 'objective_type', 'kind': 'added', 'before': None, 'after': 'comparison'}, {'field': 'factors', 'kind': 'added', 'before': None, 'after': '模型（甲、乙）'}, {'field': 'outcomes', 'kind': 'added', 'before': None, 'after': '误差与耗时'}, {'field': 'scope', 'kind': 'added', 'before': None, 'after': '合成二维场上的比较'}, {'field': 'resources', 'kind': 'added', 'before': None, 'after': '最多2小时'}, {'field': 'deliverable', 'kind': 'added', 'before': None, 'after': '实验初稿（仅规划）'}]}
- {'turn': 1, 'type': 'update_receipt', 'fields': {'research_question': 'declared', 'objective_type': 'declared', 'factors': 'proposed', 'outcomes': 'declared', 'scope': 'proposed', 'resources': 'declared', 'deliverable': 'proposed'}}
- {'turn': 2, 'type': 'human_restatement', 'fields': ['factors'], 'meaning': '用户确认自己计划中的声明；未验证科学事实'}
- {'turn': 2, 'type': 'human_choice', 'field': 'factors', 'choice_id': '8c24ee4a38ee726e', 'option_id': '63a55f890888', 'action': 'accept', 'meaning': '用户选择的规划声明或拟议步骤，未验证外部事实'}
- {'turn': 2, 'type': 'update_receipt', 'fields': {'factors': 'declared'}}
- {'turn': 3, 'type': 'human_restatement', 'fields': ['scope'], 'meaning': '用户确认自己计划中的声明；未验证科学事实'}
- {'turn': 3, 'type': 'human_choice', 'field': 'scope', 'choice_id': '959e597b801d46fd', 'option_id': '350136feb59f', 'action': 'accept', 'meaning': '用户选择的规划声明或拟议步骤，未验证外部事实'}
- {'turn': 3, 'type': 'update_receipt', 'fields': {'scope': 'declared'}}
- {'turn': 4, 'type': 'human_restatement', 'fields': ['deliverable'], 'meaning': '用户确认自己计划中的声明；未验证科学事实'}
- {'turn': 4, 'type': 'human_choice', 'field': 'deliverable', 'choice_id': '0695e949bc6916c4', 'option_id': 'f306ce1a1e4d', 'action': 'accept', 'meaning': '用户选择的规划声明或拟议步骤，未验证外部事实'}
- {'turn': 4, 'type': 'update_receipt', 'fields': {'deliverable': 'declared'}}
- {'turn': 5, 'type': 'intake', 'changes': [{'field': 'hypothesis', 'kind': 'added', 'before': None, 'after': '检验限定条件下候选与基线的主要响应差异，允许没有差异或反向结果。'}]}
- {'turn': 5, 'type': 'human_choice', 'field': 'hypothesis', 'choice_id': 'e267929206d5ea13', 'option_id': '0d59790dd5ff', 'action': 'declare', 'meaning': '用户选择的规划声明或拟议步骤，未验证外部事实'}
- {'turn': 5, 'type': 'update_receipt', 'fields': {'hypothesis': 'declared'}}
- {'turn': 6, 'type': 'intake', 'changes': [{'field': 'exclusions', 'kind': 'added', 'before': None, 'after': '本轮不声称未测试对象、数据分布或条件下仍有效。'}]}
- {'turn': 6, 'type': 'human_choice', 'field': 'exclusions', 'choice_id': 'e8eebb3b660a1c8c', 'option_id': 'e3d79640993f', 'action': 'declare', 'meaning': '用户选择的规划声明或拟议步骤，未验证外部事实'}
- {'turn': 6, 'type': 'update_receipt', 'fields': {'exclusions': 'declared'}}
- {'turn': 7, 'type': 'intake', 'changes': [{'field': 'experimental_unit', 'kind': 'added', 'before': None, 'after': '每个独立研究对象作为推断单位，同一对象的多次测量先在对象内汇总。'}]}
- {'turn': 7, 'type': 'human_choice', 'field': 'experimental_unit', 'choice_id': '5c5a06d502c3d636', 'option_id': '7f4f77dbe821', 'action': 'declare', 'meaning': '用户选择的规划声明或拟议步骤，未验证外部事实'}
- {'turn': 7, 'type': 'update_receipt', 'fields': {'experimental_unit': 'declared'}}
- {'turn': 8, 'type': 'intake', 'changes': [{'field': 'design', 'kind': 'added', 'before': None, 'after': 'crd'}]}
- {'turn': 8, 'type': 'human_choice', 'field': 'design', 'choice_id': '7634ff39ada8eefb', 'option_id': '5e5eebebef8a', 'action': 'declare', 'meaning': '用户选择的规划声明或拟议步骤，未验证外部事实'}
- {'turn': 8, 'type': 'update_receipt', 'fields': {'design': 'declared'}}
- {'turn': 9, 'type': 'intake', 'changes': [{'field': 'baseline', 'kind': 'added', 'before': None, 'after': '选择研究者确认的基线，使用相同数据划分、预算和评估流程，保留所有结果。'}]}
- {'turn': 9, 'type': 'human_choice', 'field': 'baseline', 'choice_id': '5763cfe384f66688', 'option_id': '68e45e5d3ec4', 'action': 'declare', 'meaning': '用户选择的规划声明或拟议步骤，未验证外部事实'}
- {'turn': 9, 'type': 'update_receipt', 'fields': {'baseline': 'declared'}}
- {'turn': 10, 'type': 'intake', 'changes': [{'field': 'data_source', 'kind': 'added', 'before': None, 'after': '由研究者明确选择已有数据，登记来源与版本；训练、验证和最终测试分别使用，按对象隔离以防泄漏。'}]}
- {'turn': 10, 'type': 'human_choice', 'field': 'data_source', 'choice_id': 'b815908f8040f9f7', 'option_id': '032ed53fff82', 'action': 'declare', 'meaning': '用户选择的规划声明或拟议步骤，未验证外部事实'}
- {'turn': 10, 'type': 'update_receipt', 'fields': {'data_source': 'declared'}}
- {'turn': 11, 'type': 'intake', 'changes': [{'field': 'sampling', 'kind': 'added', 'before': None, 'after': '先做先导核实方差、独立性与测量流程，不宣称功效保证，后续再确定样本与重复。'}]}
- {'turn': 11, 'type': 'human_choice', 'field': 'sampling', 'choice_id': '5afb5b9a28b721e6', 'option_id': '0c24c8b7b640', 'action': 'declare', 'meaning': '用户选择的规划声明或拟议步骤，未验证外部事实'}
- {'turn': 11, 'type': 'update_receipt', 'fields': {'sampling': 'declared'}}
- {'turn': 12, 'type': 'intake', 'changes': [{'field': 'randomization', 'kind': 'added', 'before': None, 'after': '按独立单位实施并记录随机分配和运行顺序，保留种子与分配日志。'}]}
- {'turn': 12, 'type': 'human_choice', 'field': 'randomization', 'choice_id': '63af4ad72cf189ad', 'option_id': '1feab774bfa7', 'action': 'declare', 'meaning': '用户选择的规划声明或拟议步骤，未验证外部事实'}
- {'turn': 12, 'type': 'update_receipt', 'fields': {'randomization': 'declared'}}
- {'turn': 13, 'type': 'intake', 'changes': [{'field': 'analysis', 'kind': 'added', 'before': None, 'after': '估计独立单位层面的候选与基线差异，报告区间或其他不确定性，并保留阴性结果。'}]}
- {'turn': 13, 'type': 'human_choice', 'field': 'analysis', 'choice_id': '58864eafc6b70cfa', 'option_id': 'c2da332ce9cc', 'action': 'declare', 'meaning': '用户选择的规划声明或拟议步骤，未验证外部事实'}
- {'turn': 13, 'type': 'update_receipt', 'fields': {'analysis': 'declared'}}
- {'turn': 14, 'type': 'intake', 'changes': [{'field': 'acceptance', 'kind': 'added', 'before': None, 'after': '逐项核对数据、配置、全部结果与可复现记录；不支持或不确定结果也交付，预算达到上限即停止。'}]}
- {'turn': 14, 'type': 'human_choice', 'field': 'acceptance', 'choice_id': 'cde060617582bbcb', 'option_id': 'ff4ab6f4c579', 'action': 'declare', 'meaning': '用户选择的规划声明或拟议步骤，未验证外部事实'}
- {'turn': 14, 'type': 'update_receipt', 'fields': {'acceptance': 'declared'}}
- {'turn': 15, 'type': 'intake', 'changes': [{'field': 'risks', 'kind': 'added', 'before': None, 'after': '优先核查数据泄漏、共享对象与独立性假设；证据不足时停止并交还研究者判断。'}]}
- {'turn': 15, 'type': 'human_choice', 'field': 'risks', 'choice_id': '1d8349b44adf2ff2', 'option_id': '37b9f893b245', 'action': 'declare', 'meaning': '用户选择的规划声明或拟议步骤，未验证外部事实'}
- {'turn': 15, 'type': 'update_receipt', 'fields': {'risks': 'declared'}}
- {'turn': 16, 'type': 'intake', 'changes': [{'field': 'reproducibility', 'kind': 'added', 'before': None, 'after': '保存代码和数据版本、配置、种子、运行日志、失败及阴性结果。'}]}
- {'turn': 16, 'type': 'human_choice', 'field': 'reproducibility', 'choice_id': '7935db9045513c4f', 'option_id': 'c53afd30e6da', 'action': 'declare', 'meaning': '用户选择的规划声明或拟议步骤，未验证外部事实'}
- {'turn': 16, 'type': 'update_receipt', 'fields': {'reproducibility': 'declared'}}
- {'turn': 17, 'type': 'intake', 'changes': [{'field': 'human_roles', 'kind': 'added', 'before': None, 'after': '研究者负责确认边界、复核方案和结论；执行人员及授权在实际作业前明确。'}]}
- {'turn': 17, 'type': 'human_choice', 'field': 'human_roles', 'choice_id': 'f068bc45bcf56f4e', 'option_id': '434cbbe9a5cf', 'action': 'declare', 'meaning': '用户选择的规划声明或拟议步骤，未验证外部事实'}
- {'turn': 17, 'type': 'update_receipt', 'fields': {'human_roles': 'declared'}}
- {'turn': 18, 'type': 'revise', 'changes': [{'field': 'outcomes', 'kind': 'revised', 'before': '误差与耗时', 'after': '按独立单位汇总预测误差均值，越低越好；成本作为辅助指标。'}]}
- {'turn': 18, 'type': 'human_choice', 'field': 'outcomes', 'choice_id': 'e4d37cc7f1a9f683', 'option_id': 'db89d2af30e2', 'action': 'revise', 'meaning': '用户选择的规划声明或拟议步骤，未验证外部事实'}
- {'turn': 18, 'type': 'update_receipt', 'fields': {'outcomes': 'declared'}}
- {'turn': 19, 'type': 'human_restatement', 'fields': ['hypothesis'], 'meaning': '用户确认自己计划中的声明；未验证科学事实'}
- {'turn': 19, 'type': 'human_choice', 'field': 'hypothesis', 'choice_id': '4b093bf7cbc652e2', 'option_id': '92fa506f9cac', 'action': 'accept', 'meaning': '用户选择的规划声明或拟议步骤，未验证外部事实'}
- {'turn': 19, 'type': 'update_receipt', 'fields': {'hypothesis': 'declared'}}
- {'turn': 20, 'type': 'human_restatement', 'fields': ['analysis'], 'meaning': '用户确认自己计划中的声明；未验证科学事实'}
- {'turn': 20, 'type': 'human_choice', 'field': 'analysis', 'choice_id': '9313a0e3d0d93c2b', 'option_id': '5a13e9025d8e', 'action': 'accept', 'meaning': '用户选择的规划声明或拟议步骤，未验证外部事实'}
- {'turn': 20, 'type': 'update_receipt', 'fields': {'analysis': 'declared'}}
- {'turn': 21, 'type': 'human_restatement', 'fields': ['acceptance'], 'meaning': '用户确认自己计划中的声明；未验证科学事实'}
- {'turn': 21, 'type': 'human_choice', 'field': 'acceptance', 'choice_id': 'ab40e228f117e16e', 'option_id': '7a7f88eef323', 'action': 'accept', 'meaning': '用户选择的规划声明或拟议步骤，未验证外部事实'}
- {'turn': 21, 'type': 'update_receipt', 'fields': {'acceptance': 'declared'}}

## 人类认知检查

- 我们要回答什么，不准备声称什么？
- 为什么选择当前设计，合理替代方案是什么？
- 什么结果会改变判断，哪些未知仍未解决？
- 谁负责执行、核实证据及批准最终结论？
- 何时停止、修订或交还人工判断？
