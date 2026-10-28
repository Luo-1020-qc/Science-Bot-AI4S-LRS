"""Bounded CSV ingestion and deterministic statistical tools (no eval/shell)."""
import csv
import io
import math
from collections import Counter

from ....util import digest

MISSING = {"", "na", "n/a", "nan", "null", "none"}


def missing(value):
    return value.strip().casefold() in MISSING


def number(value):
    try:
        result = float(value)
    except (ValueError, TypeError):
        raise ValueError("响应和特征必须为有限数值，不能静默编码文本") from None
    if not math.isfinite(result):
        raise ValueError("数值包含无穷或非有限值")
    return result


def parse_csv(text):
    try:
        reader = csv.reader(io.StringIO(text.lstrip("\ufeff")), strict=True)
        columns = next(reader)
        if not 2 <= len(columns) <= 100 or any(not c.strip() or c != c.strip() or len(c) > 200 for c in columns):
            raise ValueError("CSV 需要2至100个非空、无首尾空白的列名")
        if len(set(columns)) != len(columns):
            raise ValueError("CSV 列名重复")
        rows = []
        for line, values in enumerate(reader, 2):
            if len(values) != len(columns):
                raise ValueError(f"CSV 第{line}条记录列数不一致（空行也需要修复）")
            if len(rows) >= 20000:
                raise ValueError("G2 最多支持20000条记录")
            rows.append(dict(zip(columns, values)))
    except (csv.Error, StopIteration) as exc:
        raise ValueError("CSV 为空或格式不合法") from exc
    if not rows:
        raise ValueError("CSV 没有数据记录")
    return columns, rows


def inspect_csv(workspace, path):
    source = workspace.read_text(path)
    if not source["path"].casefold().endswith(".csv"):
        raise ValueError("G2 只接受 UTF-8 逗号分隔 CSV；TSV 请先显式转换")
    columns, rows = parse_csv(source["text"])
    profiles = []
    for name in columns:
        values = [row[name] for row in rows if not missing(row[name])]
        numeric = bool(values)
        for value in values:
            try:
                number(value)
            except ValueError:
                numeric = False
                break
        # Never send raw observations or target summaries to the planner. Small
        # categorical levels help choose factors; a high-cardinality ID is omitted.
        levels = sorted(set(values))
        profiles.append({"name": name, "kind": "numeric" if numeric else "text", "missing": len(rows)-len(values),
                         "unique": len(levels), "levels": levels if not numeric and len(levels) <= 12 else []})
    return {"path": source["path"], "sha256": source["sha256"], "bytes": source["bytes"], "rows": len(rows),
            "columns": profiles, "evidence_ref": f"csv:{source['path']}#{source['sha256'][:12]}"}


def validate_data(spec, text):
    columns, rows = parse_csv(text)
    required = [spec.unit, spec.response]+(spec.features if spec.design == "prediction" else [spec.factor])
    if not set(required) <= set(columns):
        raise ValueError("设计引用了不存在的列："+", ".join(sorted(set(required)-set(columns))))
    if any(missing(row[spec.unit]) for row in rows):
        raise ValueError("实验单位列不能缺失")
    if spec.design != "prediction":
        if any(missing(row[spec.factor]) for row in rows):
            raise ValueError("因素列不能缺失")
        if set(row[spec.factor] for row in rows) != set(spec.levels):
            raise ValueError("因素必须恰好包含规格中的两个水平；不能静默筛掉其他组")
    identities = [row[spec.unit] for row in rows]
    if spec.design == "paired":
        pairs = Counter((row[spec.unit], row[spec.factor]) for row in rows)
        if any(n != 1 for n in pairs.values()) or any((unit, level) not in pairs for unit in identities for level in spec.levels):
            raise ValueError("配对设计要求每个实验单位在两个水平下各有且仅有一条记录")
    elif len(set(identities)) != len(identities):
        raise ValueError("独立/预测设计要求每行对应不同实验单位；重复测量需使用配对或新增区组工具")
    numeric_columns = [spec.response]+spec.features
    omitted_units = {row[spec.unit] for row in rows if any(missing(row[c]) for c in numeric_columns)}
    if omitted_units and spec.missing_policy == "reject":
        raise ValueError("所选数值列存在缺失值；请修复数据或明确 drop_complete_case 策略")
    # For paired data omit the entire unit, never break pairing by dropping rows.
    retained = [(i, row) for i, row in enumerate(rows) if row[spec.unit] not in omitted_units]
    for _, row in retained:
        for column in numeric_columns:
            number(row[column])
    if spec.design == "prediction":
        n = len(retained)
        if int(n*.6) <= len(spec.features)+1 or min(int(n*.2), n-int(n*.6)-int(n*.2)) < 3:
            raise ValueError("预测样本不足：训练数须超过特征数+截距，验证和测试各至少3个独立单位")
    else:
        counts = Counter(row[spec.factor] for _, row in retained)
        if min(counts.get(level, 0) for level in spec.levels) < 3:
            raise ValueError("比较至少需要每组3个观测，配对设计至少3个完整实验单位；小样本结果仍属探索性")
    return {"columns": columns, "rows": rows, "retained_indices": [i for i, _ in retained],
            "omitted_indices": [i for i, row in enumerate(rows) if row[spec.unit] in omitted_units],
            "units": len(set(row[spec.unit] for _, row in retained)),
            "missing_units": len(omitted_units)}


