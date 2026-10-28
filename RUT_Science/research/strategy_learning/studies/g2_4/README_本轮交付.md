# G2.4：DOE协议、统一验收器与待专家校准任务库

日期：2026-10-27。沿用 [统一研究入口](../../README.md)，没有新增ZIP或独立项目根。应用 `science-bot.cmd` 保持，G2.4暂作为研究模块，不改变线上通用访谈或策略。

已交付可运行的结构化协议、设计编译、固定验收与反馈、统一评分、封存任务、专家待审导入和验收证据。**没有训练BC/PPO或LLM，没有接入真实工具或真实CViT，没有完成真人专家校准。**

## 1. 支持范围

| 设计 | 当前边界 | 分析与目标 |
|---|---|---|
| `crd_two_arm` | 两处理、平衡、不同实验单位；每处理的独立重复数可配置 | 同方差正态误差下的高水平减低水平均值差 |
| `rcbd_two_arm` | 两处理、至少两个完整区组；每区组每处理一个单位 | 加性区组模型；残差自由度为区组数减1 |
| `factorial_2x2` | 两因素各两水平，全因子；可无区组或有至少两个完整区组 | 必须包含两个主效应和交互；主效应或差中之差可预先作为单一主要对比 |

v1限制平衡固定效应线性模型、单一预设双侧主要对比及指定方差下的名义功效。不支持非正态/异方差推断、任意ANOVA、多个确认性主要终点、部分因子、裂区、复杂重复测量或通用因果识别。遇到超出范围的设计不回退套用CRD。

主要对比与实际重要差异分别保存。显著性/置信区间用于对零效应的判断，实际重要性另行解释；没有把“功效80%”当作“实验结论80%正确”。

## 2. 实验协议与可检查步骤

`schemas/experiment_contract.schema.json` 定义闭合协议；`schemas/request.schema.json` 定义宿主拥有的原始需求与证据。禁止额外的执行授权字段、任意公式或代码。

协议包含问题、因素水平、响应及单位、实验单位与测量次数、区组、独立重复、随机化种子、假设、分析、主要对比、alpha、目标差异、sigma、目标功效、缺失处理和资源预算。

关键声明通过来源ID与原始需求逐项绑定。当前粒度是问题、因素、响应、单位、区组、假设、分析、资源等协议节；它不替代未来逐字段提问系统。伪造更小sigma、修改主要对比或提高alpha不能凭新的文本声明通过验收。

`doe/compiler.py` 生成：

1. 独立单位分配及可重算的随机执行顺序；区组内随机化。
2. 主效应、交互和区组设计矩阵、秩、目标对比可估计性、残差及纯误差自由度。
3. 基于非中心t分布的条件功效与sigma放大1.25/1.5倍的敏感性。
4. `ground_facts → check_design → preregister → external_review → collect_outcomes → analyze → report` 的依赖步骤和各步验收条件。

步骤是可审阅计划。收集、分析和报告均未执行，所有 `executed=false`，`observed_outcomes=null`。缺失数据规则是停止并审阅，不自动删样本。

技术重复不会增加实验单位数；没有区组内重复时，纯误差可能为0，即使加性模型有残差自由度，也不能声称已检验处理×区组交互。独立性、正态性、同方差、区组加性、真实测量和随机化执行保持 `unverified`。验收通过只返回 `ready_for_review=true`，始终 `execution_authorized=false`、`scientific_success=null`。

功效计算为：

\[
SE=\sigma\sqrt{c^T(X^TX)^{-1}c},\quad \nu=N-\operatorname{rank}(X),\quad \lambda=\delta/SE.
\]

用双侧t临界值及非中心t分布计算在指定delta下的拒绝概率。主效应对应±1编码的`2 beta`，交互差中之差对应`4 beta`。sigma是有来源的规划值，pilot估计不确定性没有被积分进入功效，敏感性结果须一并审阅。

