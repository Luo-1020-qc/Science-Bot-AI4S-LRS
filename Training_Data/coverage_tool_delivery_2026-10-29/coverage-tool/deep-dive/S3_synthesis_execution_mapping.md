# S3 合成 DOE：学科壳 → 执行契约映射（做深第一件）

**日期：** 2026-10-29
**范围：** `coverage-tool/shells/s3_synthesis_doe.yaml` → `doe_contract_v1`
**目的：** 把"能提问"的学科壳升级为"能生成可校验契约"的执行样板
**依据代码：** `RUT_Science/research/strategy_learning/studies/g2_4/doe/`（schema / compiler / validation）

---

## 1. 目标协议：doe_contract_v1 字段一览

| 字段 | 取值 / 约束 |
|---|---|
| `schema_version` | 固定 `doe_contract_v1` |
| `request_hash` | 64 位十六进制；必须等于 request 的摘要 |
| `revision` | 1–1000 |
| `question` | 研究问题文本（≤2000 字符） |
| `family` | `crd_two_arm` / `rcbd_two_arm` / `factorial_2x2` |
| `factors[]` | 1–2 个；每个 `name`（`[A-Za-z][A-Za-z0-9_]*`）+ `levels`（**恰好 2 个**不重复字符串，≤80 字符） |
| `response` | `name` / `unit` / `direction`（`lower` 或 `higher`） |
| `experimental_unit` | `definition` / `independence_basis` / `measurement_repeats`（1–100） |
| `blocks[]` | 0–100 个不重复字符串；RCBD 要求 ≥2 且 `replicates=1`；factorial 允许 0 或 ≥2 |
| `replicates` | 1–100 |
| `assumptions` | 必须含 `normal_iid_errors` + `constant_error_variance`；有区组时必须加 `no_treatment_block_interaction` |
| `randomization` | `seed`（0–2³¹−1）+ `algorithm=shuffle_v1` |
| `analysis` | `model` / `primary_term` / `alpha`（.001–.2）/ `minimum_effect` / `sigma` / `target_power`（.5–.9999）/ `multiplicity=single_primary` / `missing_policy=stop_and_review` / `decision_rule=two_sided_t_ci_practical_relevance_separate` |
| `resources` | `per_run` / `budget`（单位预算） |
| `provenance[]` | **恰好 8 条**，覆盖 `/question /factors /response /experimental_unit /blocks /assumptions /analysis /resources`，每条绑定 `evidence_id` |
| `run_plan[]` | 4–1000 行；由 `compile_plan` 按 seed 生成，`replicates` 与区组决定行数 |

**请求协议 `doe_request_v1`**：`scope=design_only`、`execution_permission=denied`、9 条 evidence（8 个 claim path + `/family`），每条 `status` 必须为 `provided` 才能通过校验。

---

## 2. 逐条映射：survey_questions → 契约字段

| # | 学科壳问题 | 契约字段 | 取值规则 | 对应校验器检查 |
|---:|---|---|---|---|
| 1 | 关键因子有哪些？为什么选温度×时间？ | `question`、`factors[].name`、`family` | 1 个因子 → `crd`/`rcbd`；2 个因子 → `factorial_2x2` | `supported_scope`、`design_layout` |
| 2 | 可行域、水平与安全约束？ | `factors[].levels` | 恰好 2 个字符串；数值写进标签（如 `"80C"`/`"120C"`）。**安全约束无专属字段**，写入 `question` 并进入外部评审 | `contract_schema`、`design_layout` |
| 3 | 是否需要区组（原料批次/操作员/釜位）？ | `blocks[]`、`assumptions` | 有区组 → 必须加 `no_treatment_block_interaction`；RCBD 要求 ≥2 区组且 `replicates=1` | `assumptions_declared`、`design_layout` |
| 4 | 试验顺序如何安排？是否需要中心点？ | `randomization.seed`、`run_plan` | seed 锁定 `shuffle_v1` 生成的顺序；**v1 不支持中心点/多水平**（仅 2 水平） | `randomization_schedule` |
| 5 | 每个组合重复几次？重复是否独立？ | `replicates`、`experimental_unit.definition` / `independence_basis` / `measurement_repeats` | 重复是独立实验单元；`measurement_repeats` 是同一单元内的测量次数，不增加单元数 | `experimental_units`、`residual_degrees_of_freedom` |
| 6 | 产率如何测量？误差来源？ | `response.name` / `unit` / `direction`、`analysis.sigma` | 单一响应；sigma 必须来自 pilot 或用户声明（source 标 `pilot_estimate`） | `evidence_grounding`、`nominal_power` |
| 7 | 纯度/副产物是否记录？ | **无契约字段** | 单一响应协议：补充观察需单独记录，不进入主分析 | —（限制，见 §5） |
| 8 | 最小效应与依据？ | `analysis.minimum_effect`、`target_power`、`alpha` | 效应与 sigma 同单位；功效由验证器按非中心 t 计算 | `nominal_power` |

