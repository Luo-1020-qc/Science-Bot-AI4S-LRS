# expert_batch_002 依据与争议

**批次编号：** expert_batch_002
**日期：** 2026-10-29
**关联文件：** `expert_batch_002_decisions.jsonl`、`expert_batch_002_批次说明.md`

---

## 1. 记录与审阅关联表

| idx | task_id | turn | family | 脚本提议 | review_id | acceptable | rejected |
|---:|---|---:|---|---|---|---|---|
| 1 | darcy_train_00 | 3 | rcbd_two_arm | resolve | e3b2df2783e14e13f7fbfed651befa253c8bf801dc4d64360ecd80c0e99532dd | resolve, read_plan | stop, model_full_factorial, model_blocked_full_factorial |
| 2 | darcy_train_00 | 6 | rcbd_two_arm | workflow | e304c6d1248501f98d6a9f78ddeed50147408962339f220e506264e07e2b06b5 | workflow, read_plan | stop, model_full_factorial, model_blocked_full_factorial |
| 3 | darcy_train_00 | 9 | rcbd_two_arm | run_mock | 1d4c51845afbd975673b2d4f3c2c9b940c125b63e31035793b3af242474e5e65 | run_mock, read_plan | stop, model_full_factorial, model_blocked_full_factorial |
| 4 | darcy_train_00 | 12 | rcbd_two_arm | next | abfe1e73075fb66f402ec69c3d25626ba5426b9dc6e13a6cffaeb3d120d355d3 | next, read_plan | stop, model_full_factorial, model_blocked_full_factorial |
| 10 | darcy_train_02 | 3 | rcbd_two_arm | freeze | b323d8b6bb0a5ccdb0984a08a1e32fa5634598550f6f0352b87c9bd0776e49bf | freeze, read_plan | stop, model_full_factorial, model_blocked_full_factorial |
| 11 | darcy_train_02 | 6 | rcbd_two_arm | reconcile | eced2f8982c631926f951bdcc4b4fb353bfc8b70fb905a018c9355614f9d4e2c | reconcile, read_plan | stop, model_full_factorial, model_blocked_full_factorial |
| 12 | darcy_train_02 | 9 | rcbd_two_arm | assess | c5f636d1ead6ff086a9f43ca0e2aab185a0fdc11550f5d3ca1ab51720b46de26 | assess, read_plan | stop, model_full_factorial, model_blocked_full_factorial |
| 13 | darcy_train_03 | 0 | rcbd_two_arm | review | f4f3fbda7afc21fb5260b0868c6d847a5ec5aafff6f1adfc240195ab27288c88 | review, read_plan | stop, model_full_factorial, model_blocked_full_factorial |
| 14 | darcy_train_03 | 3 | rcbd_two_arm | workflow | 0446ccc45e01c91b4257f544ebc0b178dca6522614df013c5e85594ab657064e | workflow, read_plan | stop, model_full_factorial, model_blocked_full_factorial |
| 15 | darcy_train_03 | 6 | rcbd_two_arm | run_mock | a9c20efb338003d5731689ac3b4f31e828a9ddc98d65e410cef96b3d22f89920 | run_mock, read_plan | stop, model_full_factorial, model_blocked_full_factorial |
| 16 | darcy_train_03 | 9 | rcbd_two_arm | next | deef5a0985ef4bcfc197c86554dd79307a754930437f8d98f8a5a93c8b59197e | next, read_plan | stop, model_full_factorial, model_blocked_full_factorial |
| 17 | cvit_train_04 | 0 | factorial_2x2 | review | d1fe3db6c91f1c08558a122f452875d69504ff57414e1a10a105838965f2cec0 | review, model_blocked_full_factorial, read_plan | stop |
| 18 | cvit_train_04 | 3 | factorial_2x2 | resolve | 29b41698ded35335aa3bc540f3315a3f6344d8e103f11818a9f890a6edb63cca | resolve, read_plan | stop |
| 19 | cvit_train_04 | 6 | factorial_2x2 | workflow | de669824724dae8bdd4611a90301eb44da8585b34b34082ec0d7125afe9ada0d | workflow, read_plan | stop |
| 20 | cvit_train_04 | 9 | factorial_2x2 | run_mock | 794d81d564aed408b762041be127c953266026600df81746039a48dbba407513 | run_mock, read_plan | stop |
| 21 | cvit_train_04 | 12 | factorial_2x2 | next | e57c0c0184ebb61d11808057406167dba681829c90f7d5f2fbd9aebce80a636a | next, read_plan | stop |
| 23 | cvit_train_06 | 0 | factorial_2x2 | review | 12d41dce6e8f4f2d14f7adb8c522bbd6f38018e61c65d7ab73dbc9ccb7b13e09 | repair_budget, review, read_plan | stop |
| 24 | cvit_train_06 | 3 | factorial_2x2 | workflow | 83a7c7e32ed6d9b352609e9173cba089fe905131af6c8a78ccd338dbd87a541b | workflow, read_plan | stop |
| 25 | cvit_train_06 | 6 | factorial_2x2 | run_mock | 71b96967f9c0119466a341bd04a850253506e9e4c23b67f0f91c9818843297ac | run_mock, read_plan | stop |
| 26 | cvit_train_06 | 9 | factorial_2x2 | next | 177d37dac1cdab86c4e6c37450099cfa2cf29c1d3c49311139b77ca0273398b0 | next, read_plan | stop |
| 27 | cvit_train_07 | 0 | factorial_2x2 | review | 5077fdd790def79ca912a2547cb02979674eb1888e20271afa6c5465c2729ca0 | review, read_plan | stop |
| 28 | cvit_train_07 | 3 | factorial_2x2 | workflow | 23c7525bb7dd80284b3ad764aa7718334350d5e7d8dec7602e36a21a2f2d76fc | workflow, read_plan | stop |
| 29 | cvit_train_07 | 6 | factorial_2x2 | analyze | 56770d36561e12d1ce2b5d7b20273f460f9b9abc67d78c9f5bd45f22964062ef | analyze, read_plan | stop |

