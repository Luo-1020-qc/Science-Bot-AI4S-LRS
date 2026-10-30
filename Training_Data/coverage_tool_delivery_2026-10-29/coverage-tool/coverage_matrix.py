#!/usr/bin/env python
"""coverage_matrix.py — 学科覆盖矩阵生成器

读取 skeletons.yaml（骨架注册表）与 shells/ 目录下的学科壳 YAML，
生成 Markdown 覆盖矩阵（骨架 × 场景），并输出 matrix.md。

设计原则（与项目宿主校验思想一致）：
- 错误必须大声报出来：YAML 解析失败指出文件与行号；未知骨架 ID 指出文件名
- 缺失 executable 字段：按不可执行处理，但显式标注"字段缺失"，不静默
- shells 目录为空或不存在：报错退出
"""

import sys
from datetime import date
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: 缺少依赖 pyyaml。请先执行: pip install pyyaml")
    sys.exit(1)

ROOT = Path(__file__).resolve().parent
SKELETONS_FILE = ROOT / "skeletons.yaml"
SHELLS_DIR = ROOT / "shells"
OUTPUT_FILE = ROOT / "matrix.md"


def die(message):
    print("ERROR:", message)
    sys.exit(1)


def load_yaml(path):
    try:
        with path.open(encoding="utf-8") as stream:
            return yaml.safe_load(stream)
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        where = f"{path.name}:{mark.line + 1}:{mark.column + 1}" if mark else path.name
        problem = getattr(exc, "problem", None) or str(exc)
        die(f"YAML 解析失败 {where}: {problem}")
    except OSError as exc:
        die(f"无法读取文件 {path.name}: {exc}")


def load_skeletons():
    if not SKELETONS_FILE.is_file():
        die(f"找不到骨架注册表: {SKELETONS_FILE.name}")
    data = load_yaml(SKELETONS_FILE)
    if not isinstance(data, dict) or not isinstance(data.get("skeletons"), list):
        die(f"{SKELETONS_FILE.name} 结构错误: 缺少 skeletons 列表")
    registry = {}
    for item in data["skeletons"]:
        if not isinstance(item, dict) or "id" not in item:
            die(f"{SKELETONS_FILE.name} 中存在缺少 id 的骨架条目")
        sid = str(item["id"])
        if sid in registry:
            die(f"{SKELETONS_FILE.name} 中骨架 id 重复: {sid}")
        registry[sid] = {
            "name": item.get("name", "(未命名)"),
            "primitive": item.get("primitive", ""),
            "status": item.get("status", "unknown"),
        }
    return registry


def load_shells(registry):
    if not SHELLS_DIR.is_dir():
        die(f"找不到学科壳目录: {SHELLS_DIR}")
    files = sorted(list(SHELLS_DIR.glob("*.yaml")) + list(SHELLS_DIR.glob("*.yml")))
    if not files:
        die(f"学科壳目录为空: {SHELLS_DIR}（至少需要一个 .yaml 文件）")

    shells = []
    seen_names = {}
    for path in files:
        data = load_yaml(path)
        if not isinstance(data, dict):
            die(f"{path.name}: 顶层必须是映射（key: value）")
        for field in ("scenario_name", "domain", "skeleton"):
            if field not in data or data[field] in (None, ""):
                die(f"{path.name}: 缺少必填字段 {field}")
        skeleton_id = str(data["skeleton"])
        if skeleton_id not in registry:
            die(f"{path.name}: 引用了不存在的骨架 id '{skeleton_id}'（可用: {', '.join(sorted(registry))}）")

        name = str(data["scenario_name"])
        if name in seen_names:
            die(f"场景名重复: '{name}'（{seen_names[name]} 与 {path.name}）")
        seen_names[name] = path.name

        executable_raw = data.get("executable", None)
        missing_flag = executable_raw is None
        if missing_flag:
            executable = False
        elif isinstance(executable_raw, bool):
            executable = executable_raw
        else:
            die(f"{path.name}: executable 必须是 true/false，实际是 {executable_raw!r}")

        shells.append(
            {
                "file": path.name,
                "scenario_name": name,
                "domain": str(data["domain"]),
                "skeleton": skeleton_id,
                "executable": executable,
                "missing_flag": missing_flag,
            }
        )
    return shells


def build_table(registry, shells):
    by_skeleton = {sid: [] for sid in registry}
    for shell in shells:
        by_skeleton[shell["skeleton"]].append(shell)

    rows = []
    rows.append("| 骨架 | 名称 | 内核状态 | 场景数 | 可执行场景数 | 覆盖学科 |")
    rows.append("|---|---|---|---:|---:|---|")
    total = executable_total = 0
    missing_fields = []
    for sid, meta in registry.items():
        items = by_skeleton[sid]
        count = len(items)
        exec_count = sum(1 for it in items if it["executable"])
        domains = "、".join(sorted({it["domain"] for it in items})) or "—"
        rows.append(
            f"| {sid} | {meta['name']} | {meta['status']} | {count} | {exec_count} | {domains} |"
        )
        total += count
        executable_total += exec_count
        for it in items:
            if it["missing_flag"]:
                missing_fields.append(f"{it['file']}（{it['scenario_name']}）")

    coverage = (executable_total / total * 100) if total else 0.0
    summary = [
        "",
        f"**总场景数：** {total}",
        f"**可执行场景数：** {executable_total}",
        f"**可执行覆盖率：** {coverage:.1f}%",
    ]
    if missing_fields:
        summary.append(f"**executable 字段缺失（按不可执行计）：** {'；'.join(missing_fields)}")
    return "\n".join(rows), "\n".join(summary)


def main():
    registry = load_skeletons()
    shells = load_shells(registry)
    table, summary = build_table(registry, shells)
    content = "\n".join(
        [
            "# 学科覆盖矩阵",
            "",
            f"生成日期：{date.today().isoformat()}",
            f"骨架注册表：{SKELETONS_FILE.name}",
            f"学科壳目录：{SHELLS_DIR.name}/（{len(shells)} 个文件）",
            "",
            table,
            summary,
            "",
            "> 说明：本矩阵由脚本自动生成；可执行状态以 skeletons.yaml 的 status 与各学科壳的",
            "> executable 字段为准。required/planned/proposal_only 的差异不代表能力等级。",
            "",
        ]
    )
    OUTPUT_FILE.write_text(content, encoding="utf-8")
    print(content)
    print(f"已生成: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
