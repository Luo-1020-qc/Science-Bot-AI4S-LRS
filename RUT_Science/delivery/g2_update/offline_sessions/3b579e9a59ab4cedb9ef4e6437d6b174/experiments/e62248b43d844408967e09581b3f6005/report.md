# 表格实验报告

同一合成单位before与after的平均差是否为零？

报告为已声明设计下的探索性比较；显著性不证明因果，也不证明假设为真。

```json
{
  "schema_version": "tabular_report_v1",
  "complete": true,
  "experiment_id": "e62248b43d844408967e09581b3f6005",
  "spec": {
    "data_path": "paired_measurements.csv",
    "research_question": "同一合成单位before与after的平均差是否为零？",
    "design": "paired",
    "response": "y",
    "unit": "id",
    "provenance": "synthetic",
    "sampling_note": "全部现有合成样本，仅作探索性演示；未进行事先功效计算",
    "factor": "condition",
    "levels": [
      "before",
      "after"
    ],
    "features": [],
    "randomization_note": "not_applicable",
    "missing_policy": "reject",
    "alpha": 0.05,
    "seed": 42,
    "schema_version": "experiment_spec_v1"
  },
  "protocol": {
    "goal": "two_sided_mean_comparison",
    "hypothesis": "H0: E[y|before] - E[y|after] = 0",
    "methods": [
      "paired_t"
    ],
    "metric": "mean_difference, two-sided p, confidence interval",
    "preprocessing": "no transformation",
    "split": null,
    "replication": "distinct declared units; random seed is not an independent replicate",
    "assumptions": [
      "independent units; inspect outliers and distributional assumptions",
      "complete matched units; approximately normal within-unit differences"
    ],
    "sample_basis": "全部现有合成样本，仅作探索性演示；未进行事先功效计算",
    "causal_claim": "not_established; provenance and randomization are user declarations",
    "stopping": "fixed plan, no hyperparameter search or test feedback",
    "failure": "pause at tool boundary; repair inputs with a new draft; no silent substitutions"
  },
  "data_sha256": "300b205b2110f10a20aad79687e0a2e765deb38529ec273d54d5209a251821ba",
  "plan_hash": "fafdf14a83941cbeb953e27a5f3571eade2eceb8b0bde960b4d08174dff00fd0",
  "draft_hash": "711cfe58806757d999d97466c4c630aadbbb7c94a73a5c4593d28eb1e34edffc",
  "sample": {
    "retained_indices": [
      0,
      1,
      2,
      3,
      4,
      5,
      6,
      7,
      8,
      9,
      10,
      11,
      12,
      13,
      14,
      15,
      16,
      17,
      18,
      19,
      20,
      21,
      22,
      23,
      24,
      25,
      26,
      27,
      28,
      29,
      30,
      31
    ],
    "omitted_indices": [],
    "units": 16,
    "missing_units": 0
  },
  "metrics": {
    "method": "paired_t",
    "direction": "before minus after",
    "levels": [
      "before",
      "after"
    ],
    "n": [
      16,
      16
    ],
    "means": [
      11.648251935130897,
      13.193745348994947
    ],
    "mean_difference": -1.5454934138640493,
    "statistic": -3.3935136459226243,
    "degrees_of_freedom": 15.0,
    "p_value": 0.004010810606680008,
    "confidence_level": 0.95,
    "confidence_interval": [
      -2.5162103693134927,
      -0.5747764584146046
    ],
    "reject_null": true
  },
  "scientific_success": null,
  "execution_success": true,
  "interpretation": "报告为已声明设计下的探索性比较；显著性不证明因果，也不证明假设为真。",
  "limitations": [
    "来源、独立性和随机化由用户声明，未通过列检查验证",
    "未进行事先功效/样本量计算；小样本、异常值或依赖结构会限制推断",
    "当前不支持多因素、聚类、时间序列、多重比较或自动超参数搜索"
  ],
  "versions": {
    "python": "3.12.14",
    "numpy": "2.5.4",
    "scipy": "1.18.1"
  },
  "artifacts": {
    "compare": "nodes/compare.json"
  },
  "evidence_ref": "tool_e0996101b9c7e7f7"
}
```
