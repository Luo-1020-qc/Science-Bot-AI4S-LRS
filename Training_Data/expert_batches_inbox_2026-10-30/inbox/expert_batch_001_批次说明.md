# expert_batch_001 批次说明

**批次编号：** expert_batch_001（校准批次）
**日期：** 2026-10-29
**作者（审阅执行）：** RAOGUOCHONG（外部声明，待项目负责人核验）
**复核人：** 待项目负责人指定（本批次尚未经负责人复核）
**数据版本：** `tool_harness_rl_v2`
**提交内容：** 仅决策审阅（decisions），未包含新任务（tasks）

---

## 1. 数量与范围

| 项目 | 内容 |
|---|---|
| 决策记录数 | 8 条（源自 `pending_decisions.jsonl` 的 idx 0/5/6/7/8/9/22/30） |
| 覆盖任务 | darcy_train_00、darcy_train_01、darcy_train_02、cvit_train_05、cvit_train_07（共 5 个） |
| 覆盖阶段 | turn 0（开局复核/修补）、turn 3（freeze）、turn 6（reconcile）、turn 9（assess / report） |
| 覆盖 family | rcbd_two_arm（6 条）、factorial_2x2（2 条） |
| 状态 | 全部 `approved`，无 pending / rejected |

> 说明：标注文档 §10 建议首批约 10 条。本批为 8 条校准批，剩余记录待负责人复核口径后再补足。

## 2. 文件清单

| 文件 | 内容 |
|---|---|
| `expert_batch_001_decisions.jsonl` | 8 条完整决策记录的副本，**仅修改 `review` 字段**，其余字段（含 review_id、observation、observation_hash、candidates、哈希）保持原样 |
| `expert_batch_001_依据与争议.md` | 来源、实验单位与分组、效应/方差依据、停止假设、争议与保留项 |
| `expert_batch_001_批次说明.md` | 本文件 |

## 3. 来源与完整性

| 项目 | 值 |
|---|---|
| 源文件 | `Training_Data_Darcy_CViT/v2/expert/pending_decisions.jsonl` |
| 源文件 SHA256 | `0658eaf34407925616e08458c43ce2b6e4b71df44e2fd0e0e3ccd4d11a74b111` |
| 输出文件 SHA256 | `10e89dc8181df6b136731246ac20b5264e2ed363d9fbb41d0d68cd67d651f487` |
| 生成方式 | 脚本读取源文件 → 深拷贝 8 条记录 → 仅替换 `review` 对象 → 逐行写 UTF-8 JSONL |
| 自动校验 | ① 所有动作 ID 均存在于该记录的 candidates；② acceptable 与 rejected 无交集；③ 除 `review` 外其余字段与源记录逐字段一致（sort_keys JSON 比较） |

## 4. 修订历史

| 版本 | 日期 | 修改 |
|---|---|---|
| v1 | 2026-10-29 | 初版：8 条核准决策，待负责人复核 |

## 5. 后续流程（按标注文档 §11）

1. 负责人复核本批 8 条的口径（重点见《依据与争议》§6 的待裁决项）
2. 复核通过后由工程执行：
   ```powershell
   .\RUT_Science\.venv\Scripts\python.exe -B 'Training_Data_Darcy_CViT/v2/expert_import.py' decisions expert/inbox/expert_batch_001_decisions.jsonl expert/imports/expert_batch_001_decisions.json
   ```
3. 导入失败时按报错逐条修正，**不覆盖原始文件，另起批次编号重新提交**
