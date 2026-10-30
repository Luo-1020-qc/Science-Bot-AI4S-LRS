# 给队友：学科壳（scenario shells）总览

**日期：** 2026-10-29
**维护者：** RAOGUOCHONG
**性质：** 交付包说明（原型阶段，非最终版）
**一句话：** 65 个"学科场景需求规格"，把用户的科研问题变成可访谈、可检查、可执行（或明确不可执行）的条目。

---

## 1. 这是什么

一个"学科壳"（shell）描述**一个具体科研场景**需要什么：

| 字段 | 作用 |
|---|---|
| `scenario_name` / `domain` / `skeleton` | 场景名、学科、所属任务骨架 |
| `executable` | 当前系统能否真正执行（不是"以后能不能"） |
| `vocabulary` | 领域词汇表（处理名/指标名/单位/对比） |
| `survey_questions` | 访谈时要问用户的问题（7–9 条） |
| `rubric` | 计划建议书的逐条检查清单（8 条左右） |
| `proposal_template` | 建议书章节结构 |
| `source` / `notes` | 来源与备注 |

**骨架（skeleton）** 是底层统计方法：S1 两组独立比较、S2 配对比较、S3 因子设计、S4 数值预测、S5 多组比较（待开发）等。

---

## 2. 数字速览

| 指标 | 数值 |
|---|---:|
| 场景总数 | **65** |
| 今天可执行 | **53（81.5%）** |
| 不可执行（诚实标注） | 12 |
| 可执行骨架 | S1（19）、S2（11）、S3（12/13）、S4（11） |
| 待开发骨架场景 | S5（10）、S6（1）、响应面（1） |

**为什么不是 100%？**
- S5（多组比较）内核未实现 → 10 个场景只有需求规格
- S6 良品率是比例数据 → 归入未实现的 S6
- 化工响应面超出当前 2×2 内核

这是**有意为之**：宁可标"不可执行"，也不假装能跑。

---

## 3. 阅读路径

### 5 分钟
1. 本文件
2. `matrix.md`（覆盖矩阵）
3. `矩阵_场景对照表.md`（哪个骨架有哪些场景）

### 15 分钟（研究/领域队友）
挑 2–3 个你熟悉的领域场景，看 `shells/*.yaml` 里的 `survey_questions` 与 `rubric`：
- 问题是否问到了该问的？（混杂、重复、测量、异常、阈值）
- 检查清单是否符合领域常识？
- 缺什么关键问题？

### 30 分钟（开发队友）
看 `deep-dive/`：
- `Materials_Chemistry_execution_pack.md`：16 个材料/化学场景 → 三条执行路径的完整映射 + 实测结果 + 开发待办（P0：分组划分）
- `S3_synthesis_execution_mapping.md`：DOE 契约字段、功率扫描、限制
- `examples/run_g2_demos.py`：三条路径的可复现演示（合成数据）

---

## 4. 目录结构

```
coverage-tool/
├── README_给队友.md              ← 本文件
├── skeletons.yaml                ← 10 个骨架注册表
├── shells/                       ← 65 个 YAML（唯一源，人审版）
├── shells_json/                  ← 65 个 JSON（派生，程序消费）
│   └── index.json                ← 按骨架分组的总索引（含 sha256）
├── matrix.md                     ← 自动生成的覆盖矩阵
├── 矩阵_场景对照表.md             ← 骨架 → 场景导航表（自动生成）
├── coverage_matrix.py            ← 覆盖矩阵生成器
├── export_shells_json.py         ← YAML → JSON 导出器
└── deep-dive/
    ├── Materials_Chemistry_execution_pack.md
    ├── S3_synthesis_execution_mapping.md
    └── examples/
        ├── run_g2_demos.py
        ├── tensile.csv
        ├── hardness_paired.csv
        └── property_prediction.csv
```

**规则：`shells/*.yaml` 是唯一源。** 改内容改 YAML；JSON 是派生文件，不要手改，重新导出即可。

---

## 5. 如何运行

需要 Python 3.10+ 与 `pyyaml`。

```bash
cd coverage-tool

# 重新生成覆盖矩阵
python coverage_matrix.py

# 重新导出 JSON 与索引、导航表
python export_shells_json.py
```

跑演示（需要项目 venv，因为要 import rut_science）：

```bash
cd deep-dive/examples
<项目>/.venv/Scripts/python.exe run_g2_demos.py
```

---

## 6. 如何新增一个场景

1. 在 `shells/` 复制一个**同骨架**的壳文件（模板）
2. 修改 `scenario_name` / `domain` / `vocabulary` / `survey_questions` / `rubric` / `proposal_template`
3. 跑 `export_shells_json.py` 与 `coverage_matrix.py`，确认无报错、矩阵更新
4. 提交给负责人复核（rubric 质量是重点）
5. 更新 `source` 与 `notes`（来源与注意事项）

**字段规范**：`scenario_name` 全局唯一；`skeleton` 必须在 `skeletons.yaml` 中存在；`executable` 缺失会按 false 计并标注。

---

## 7. 诚实边界（请不要"顺手修掉"）

| 标注 | 含义 |
|---|---|
| `executable: false` | 当前内核不支持，仅生成建议书；**不要改成 true**，除非内核已实现并有测试 |
| `skeleton: S5/S6` | 待开发骨架；场景已备好，内核一实现即可解锁 |
| `notes` 中的"不可执行" | 是对限制的显式记录，属于交付内容 |

---

## 8. 与主项目的关系

- 这些壳目前是**独立沙盒**（`Hackthon/coverage-tool/`），不修改 `Science-Bot-AI4S-LRS` 的代码；
- 执行路径已经过实测：G2 表格比较（Welch/配对 t）、DOE 契约（factorial_2x2）、G2 预测对比（mean vs OLS）；
- 下一步（开发侧）：`shell_to_contract.py`（壳 + 用户回答 → 契约）、分组划分（材料/电池防泄漏）、S5 多水平内核；
- 线 A（专家标注）另行推进：`Training_Data_Darcy_CViT/v2/expert/inbox/expert_batch_001_*`。

---

## 9. 版本记录

| 版本 | 日期 | 内容 |
|---|---|---|
| v1 | 2026-10-29 | 65 个场景（S1 19 / S2 11 / S3 13 / S4 11 / S5 10 / S6 1）；材料/化学 10 个主力壳 survey 升级；JSON 导出与索引；做深 3 件交付 |
