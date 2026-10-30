# 材料 / 化学场景做深：执行包

**日期：** 2026-10-29
**范围：** 材料与化学类学科壳（13 个核心场景 + 3 个电池相邻场景）
**目标：** 明确每个场景走哪条执行路径、映射到哪个真实契约、哪些能力当前不支持
**配套：** `deep-dive/S3_synthesis_execution_mapping.md`（DOE 路径细节）、`deep-dive/examples/`（可复现脚本与数据）

---

## 1. 场景清单与执行路径

| # | 学科壳 | 骨架 | 执行路径 | 今天可执行 |
|---:|---|---|---|---|
| 1 | `s1_materials_tensile` 两种配方抗拉强度 | S1 | G2 独立比较（Welch t） | ✅ 已实测 |
| 2 | `s1_materials_coating_wear` 两种涂层耐磨性 | S1 | G2 独立比较 | ✅ |
| 3 | `s1_chemistry_catalyst` 两种催化剂产率 | S1 | G2 独立比较 | ✅ |
| 4 | `s2_materials_hardness` 同批试样两种热处理硬度 | S2 | G2 配对比较（配对 t） | ✅ 已实测 |
| 5 | `s2_chemistry_method_comparison` 两种检测方法比对 | S2 | G2 配对比较 | ✅ |
| 6 | `s3_synthesis_doe` 温度×时间合成 DOE | S3 | DOE 契约（factorial_2x2） | ✅ 已实测 |
| 7 | `s3_materials_sintering` 烧结温度×时间 | S3 | DOE 契约（factorial_2x2 / 区组） | ✅ |
| 8 | `s3_catalyst_additives` 助剂组合筛选 | S3 | DOE 契约（factorial_2x2） | ✅ |
| 9 | `s3_materials_coating_cure` 涂层厚度×固化温度 | S3 | DOE 契约（factorial_2x2） | ✅ |
| 10 | `s3_chemical_reactor_rsm` 响应面优化 | S3 | ❌ 超出 2 水平内核 | ⛔ 仅建议书 |
| 11 | `s4_materials_property_prediction` 成分→屈服强度 | S4 | G2 预测对比（mean vs OLS） | ✅ 已实测 |
| 12 | `s4_qsar` 分子描述符→活性 | S4 | G2 预测对比（预计算描述符） | ✅ |
| 13 | `s4_materials_fatigue` 工艺→疲劳寿命 | S4 | G2 预测对比（对数寿命） | ✅（需分组划分，见 §5） |
| 14 | `s3_battery_cycling` 充放电参数→容量保持 | S3 | DOE 契约 | ✅ |
| 15 | `s3_battery_electrolyte` 电解液×温度 | S3 | DOE 契约 | ✅ |
| 16 | `s4_battery_fade` 工况→容量衰减 | S4 | G2 预测对比 | ✅（需按电芯分组） |

**结论：16 个场景中 15 个今天有执行路径；1 个（响应面）诚实标注为仅建议书。**

---

## 2. 路径 A：G2 独立 / 配对比较（S1 / S2）

### 2.1 survey → ExperimentSpec 字段映射

| survey 维度 | ExperimentSpec 字段 | 取值规则 | 说明 |
|---|---|---|---|
| 处理定义 | `factor` + `levels` | 恰好 2 个水平（字符串） | 多于 2 组 → S5（待开发） |
| 独立 or 配对 | `design` | `independent` / `paired` | 配对要求每单位在两水平下各一条记录 |
| 实验单位 | `unit`（列名） | 独立：每行唯一；配对：单位×水平唯一 | 重复测量需用配对或新区组工具 |
| 响应指标 | `response`（列名） | 数值列 | 单一响应 |
| 重复次数 | `sampling_note` | ≥3/组（校验强制） | 写入来源依据，不写"拍脑袋" |
| 缺失处理 | `missing_policy` | `reject` / `drop_complete_case` | 配对缺失整单位剔除 |
| 数据性质 | `provenance` | `observational` / `randomized` / `synthetic` | randomized 必须写 `randomization_note`，不能由模型补造 |
| 显著性与种子 | `alpha`（.001–.2）/ `seed` | 默认 .05 / 42 | alpha 是约定，不是领域真理 |

**当前不支持**（诚实边界）：
- 三组及以上（S5）
- 效应阈值/实际意义判定（只报告均值差、p、CI；阈值需外部声明）
- 测量单位字段（单位写在列名或 `sampling_note`）
- 非参检验（Welch/配对 t 之外的方法）

### 2.2 实测结果（合成数据，链路由 `examples/run_g2_demos.py` 复现）

**材料拉伸（独立，24 个试样）**

| 项目 | 结果 |
|---|---|
| 方法 | Welch t |
| 均值 | A 848.11 MPa vs B 822.92 MPa |
| 均值差 | 25.19 MPa，95% CI [12.64, 37.75] |
| p 值 | 0.00041（拒绝原假设） |

**材料硬度（配对，12 个试样）**

| 项目 | 结果 |
|---|---|
| 方法 | 配对 t |
| 均值 | A 251.69 HV vs B 266.27 HV |
| 均值差 | −14.59 HV，95% CI [−24.11, −5.06] |
| p 值 | 0.00625（拒绝原假设） |

> 以上为**合成示例**，用于验证执行链路，不代表任何真实材料结论。

---

## 3. 路径 B：DOE 契约（S3）

详细映射见 `S3_synthesis_execution_mapping.md`。材料/化学的 4 个 S3 场景复用同一模板，仅替换字段：

