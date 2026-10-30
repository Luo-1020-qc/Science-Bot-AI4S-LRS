# -*- coding: utf-8 -*-
"""材料/化学做深：用 G2 真实执行路径跑三个示例

路径 A：independent（材料拉伸，Welch t）
路径 B：paired（材料硬度，配对 t）
路径 C：prediction（材料性能预测，mean vs OLS）

数据为合成示例，仅用于验证执行链路；不代表真实材料结论。
"""
import csv
import json
import random
from pathlib import Path

from rut_science.science_bot.general.adapters import tabular
from rut_science.science_bot.general.experiment import ExperimentSpec

EX = Path(__file__).resolve().parent
EX.mkdir(parents=True, exist_ok=True)


def write_csv(name, header, rows):
    path = EX / name
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    return path


def gen_tensile():
    rng = random.Random(11)
    rows = []
    for i in range(12):
        rows.append([f"A{i+1:02d}", "formula_A", f"{rng.gauss(850, 15):.2f}"])
    for i in range(12):
        rows.append([f"B{i+1:02d}", "formula_B", f"{rng.gauss(820, 15):.2f}"])
    return write_csv("tensile.csv", ["specimen_id", "formula", "tensile_MPa"], rows)


def gen_hardness():
    rng = random.Random(22)
    rows = []
    for s in range(1, 13):
        base = rng.gauss(250, 20)
        rows.append([f"S{s:02d}", "process_A", f"{base + rng.gauss(0, 8):.2f}"])
        rows.append([f"S{s:02d}", "process_B", f"{base + 15 + rng.gauss(0, 8):.2f}"])
    return write_csv("hardness_paired.csv", ["sample_id", "process", "hardness_HV"], rows)


def gen_prediction():
    rng = random.Random(33)
    rows = []
    for i in range(60):
        c = rng.uniform(0.1, 0.6)
        mn = rng.uniform(0.5, 1.8)
        si = rng.uniform(0.1, 0.5)
        cr = rng.uniform(0.0, 1.2)
        y = 300 + 120 * c + 60 * mn + 40 * si + 30 * cr + rng.gauss(0, 8)
        rows.append([f"M{i+1:03d}", f"{c:.3f}", f"{mn:.3f}", f"{si:.3f}", f"{cr:.3f}", f"{y:.2f}"])
    return write_csv(
        "property_prediction.csv",
        ["sample_id", "C", "Mn", "Si", "Cr", "yield_MPa"],
        rows,
    )


def run_compare(csv_path, spec):
    text = csv_path.read_text(encoding="utf-8")
    data = tabular.validate_data(spec, text)
    result = tabular.compare(spec, data)
    result["units"] = data["units"]
    return result


def run_prediction(csv_path, spec):
    text = csv_path.read_text(encoding="utf-8")
    data = tabular.validate_data(spec, text)
    split = tabular.partition(spec, data)
    model = tabular.fit(spec, data, split)
    selection = tabular.select(spec, data, split, model)
    evaluation = tabular.evaluate(spec, data, split, model, selection)
    return {
        "split_sizes": {k: len(split[k]) for k in ("train", "validation", "test")},
        "selection": selection,
        "evaluation": {
            k: evaluation[k]
            for k in ("selected", "test_mse", "test_rmse", "test_mse_by_method",
                      "test_evaluations")
        },
    }


def main():
    tensile = gen_tensile()
    hardness = gen_hardness()
    prediction = gen_prediction()

    spec_tensile = ExperimentSpec(
        data_path=str(tensile),
        research_question="配方 A 与配方 B 的抗拉强度是否存在差异？",
        design="independent",
        response="tensile_MPa",
        unit="specimen_id",
        provenance="synthetic",
        sampling_note="每组 12 个独立试样（合成示例）",
        factor="formula",
        levels=["formula_A", "formula_B"],
    )
    spec_hardness = ExperimentSpec(
        data_path=str(hardness),
        research_question="同一批试样两种热处理后的硬度差异？",
        design="paired",
        response="hardness_HV",
        unit="sample_id",
        provenance="synthetic",
        sampling_note="12 个试样，每试样两种处理各测一次（合成示例）",
        factor="process",
        levels=["process_A", "process_B"],
    )
    spec_prediction = ExperimentSpec(
        data_path=str(prediction),
        research_question="用成分特征预测屈服强度，mean 与 OLS 哪个更好？",
        design="prediction",
        response="yield_MPa",
        unit="sample_id",
        provenance="synthetic",
        sampling_note="60 个独立试样（合成示例）",
        features=["C", "Mn", "Si", "Cr"],
        seed=42,
    )

    out = {
        "tensile_independent": run_compare(tensile, spec_tensile),
        "hardness_paired": run_compare(hardness, spec_hardness),
        "property_prediction": run_prediction(prediction, spec_prediction),
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