方法依据：[NIST CRD](https://www.itl.nist.gov/div898/handbook/pri/section3/pri331.htm)、[区组](https://www.itl.nist.gov/div898/handbook/pri/section3/pri332.htm)、[全因子](https://www.itl.nist.gov/div898/handbook/pri/section3/pri333.htm)、[SciPy非中心t](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.nct.html)。参考材料均已复制并记录哈希，未导入复制的应用代码。

## 3. 统一反馈、选模与停止规则

`doe/validation.py:validate` 是固定验收器；`doe/scoring.py:score` 在train/development/heldout阶段使用相同谓词和奖励，不再另设宽松开发成功率。接口不读取任务隐藏期望标签。

- 有效提交或有当前公开证据支持的必要停止：终局+10。
- 错误提交、无依据停止、未知提交类型：终局−10。
- 决策成本为每步0.01，1至40步，上限0.4，不会压过完成奖励。
- 不奖励显著结果、虚构高精度、重复填槽或反复修订。
- 开发选模按失败数、无依据停止数、成本依次排序，不只看平均步数。

允许停止的范围：用户已经明确无法提供的关键证据，或原始需求明确要求不支持的设计。尚未回答的问题不能当作无法回答；本轮设计任务中，拒绝真实执行不妨碍提供设计；单一候选超预算也不能据此证明所有设计都不可行。

当前只是未来RL可复用的反馈/选模基础设施，没有actor、critic或PPO更新。完整对话收集、DAgger及新强化训练仍属下一阶段。

## 4. 任务与专家审阅

任务库：**84训练、42开发、42封存**。14类案例覆盖三种设计，包括正确设计、技术重复、重复单位、非随机顺序、缺失处理组合、错误模型、低功效、超预算、伪造方差、未知/未回答事实、缺失来源、切换主要对比和不支持范围。

源组身份无交叠，但三分区共享生成模板；这是合成回归/校准案例库，不能声称独立领域泛化。封存记录本轮未通过任务加载接口打开用于评分、训练或审阅；仅进行文件哈希核对。文件存放在同一机器，Python审计钩子不是对抗恶意程序的OS隔离。

`review/pending.jsonl` 共**42条待审**，不包含脚本期望答案，审阅者、结论、理由及时间保持空白。真人专家标签为**0**。

审阅时复制待审文件到本study的 `review/reviewed_by_user.jsonl`，填入 `approved`、`acceptable/reject/needs_information`、问题代码、理由、审阅者和带时区时间。不要覆盖冻结的pending队列。

导入核对训练分区、原始文件哈希、观察、源行和身份，拒绝重复、篡改、待审、缺失说明或越权字段。导入者身份只是外部声明，不自动证明专业资质；导入不触发训练或修改规则。单元测试中的批准夹具标明synthetic，留在 `current_test_outputs/`，不计专家标签。

## 5. 命令

在 `LangGraph_RL_Agent` 项目根目录运行，使用现有解释器，不安装新依赖：

```powershell
& '.\RUT_Science\.venv\Scripts\python.exe' -B 'RUT_Science/scripts/science_bot_research.py' test --study g2_4
& '.\RUT_Science\.venv\Scripts\python.exe' -B 'RUT_Science/scripts/science_bot_research.py' demo --study g2_4
& '.\RUT_Science\.venv\Scripts\python.exe' -B 'RUT_Science/scripts/science_bot_research.py' verify --study g2_4
```

开发诊断与显式验证示例：

```powershell
& '.\RUT_Science\.venv\Scripts\python.exe' -B 'RUT_Science/research/strategy_learning/studies/g2_4/run.py' evaluate
& '.\RUT_Science\.venv\Scripts\python.exe' -B 'RUT_Science/research/strategy_learning/studies/g2_4/run.py' validate --request examples/factorial_request.json --input examples/factorial_contract.json
```

导入手工审阅（完成审阅后使用）：

```powershell
& '.\RUT_Science\.venv\Scripts\python.exe' -B 'RUT_Science/research/strategy_learning/studies/g2_4/run.py' review-import --input review/reviewed_by_user.jsonl --output review/reviewed_labels_v1.json
```

输入输出路径限定在本study。`build`首次生成并冻结协议，已有冻结时仅检查，不覆盖。`review-export`默认也拒绝覆盖现有pending文件。

## 6. 本轮证据与验收

- **49项测试通过**：设计反例、独立公式对照、合成高斯模拟、作用尺度、来源保护、评分一致性、停止证据、审阅和隔离。
- **42/42开发案例符合脚本预期**，包含6个正例、36个反例；不是专家正确率或Agent成功率。
- 无差别停止诊断：42例中仅6例有当前依据支持停止，其余36例为无依据停止。
- 冻结11个协议源码文件、两份schema、任务封存与待审队列；没有选中策略或正式训练transition。
- 演示修复遗漏交互模型后，条件名义功效约0.92185；它不是实际实验精度。
- 原应用核心与G2.2/G2.3制品受保护，运行入口和线上策略不变。

证据：[冻结协议](evidence/protocol_freeze.json)、[开发诊断](evidence/development_diagnostics.json)、[反馈演示](evidence/demo.json)、[当前验收](evidence/current_verification.json)、[复制清单](evidence/copied_files.json)。总交付入口见 [G2.4交付](../../../../delivery/g2_4_update/README_本轮交付.md)。

下一步先开展独立专家审阅、修订有争议的验收标准并另建版本；然后进行BC与状态聚合。只有这些基线可靠后，再启动新的受约束PPO比较。