| 场景 | `factors`（2×2） | `response` | 区组建议 |
|---|---|---|---|
| 合成 DOE | temperature {80C,120C} × time {30min,90min} | yield / % | 原料批次 |
| 烧结 | temperature {1200C,1400C} × hold {2h,6h} | density / % | 炉次/装舟位置 |
| 助剂筛选 | additive_A {0,1} × additive_B {0,1} | conversion / % | 催化剂制备批次 |
| 涂层固化 | thickness {20um,50um} × cure_temp {80C,120C} | adhesion / 级 | 基材批次 |

**共同约束**：
- 每个因子恰好 2 水平；超过 2 水平或中心点 → 需要 DOE v2
- 单一响应
- 安全约束（溶剂沸点、炉温上限、压力）无字段，写入 `question` + 外部评审
- `nominal_power` 条件于声明的 sigma（见 S3 文档 §4 扫描表）

---

## 4. 路径 C：G2 预测对比（S4）

### 4.1 survey → ExperimentSpec 字段映射

| survey 维度 | ExperimentSpec 字段 | 取值规则 |
|---|---|---|
| 特征定义 | `features` | 1–20 个数值列；不能与响应/单位列重名 |
| 响应 | `response` | 数值列；可与对数变换后的列同名（如 `log_life`） |
| 实验单位 | `unit` | 每行唯一（当前不支持分组） |
| 数据来源 | `provenance` + `sampling_note` | 来源与样本量依据 |
| 划分 | 固定 60/20/20 + `seed` | 不可自定义比例 |
| 预处理 | 自动只在训练集拟合 | 标准化；不支持缺失填补 |
| 模型选择 | 验证集 MSE；平局偏好 mean | 测试集只评一次 |

**当前不支持（材料场景的关键限制）**：
- **按批次/炉号/电芯分组划分**：当前划分是随机置换，同批次样本可能跨集 → 对材料/电池数据是泄漏风险
- 自定义划分比例
- 非线性模型（只有 mean 与 OLS）
- 缺失值填补（缺失按策略剔除）

### 4.2 实测结果（合成数据，60 个试样）

| 项目 | 结果 |
|---|---|
| 划分 | train 36 / validation 12 / test 12 |
| 验证集 MSE | mean 911.13 vs OLS 76.17 → 选中 OLS |
| 测试集 MSE | OLS 137.51（RMSE 11.73 MPa） |
| 测试评价次数 | 1 |
| 选择依据 | 仅验证集；平局规则偏好 mean |

---

## 5. 验收规则来源（材料/化学）

### 5.1 测量标准（已核实）

| 场景 | 标准 | 用途 |
|---|---|---|
| 拉伸 | ASTM E8/E8M；GB/T 228.1 | 试样尺寸、加载速率、引伸计 |
| 硬度 | ASTM E384；ISO 6507 | 显微压痕、载荷、保压时间 |
| 磨损 | ASTM G99 | 销盘磨损、载荷、转速 |
| 预测 | Cawley & Talbot (2010)；scikit-learn 数据泄漏说明 | 选择偏差与泄漏 |

### 5.2 仍然缺失（不得编造）

| 规则 | 状态 | 需要什么 |
|---|---|---|
| 抗拉强度最小有意义差异 | ⚠️ 占位 | 产品规格/设计许用值 |
| 硬度最小有意义差异 | ⚠️ 占位 | 工艺规范或客户要求 |
| 产率 5%（S3 示例） | ⚠️ 占位 | 工艺目标或历史改进幅度 |
| sigma（各组） | ⚠️ 占位 | 历史批次标准差或 pilot |
| 疲劳寿命的适用域 | ⚠️ 占位 | 应力水平范围与失效判据 |

> 测量标准回答"怎么测"，不回答"差多少才算有意义"——后者必须来自工程需求。

---

## 6. 验证记录

| 验证项 | 结果 |
|---|---|
| G2.4 官方测试 | Ran 49 tests — OK（53 子测试） |
| 路径 A 独立比较 | ✅ Welch t 正常输出 |
| 路径 A 配对比较 | ✅ 配对 t 正常输出 |
| 路径 C 预测 | ✅ 划分/拟合/选择/单次评价正常 |
| DOE 示例契约 | ✅ 15 项检查中仅 power 按配置阻断 |

**复现命令：**

```powershell
cd "E:\CityU\Msc AIFS\Semester A\DSC6021\Hackthon\coverage-tool\deep-dive\examples"
& "..\..\..\Science-Bot-AI4S-LRS\RUT_Science\.venv\Scripts\python.exe" run_g2_demos.py
```

---

## 7. 给开发队友的待办（按优先级）

1. **分组划分**（P0）：预测路径支持按 `group_column`（批次/炉号/电芯）划分——材料与电池场景的防泄漏前提
2. **多水平因子**（P1）：S5 的 10 个场景与响应面共用同一扩展（水平数 3+）
3. **`shell_to_contract.py`**（P1）：学科壳 YAML + 用户回答 → 自动生成 G2/DOE 契约（当前手工）
4. **响应面 v2**（P2）：中心点 + 二次模型；影响 `s3_chemical_reactor_rsm`
5. **效应阈值字段**（P2）：在契约中显式记录"实际意义阈值"及其来源

---

## 8. 答辩可用的三句话

1. "材料/化学的 16 个场景中，15 个今天已有可执行路径；1 个响应面场景我们诚实标注为仅建议书。"
2. "拉伸、硬度、性能预测三条路径都用真实执行器跑通过，输出包含效应量、置信区间与单次测试评价。"
3. "我们知道自己的边界：多水平、分组划分、响应面还不支持——这些都已写成开发待办，而不是用演示掩盖。"
