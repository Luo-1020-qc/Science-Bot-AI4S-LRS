# expert_batches 合并复核请求

**日期：** 2026-10-29
**发起人：** RAOGUOCHONG（审阅执行）
**收件人：** 项目负责人 / 数据负责人
**状态：** 31 条待审记录已全部完成审阅，等待口径复核

---

## 1. 总览

| 批次 | 记录数 | 范围 | 文件 |
|---|---:|---|---|
| batch_001 | 8 | darcy_00/01/02、cvit_05/07 | `expert_batch_001_*` |
| batch_002 | 23 | batch_001 之后剩余全部 | `expert_batch_002_*` |
| **合计** | **31** | 8 个 episode、turn 0–12 | — |

**标注统计：** acceptable 67 条（平均 2.2/记录）、rejected 65 条（平均 2.1/记录）、**31/31 全部多解**（每条 ≥2 个合理动作）。

---

## 2. 请复核的 6 个口径问题

### 沿用 batch_001 的 5 项
1. **ask_variance 与 review 并列**是否可接受（idx 22）？
2. **修补前是否必须先复核**（idx 5/9 的缺陷公开可见）？
3. **次优动作不列负例**（model_two_arm 在 rcbd 下忽略区组但无偏）是否接受？
4. **reviewer 身份**（外部声明 RAOGUOCHONG）需核验。
5. **批次规模**：8+23 的拆分是否可接受？

### batch_002 新增 1 项
6. **预算偏差 idx 23–26**：合同 budget=257、用户声明 256（超出 1 单位）。
   本批判"修复（未冻结时）/ 记录（已冻结时）"，未阻断执行。请裁决是否应阻断。

---

## 3. 本批关键判断（供抽查）

| 记录 | 判断 | 依据 |
|---|---|---|
| idx 17 | 接受 `model_blocked_full_factorial`（修补） | factorial_2x2 两因子 + 区组，而合同 model=two_arm，结构性不符 |
| idx 21 | 接受 `next`，拒绝 `stop` | assess=inconclusive，阴性结果也须走到报告 |
| idx 23 | 接受 `repair_budget` | budget 257 vs 声明 256，公开可见 |
| idx 29 | 接受 `analyze`，不列 `poll` | reconcile 复用既有作业且已 mock_completed |
| 全部 31 条 | `stop` 全部 rejected | evidence_ids 为空；开局无证据或流程未完成 |

---

## 4. 导入命令（复核通过后）

```powershell
.\RUT_Science\.venv\Scripts\python.exe -B 'Training_Data_Darcy_CViT/v2/expert_import.py' decisions expert/inbox/expert_batch_001_decisions.jsonl expert/imports/expert_batch_001_decisions.json
.\RUT_Science\.venv\Scripts\python.exe -B 'Training_Data_Darcy_CViT/v2/expert_import.py' decisions expert/inbox/expert_batch_002_decisions.jsonl expert/imports/expert_batch_002_decisions.json
```

## 5. 完整性

- 仅修改 `review` 字段，其余字段与源记录逐字段一致（脚本自动校验）；
- 未新增任务、未读取封存数据、未伪造工具反馈；
- 源 `pending_decisions.jsonl` 未修改；
- 两批 SHA256 记录在各自《批次说明》中。