---

## 2. 本批新发现（与 batch_001 的差异）

1. **idx 17：模型结构性错误**
   factorial_2x2（两因子 + 6 区组）但 `analysis.model=two_arm`，无法估计两因子结构/交互。
   判 `model_blocked_full_factorial` 可接受（修补）与 `review` 并列；后续历史显示脚本确实修补为 blocked_full_factorial 并重新复核通过（idx 18）。
2. **idx 23–26：预算偏差**
   合同 `resources.budget=257`，用户声明 `resource_budget=256`（超出 1 单位）。
   - idx 23（未冻结）：判 `repair_budget` 可接受；
   - idx 24–26（已冻结）：未列入 patch（哈希不匹配无法生效），但在 reason 中记录"应在报告中说明"。
   **请负责人裁决：该偏差是否应阻断执行，还是仅需在报告披露。**
3. **idx 21：阴性/不确定结果**
   assess 返回 `status=inconclusive`、`practical_benefit_supported=false`。
   判 `next` 可接受（应继续到报告），stop 拒绝——阴性结果不等于可以无报告终止。
4. **idx 29：复用既有作业**
   reconcile 返回 `status=mock_completed`、`reused=true`，分析前无需重复执行；`poll` 未列入（作业已完成）。

---

## 3. 停止判定一致性

本批 23 条全部将 `stop` 列为 rejected，理由分三类：
- 开局（idx 13、17、23、27）：无任何观测证据；
- 流程中（idx 1/2/10/11/14/18/19/24/28 等）：前置刚完成、后续未开始；
- 收尾前（idx 4/12/16/21/26/29 等）：评估或报告未完成。

`host.stop_with_evidence` 的 `evidence_ids` 在所有记录中均为空。

---

## 4. 模型判定一致性

| family | 判定 |
|---|---|
| rcbd_two_arm（单因子） | `full_factorial` / `blocked_full_factorial` 结构不符 → rejected；`model_two_arm` 忽略区组但无偏 → 次优不列 |
| factorial_2x2（两因子） | `blocked_full_factorial` 与设计一致；`two_arm` 无法估计两因子结构 → 仅在 idx 17 作为"当前错误模型"指出；其余不列 |

---

## 5. 争议与保留（请负责人裁决）

1. **预算偏差 idx 23–26**：257 vs 256 是否阻断？（本批判"修复/记录"，未阻断）
2. **review 与 repair 并列**（沿用 batch_001 口径）：idx 17/23 同时列 review 与直接修补，是否接受？
3. **次优动作不列负例**：`model_two_arm` 在 rcbd 下判次优不列，是否接受？
4. **reviewer 身份**：外部声明 `RAOGUOCHONG`，需核验。

---

## 6. 最终处理状态

| 状态 | 数量 |
|---|---:|
| approved | 23 |
| pending | 0 |
| rejected | 0 |

**统计：** acceptable 48 条（平均 2.1），rejected 45 条（平均 2.0），多解记录 23/23。

**声明：** 仅修改 review 字段；未新增任务；未读取封存数据；未伪造工具反馈。