---

## 3. rubric → 校验器检查映射

| rubric 条目 | 校验器检查 | 说明 |
|---|---|---|
| 因子与水平有可行域依据 | `evidence_grounding`（source=user_declaration/pilot_estimate） | 只证明"有来源"，不证明来源本身正确 |
| 随机化与区组方案已声明 | `randomization_schedule` | 重算调度必须与 seed 一致 |
| 试验顺序与中心点/重复点安排 | `randomization_schedule` | 中心点不被 v1 支持 |
| 每个组合重复 ≥2 且独立 | `experimental_units`、`residual_degrees_of_freedom` | 单元 ID 必须唯一 |
| 产率测定方法与误差来源 | `response` 字段 + `nominal_power` | 测量误差进入 sigma |
| 纯度/副产物记录 | **无对应检查** | 协议限制 |
| 功效/方差依据有来源 | `nominal_power` | 条件于声明的 sigma 与模型 |
| 安全约束已声明 | **无对应检查** | 需外部评审 |

> 注意：验证器最后一条 `real_world_assumptions` 永远是 `unverified`——单元独立性、方差、测量质量与真实随机化都需要外部证据。这是设计上的诚实边界。

---

## 4. 实测：示例契约与功率扫描

**示例配置**（合成参数场景，2×2 全因子 + 2 个原料批次区组）：

```json
{
  "family": "factorial_2x2",
  "factors": [
    {"name": "temperature", "levels": ["80C", "120C"]},
    {"name": "time", "levels": ["30min", "90min"]}
  ],
  "response": {"name": "yield", "unit": "%", "direction": "higher"},
  "blocks": ["batch1", "batch2"],
  "replicates": 3,
  "analysis": {
    "model": "blocked_full_factorial",
    "primary_term": "temperature:time",
    "alpha": 0.05,
    "minimum_effect": 5.0,
    "sigma": 2.0,
    "target_power": 0.8
  }
}
```

**扫描结果**（`primary_term=temperature:time`，MDE=5%，target_power=0.8，2 区组）：

| 重复/区组 | sigma | 运行数 | 残差 df | 名义功效 | 是否通过 |
|---:|---:|---:|---:|---:|---|
| 2 | 1.0 | 16 | 11 | 0.995 | ✅ |
| 2 | 1.5 | 16 | 11 | 0.858 | ✅ |
| 2 | 2.0 | 16 | 11 | 0.625 | ❌ `nominal_power` |
| 3 | 2.0 | 24 | 19 | 0.827 | ✅ |
| 4 | 2.0 | 32 | 27 | 0.926 | ✅ |
| 3 | 3.0 | 24 | 19 | 0.491 | ❌ |
| 6 | 3.0 | 48 | 43 | 0.806 | ✅ |
| 8 | 3.0 | 64 | 59 | 0.906 | ✅ |

**结论：**
1. 功率校验是真实约束：sigma=2% 时 3 次重复（24 次运行）刚好通过（0.827）；sigma=3% 时需 6 次重复（48 次运行）。
2. 这让"预算 vs 功效"的取舍变成可计算、可展示的证据，而不是拍脑袋。
3. 所有未通过配置的 blocker 都是 `nominal_power`，其余 14 项检查全部通过——说明契约结构、来源绑定、随机化、可估计性都是正确的。

---

## 5. 边界与限制（必须写进答辩与建议书）

1. **仅支持 2 水平因子**：不能表达中心点、响应面或多水平；温度只能二选一（如 80/120°C）。
2. **单一响应**：产率与纯度不能同时作为主响应；副产物需单独记录，不进入主分析。
3. **安全约束无字段**：溶剂沸点、压力上限等只能写在 question 并进入外部评审。
4. **区组一致性依赖人工**：验证器只能确认调度与 seed 一致，不能证明原料批次真的同质。
5. **功效条件于声明 sigma**：`nominal_power` 是"条件于声明的 sigma 与模型假设"的数字，不是实测功效。
6. **real_world_assumptions 永远 unverified**：单元独立性、测量质量与真实随机化需外部证据。

---

## 6. 使用方式

```powershell
# 在 science bot 内校验（契约 JSON + 请求 JSON）
/doe validate '{"request":{...},"contract":{...}}'

# 或直接调用验证器（开发侧）
.\RUT_Science\.venv\Scripts\python.exe -c "from doe.validation import validate; ..."
```

