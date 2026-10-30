# expert_batch_001 依据与争议

**批次编号：** expert_batch_001
**日期：** 2026-10-29
**关联文件：** `expert_batch_001_decisions.jsonl`、`expert_batch_001_批次说明.md`

---

## 1. 记录与审阅关联表

| idx | task_id | turn | family | 脚本提议 | review_id | acceptable | rejected |
|---:|---|---:|---|---|---|---|---|
| 0 | darcy_train_00 | 0 | rcbd_two_arm | review | 214c8d6e747440465c0b969afc03b57776f1b015ee6391c2e7056b80adb9f0ef | review, read_plan | stop, model_full_factorial, model_blocked_full_factorial |
| 5 | darcy_train_01 | 0 | rcbd_two_arm | repair_response | 6b03e53d161a22e889ae7b271cdfd2cf552765c047f1c90d441cfb31250d29f4 | repair_response, review, read_plan | stop, model_full_factorial, model_blocked_full_factorial |
| 6 | darcy_train_01 | 3 | rcbd_two_arm | freeze | 7d950688c9fea5110e19d29b3953cd77a4eabbe2bea13a9741255e826f9b6c41 | freeze, read_plan | stop, model_full_factorial, model_blocked_full_factorial |
| 7 | darcy_train_01 | 6 | rcbd_two_arm | reconcile | 8780e9c8ce05ce5aa8af30c97aa5458638ebb991ae4037180378a6d246054684 | reconcile, read_plan | stop, model_full_factorial, model_blocked_full_factorial |
| 8 | darcy_train_01 | 9 | rcbd_two_arm | assess | 5428778a6b4ecb456153380b161855bba7c312e1ab6b5d20168fd61e5130a47d | assess, read_plan | stop, model_full_factorial, model_blocked_full_factorial |
| 9 | darcy_train_02 | 0 | rcbd_two_arm | repair_budget | 8397eeda1865668a16fbfe37fa06936499096143e5df487f4b983279f502bb30 | repair_budget, review, read_plan | stop, model_full_factorial, model_blocked_full_factorial |
| 22 | cvit_train_05 | 0 | factorial_2x2 | ask_variance | 2a28db14d9547babdcb44a8e1096bc882f853e3836e1519231c3b7fedc7c4abc | ask_variance, review, read_plan | stop |
| 30 | cvit_train_07 | 9 | factorial_2x2 | report | 9abfcce1b97bb6442a2063e756974edfce146b2d92467b5c71381a332a411abe | report, read_plan | stop |

---

## 2. 来源及版本

| 项目 | 内容 |
|---|---|
| 协议版本 | `tool_harness_rl_v2` |
| 源记录 | `v2/expert/pending_decisions.jsonl`（SHA256: `0658eaf3…b111`） |
| 场景 | Darcy（`rcbd_two_arm`）与 CViT（`factorial_2x2`），mock 工具，`real_execution_allowed=false` |
| 数据来源声明 | Darcy 为公开数值数据派生的受控任务；CViT 为模拟配置/作业协议。**本批不含任何真实实验执行** |
| 封存边界 | 未读取任何 `evaluator_only` 或测试集内容；审阅仅基于各记录公开的 observation |

---

## 3. 实验单位与分组依据

- **rcbd_two_arm（Darcy）**：随机完全区组、两处理（predictor: mean_field vs ridge_field）；实验单位为独立数据实现块内的一次预测应用；`replicates=1`，区组化用于控制数据实现间差异。
- **factorial_2x2（CViT）**：两因子各两水平（architecture × learning_rate），`primary_term=architecture`；区组设计映射为模拟配置，不涉及真实 GPU 作业。

因此：
- `rcbd_two_arm` 下 `full_factorial` / `blocked_full_factorial` 模型需要至少两个因子，与单因子设计结构不符 → 判 rejected（8 条中 6 条适用）。
- `factorial_2x2` 下全因子模型与设计一致（当前合同已为 `blocked_full_factorial`），不列入；`model_two_arm` 忽略 `learning_rate` 因子，主效应估计仍无偏但属次优 → 不列入。

---

## 4. 效应与方差依据

| 记录 | minimum_effect | practical_margin | sigma / variance_source | 处理 |
|---|---:|---:|---|---|
| idx 0/5/6/7/8/9/30 | 0.02 | 0.01 | sigma=0.02；`synthetic pilot declaration; not real evidence` | 按声明值用于功效判断；reason 中未据其做额外推断 |
| idx 22 | 0.02 | 0.01 | **sigma=null；variance_source=null；variance_available=false** | 判 `ask_variance` 可接受（缺少方差依据，需向用户获取） |

**声明**：sigma=0.02 为合成 pilot 声明，不是真实证据；本批审阅未将其当作已验证方差，也未据此声称任何真实统计功效。

---

## 5. 分析与停止假设

1. **停止（stop）判定规则**：`host.stop_with_evidence` 必须在当前观察中存在可引用的停止依据。本批 8 条记录的 stop 参数均为 `evidence_ids=[]`；且：
   - idx 0、5、9：开局无观测；
   - idx 6、7：流程推进中，前置刚完成、后续未开始；
   - idx 8：分析完成但主张评估与报告未做；
   - idx 30：环境 `next_step` 明确要求报告，报告未完成。
   → 全部判 rejected（无据停止 / 半途终止）。
2. **流程顺序假设**：复核（review）→ 修补（patch）/解决（resolve）→ 对齐（align）→ 冻结（freeze）→ 编译（workflow）→ 校验（verify）→ 对账（reconcile）→ 执行（run）→ 分析（analyze）→ 评估（assess）→ 下一步（next）→ 报告（report）。
3. **重复动作**：对当前版本已完成且状态有效的动作（如 idx 6/7/8/30 的 review/align），不列入 acceptable（重复执行无新证据）；未列入不等同于负例。
4. **冻结后 patch**：idx 7/8/30 的计划已冻结，patch 携带的 `expected_contract_hash` 与冻结点不一致，宿主将拒绝；故未列入（idx 6 的计划尚未冻结，但模型类 patch 因结构错误列入 rejected）。

---

## 6. 争议与保留项（请负责人裁决）

1. **反问顺序之争**：idx 22 同时列 `ask_variance` 与 `review` 为可接受。理由：计划已公开显示缺少方差（variance_available=false），先问与先复核两条路径均成立。若项目口径要求"必须先复核再提问"，请统一修订。
2. **修补前是否必须先复核**：idx 5（响应变量 training_loss→relative_l2）、idx 9（预算 2→256）的缺陷在当前观察中公开可见，故直接修补与先复核均列为可接受。若口径要求"patch 一律以 review 发现为前置"，请统一修订并重审本批两条。
3. **次优但不错误**：`model_two_arm` 在 rcbd_two_arm（忽略区组）与 factorial_2x2（忽略第二因子）下均判为"次优、不列入"，而非 rejected。若负责人认为应作负例，请明确。
4. **reviewer 身份**：本批 reviewer 为外部声明 `RAOGUOCHONG`，按标注文档 §11 需由项目负责人核验。
5. **批次规模**：本批 8 条（建议为约 10 条）。是否先以 8 条校准、或补足至 10 条后一并复核，请负责人决定。

---

## 7. 最终处理状态

| 状态 | 数量 | 说明 |
|---|---:|---|
| approved | 8 | 待负责人复核后导入 |
| pending | 0 | 无 |
| rejected | 0 | 无 |

**声明**：本批未新增任务、未修改任何源记录、未补造工具反馈、未填写策略概率或 critic 值；所有判断仅基于各记录公开的 observation 与 history。
