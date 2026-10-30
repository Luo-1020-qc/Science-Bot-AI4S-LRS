# coverage-tool — 学科覆盖矩阵工具

把"学科壳"数据文件自动汇总成覆盖矩阵（骨架 × 场景），用于：
- 追踪泛化覆盖率（已覆盖多少学科场景、多少可执行）
- 答辩展示（一张表说明能力边界）
- 新增学科时自动更新，无需手工维护表格

**定位**：Tier 2 沙盒工具，不依赖 science bot 代码，可独立运行。

---

## 目录结构

```
coverage-tool/
├── skeletons.yaml          # 骨架注册表（10 个骨架：S1-S10）
├── shells/                 # 学科壳目录（每个场景一个 YAML）
│   ├── s1_chemistry_catalyst.yaml
│   ├── s2_clinical_paired.yaml
│   └── s3_synthesis_doe.yaml
├── coverage_matrix.py      # 生成器
└── matrix.md               # 自动生成的覆盖矩阵（不要手改）
```

## 运行

```powershell
cd "E:\CityU\Msc AIFS\Semester A\DSC6021\Hackthon\coverage-tool"
& "..\Science-Bot-AI4S-LRS\RUT_Science\.venv\Scripts\python.exe" coverage_matrix.py
```

依赖：`pyyaml`（项目 venv 已内置）。

## 学科壳字段说明

| 字段 | 必填 | 说明 |
|---|---|---|
| `scenario_name` | ✅ | 场景名，全局唯一 |
| `domain` | ✅ | 学科（如：化学、临床医学） |
| `skeleton` | ✅ | 所属骨架 id（必须在 skeletons.yaml 中存在） |
| `executable` | 建议 | true/false；缺失时按 false 计并标注"字段缺失" |
| `summary` | 建议 | 一句话场景说明 |
| `vocabulary` | 建议 | 领域词汇表（处理名/指标名/单位/对比） |
| `survey_questions` | 建议 | 访谈时要问清楚的问题 |
| `rubric` | 建议 | 逐条检查清单（计划建议书必须逐条核对） |
| `proposal_template` | 建议 | 建议书章节结构 |
| `source` / `notes` | 可选 | 来源与备注 |

## 校验规则（故意设计得"会大声报错"）

| 情况 | 行为 |
|---|---|
| YAML 语法错误 | 报错并指出 `文件名:行:列` |
| 引用不存在的骨架 id | 报错并列出该文件与可用 id |
| 必填字段缺失 | 报错并指出文件名与字段 |
| `executable` 缺失 | 按不可执行计，矩阵中标注"字段缺失" |
| shells 目录为空/不存在 | 报错退出 |
| 场景名重复 | 报错并指出两个文件 |

> 这些规则对应项目"宿主校验"原则：错误不能静默跳过。

## 新增学科壳的流程

1. 从 `shells/` 里复制一个同骨架的壳文件（模板）
2. 修改 `scenario_name` / `domain` / `vocabulary` / `survey_questions` / `rubric`
3. 跑一次生成器，确认矩阵更新、无报错
4. 把改动提交给负责人复核（rubric 质量是重点）