**下一步（给开发队友）：**
- [ ] 写一个 `shell_to_contract.py`：读学科壳 YAML + 用户回答 → 生成 `doe_request_v1` + `doe_contract_v1`（当前是手工映射）
- [ ] 把 `/doe` 访谈的问卷字段与学科壳的 `survey_questions` 对齐（现在两者独立）
- [ ] 决定中心点/多水平是否进入 v2（会扩大 schema 与校验器）

---

## 7. 验收规则来源（做深第二件）

### 7.1 方法学来源（已核实）

| 规则 | 取值 | 来源 | 说明 |
|---|---|---|---|
| `alpha = 0.05` | 双侧 5% | Cohen (1988) 的常规约定；NIST/SEMATECH e-Handbook 样本量章节使用同一记号 | 显著性水平是**约定**，不是领域真理 |
| `target_power = 0.80` | 80% | Cohen (1988)：power 常设为 .80；NIST 样本量表以 1−β = 0.80/0.90 等档位给出 | 同上 |
| 样本量取决于 α、β、σ、δ | — | NIST/SEMATECH e-Handbook §7.2.2.2（Sample sizes required） | 明确写出：没有 σ 与 δ 就无法计算样本量 |
| 最小可检测效应（MDE）定义 | — | NIST §7.2.2.2；MDRC MDE 说明 | MDE 是"设计在给定功效下能检出的最小真实差异" |

**引用：**
- NIST/SEMATECH e-Handbook of Statistical Methods: <https://www.itl.nist.gov/div898/handbook/>
- NIST §7.2.2.2 Sample sizes required: <https://www.itl.nist.gov/div898/handbook/prc/section2/prc222.htm>
- Cohen, J. (1988). *Statistical Power Analysis for the Behavioral Sciences*（power=.80、α=.05 的常规约定；二手引用见 <https://pmc.ncbi.nlm.nih.gov/articles/PMC6736231/>）

### 7.2 领域数值（仍待补，不得编造）

| 规则 | 当前示例值 | 状态 | 需要什么 |
|---|---|---|---|
| `minimum_effect = 5%`（产率） | 5 个百分点 | ⚠️ 占位 | 工艺/质量标准：产率提升多少才有经济或工艺意义（规格限、客户要求、历史改进幅度） |
| `sigma = 2%`（产率） | 2 个百分点 | ⚠️ 占位 | 历史批次标准差或 pilot 实验记录；无来源时 `nominal_power` 校验会挡住 |
| `analysis.primary_term` | `temperature:time`（交互） | 示例 | 研究问题决定：主效应还是交互；必须在看数据前声明 |
| `replicates` / `blocks` | 3 / 2 | 示例 | 由功效与资源共同决定（见 §4 扫描表） |

> **诚实声明**：方法学约定（α、power）有公开来源；**领域数值（5%、2%）目前只是占位，不是已验证标准**。正式提交前必须把来源写进 `evidence.reference`，否则只能标注为"示例/待校准"。

### 7.3 给领域负责人的查证清单

- [ ] 产率 5 个百分点的工艺意义：查产品规格书、工艺改进目标或文献中的典型改进幅度
- [ ] sigma 2%：取历史批次数据计算标准差（至少 10 批），或做 3–5 次 pilot
- [ ] 主效应 vs 交互：与研究问题对齐（"温度和时间是否协同"→ 交互；"温度是否有效"→ 主效应）
- [ ] 资源约束：单次反应成本 × 计划运行数，确认预算字段可覆盖

---

## 8. 验证记录（做深第三件）

### 8.1 G2.4 官方测试

```
运行方式：先安装隔离守卫，再发现测试（run.py test 的同一路径）
结果：Ran 49 tests — OK（53 项子测试通过）
```

**注意**：直接 `pytest` 会因未调用 `doe.guard.install()` 而使隔离测试
（`test_live_import_network_process_and_external_write_are_blocked`）失败；
正确方式是用官方入口或显式安装守卫。这是测试运行方式问题，不是代码缺陷。

### 8.2 示例契约验证

§4 的三种配置均通过结构性检查（schema、来源绑定、随机化、可估计性、残差自由度），
仅 `nominal_power` 一项按配置不同而通过/阻断——证明校验器按预期工作。

### 8.3 尚未验证

- [ ] `shell_to_contract.py` 自动化（当前映射为手工）
- [ ] `/doe` 访谈与学科壳 survey 的对齐
- [ ] 真实产率数据（本做深全程使用合成示例值）