def compare(spec, data):
    import numpy as np
    from scipy import stats
    rows = [data["rows"][i] for i in data["retained_indices"]]
    groups = [[number(row[spec.response]) for row in rows if row[spec.factor] == level] for level in spec.levels]
    if spec.design == "paired":
        paired = {row[spec.unit]: {} for row in rows}
        for row in rows:
            paired[row[spec.unit]][row[spec.factor]] = number(row[spec.response])
        groups = [[values[level] for values in paired.values()] for level in spec.levels]
        if np.var(np.asarray(groups[0])-groups[1], ddof=1) <= 0:
            raise ValueError("配对差值无变异，t 检验无法估计不确定性；不会伪造 p 值")
        test = stats.ttest_rel(*groups, alternative="two-sided", nan_policy="raise")
    else:
        if sum(float(np.var(group, ddof=1)) for group in groups) <= 0:
            raise ValueError("两组均无变异，t 检验无法估计不确定性")
        test = stats.ttest_ind(*groups, equal_var=False, alternative="two-sided", nan_policy="raise")
    interval = test.confidence_interval(confidence_level=1-spec.alpha)
    result = {"method": "paired_t" if spec.design == "paired" else "welch_t",
              "direction": spec.levels[0]+" minus "+spec.levels[1], "levels": spec.levels,
              "n": [len(group) for group in groups], "means": [float(np.mean(group)) for group in groups],
              "mean_difference": float(np.mean(groups[0])-np.mean(groups[1])),
              "statistic": float(test.statistic), "degrees_of_freedom": float(test.df),
              "p_value": float(test.pvalue), "confidence_level": 1-spec.alpha,
              "confidence_interval": [float(interval.low), float(interval.high)],
              "reject_null": bool(test.pvalue < spec.alpha)}
    if not all(math.isfinite(result[key]) for key in ("statistic", "degrees_of_freedom", "p_value", "mean_difference")):
        raise ValueError("检验出现非有限值，已暂停")
    return result


def partition(spec, data):
    import numpy as np
    indices = np.random.default_rng(spec.seed).permutation(data["retained_indices"]).tolist()
    first, second = int(len(indices)*.6), int(len(indices)*.2)
    return {"seed": spec.seed, "train": indices[:first], "validation": indices[first:first+second],
            "test": indices[first+second:], "unit_column": spec.unit, "index_kind": "zero_based_data_record"}


def _xy(spec, data, indices):
    import numpy as np
    x = np.asarray([[number(data["rows"][i][name]) for name in spec.features] for i in indices], dtype=float)
    y = np.asarray([number(data["rows"][i][spec.response]) for i in indices], dtype=float)
    return x, y


def fit(spec, data, split):
    import numpy as np
    x, y = _xy(spec, data, split["train"])
    center, scale = x.mean(axis=0), x.std(axis=0)
    if np.any(scale == 0):
        raise ValueError("训练特征含常量列；请明确修订特征，不能自动忽略")
    matrix = np.column_stack([np.ones(len(x)), (x-center)/scale])
    coefficients, _, rank, singular = np.linalg.lstsq(matrix, y, rcond=None)
    if rank != matrix.shape[1] or not np.isfinite(coefficients).all():
        raise ValueError("训练矩阵秩不足或系数非有限，不能静默换模型")
    if float(singular[0]/singular[-1]) > 1e10:
        raise ValueError("训练矩阵病态，请修订特征")
    return {"mean": float(y.mean()), "coefficients": coefficients.tolist(), "features": spec.features,
            "center": center.tolist(), "scale": scale.tolist(), "rank": int(rank),
            "fit_indices_hash": digest(split["train"]), "fit_partition": "train_only"}


def _predictions(spec, data, indices, model):
    import numpy as np
    x, y = _xy(spec, data, indices)
    linear = np.column_stack([np.ones(len(x)), (x-model["center"])/model["scale"]]) @ np.asarray(model["coefficients"])
    return y, {"mean": np.full(len(y), model["mean"]), "ols": linear}


def select(spec, data, split, model):
    import numpy as np
    y, predictions = _predictions(spec, data, split["validation"], model)
    mse = {key: float(np.mean((value-y)**2)) for key, value in predictions.items()}
    # Deterministic tie rule prefers the simpler baseline.
    selected = "mean" if mse["mean"] <= mse["ols"] else "ols"
    return {"validation_mse": mse, "selected": selected, "selection_partition": "validation_only",
            "no_refit": True, "model_hash": digest(model)}


def evaluate(spec, data, split, model, selection):
    import numpy as np
    from scipy import stats
    y, predictions = _predictions(spec, data, split["test"], model)
    selected = selection["selected"]
    loss = (predictions[selected]-y)**2
    # Bootstrap uncertainty is descriptive for this frozen test sample; it is
    # not a confidence interval across independent model training repetitions.
    rng = np.random.default_rng(spec.seed+1)
    bootstrap = [float(np.mean(loss[rng.integers(0, len(loss), len(loss))])) for _ in range(1000)]
    interval = np.quantile(bootstrap, [spec.alpha/2, 1-spec.alpha/2]).tolist()
    delta = (predictions["mean"]-y)**2-(predictions["ols"]-y)**2
    se = float(stats.sem(delta))
    q = float(stats.t.ppf(1-spec.alpha/2, len(delta)-1))
    return {"selected": selected, "test_mse": float(loss.mean()), "test_rmse": float(np.sqrt(loss.mean())),
            "test_mse_bootstrap_interval": interval, "bootstrap_resamples": 1000,
            "confidence_level": 1-spec.alpha, "uncertainty_scope": "conditional on fixed fitted model; IID test-unit resampling",
            "baseline_minus_ols_mse": float(delta.mean()),
            "paired_loss_difference_interval": [float(delta.mean()-q*se), float(delta.mean()+q*se)],
            "test_mse_by_method": {name: float(np.mean((pred-y)**2)) for name, pred in predictions.items()},
            "indices": split["test"], "observed": y.tolist(), "predicted": predictions[selected].tolist(),
            "test_evaluations": 1, "selection_hash": digest(selection), "model_hash": digest(model)}
