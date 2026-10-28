# 表格实验报告

比较A与B的平均y

报告为已声明设计下的探索性比较；显著性不证明因果，也不证明假设为真。

```json
{
  "schema_version": "tabular_report_v1",
  "complete": true,
  "experiment_id": "1629919652794db19d05482804d80e71",
  "spec": {
    "data_path": "two_groups.csv",
    "research_question": "比较A与B的平均y",
    "design": "independent",
    "response": "y",
    "unit": "id",
    "provenance": "synthetic",
    "sampling_note": "全部现有合成样本，仅作探索性分析",
    "factor": "group",
    "levels": [
      "A",
      "B"
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
    "hypothesis": "H0: E[y|A] - E[y|B] = 0",
    "methods": [
      "welch_t"
    ],
    "metric": "mean_difference, two-sided p, confidence interval",
    "preprocessing": "no transformation",
    "split": null,
    "replication": "distinct declared units; random seed is not an independent replicate",
    "assumptions": [
      "independent units; inspect outliers and distributional assumptions",
      "normal approximation for group means"
    ],
    "sample_basis": "全部现有合成样本，仅作探索性分析",
    "causal_claim": "not_established; provenance and randomization are user declarations",
    "stopping": "fixed plan, no hyperparameter search or test feedback",
    "failure": "pause at tool boundary; repair inputs with a new draft; no silent substitutions"
  },
  "data_sha256": "c8d22904e456e37a661431a7b598956cdd7c5f9d1d4b05b8ed4b3c26d95c4316",
  "plan_hash": "9b49a68a29a749a191f793b09ae957809305315699e45d9624fbb50a0bf102a5",
  "draft_hash": "8e0d8049178536c626214c2f932a9412a3321ead1c96c9c9f7928ca6f79458d0",
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
      26
    ],
    "omitted_indices": [],
    "units": 27,
    "missing_units": 0
  },
  "metrics": {
    "method": "welch_t",
    "direction": "A minus B",
    "levels": [
      "A",
      "B"
    ],
    "n": [
      12,
      15
    ],
    "means": [
      9.97747079419157,
      13.25103792624582
    ],
    "mean_difference": -3.27356713205425,
    "statistic": -3.4340286715996107,
    "degrees_of_freedom": 20.268761324223625,
    "p_value": 0.00258848929234127,
    "confidence_level": 0.95,
    "confidence_interval": [
      -5.260370983721181,
      -1.2867632803873188
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
  "evidence_ref": "tool_de06d2ec7888b432"
}
```
