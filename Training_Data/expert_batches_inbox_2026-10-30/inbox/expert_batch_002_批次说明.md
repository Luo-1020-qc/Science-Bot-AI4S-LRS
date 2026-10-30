# expert_batch_002 批次说明

**批次编号：** expert_batch_002
**日期：** 2026-10-29
**作者（审阅执行）：** RAOGUOCHONG（外部声明，待核验）
**复核人：** 待项目负责人指定
**数据版本：** `tool_harness_rl_v2`
**提交内容：** 仅决策审阅（decisions），未包含新任务

---

## 1. 数量与范围

| 项目 | 内容 |
|---|---|
| 决策记录数 | 23 条（batch_001 之后的全部剩余记录） |
| 覆盖任务 | darcy_train_00/02/03、cvit_train_04/06/07（共 6 个） |
| 覆盖阶段 | turn 0/3/6/9/12：review、resolve、workflow、run_mock、next、assess、analyze、freeze、reconcile |
| 状态 | 全部 `approved` |

> 与 batch_001 合并后，31 条待审记录全部完成审阅。

## 2. 文件与完整性

| 项目 | 值 |
|---|---|
| 源文件 | `pending_decisions.jsonl` |
| 源 SHA256 | `0658eaf34407925616e08458c43ce2b6e4b71df44e2fd0e0e3ccd4d11a74b111` |
| batch_001 SHA256 | `10e89dc8181df6b136731246ac20b5264e2ed363d9fbb41d0d68cd67d651f487` |
| 本批 SHA256 | `d6dc6084266f7116aa937ac17db5602c8e80cb8dd2d64f5796e05a16155bf55a` |
| 自动校验 | 动作 ID 均存在；acceptable/rejected 无交集；除 review 外字段与源记录逐字段一致 |

## 3. 修订历史

| 版本 | 日期 | 内容 |
|---|---|---|
| v1 | 2026-10-29 | 初版：剩余 23 条；含 idx 17 模型错误与 idx 23–26 预算偏差的说明 |

## 4. 导入命令（复核通过后）

```powershell
.\RUT_Science\.venv\Scripts\python.exe -B 'Training_Data_Darcy_CViT/v2/expert_import.py' decisions expert/inbox/expert_batch_002_decisions.jsonl expert/imports/expert_batch_002_decisions.json
```

## 5. 注意

- 本批与 batch_001 共用同一标注口径；若负责人调整口径（见《依据与争议》§5），两批需一并修订；
- 原始 `pending_decisions.jsonl` 未修改；
- 不覆盖既有文件，如需修改请另起批次号。
