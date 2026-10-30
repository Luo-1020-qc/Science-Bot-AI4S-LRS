#!/usr/bin/env python
"""export_shells_json.py — 学科壳 YAML → JSON 批量导出

输出：
- shells_json/<name>.json      与 YAML 一一对应
- shells_json/index.json       按骨架分组的总索引（含哈希）
- 矩阵_场景对照表.md            骨架 → 场景文件的导航表

规则：
- YAML 是唯一源；JSON 为派生文件，不要手改
- 解析/校验失败立刻报错退出（不静默跳过）
- 保留中文（ensure_ascii=False）
"""
import hashlib
import json
import sys
from datetime import date
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: 缺少依赖 pyyaml。请先执行: pip install pyyaml")
    sys.exit(1)

ROOT = Path(__file__).resolve().parent
YAML_DIR = ROOT / "shells"
JSON_DIR = ROOT / "shells_json"
SKELETONS_FILE = ROOT / "skeletons.yaml"
INDEX_FILE = JSON_DIR / "index.json"
NAV_FILE = ROOT / "矩阵_场景对照表.md"


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
        die(f"YAML 解析失败 {where}: {getattr(exc, 'problem', str(exc))}")


def load_skeletons():
    if not SKELETONS_FILE.is_file():
        die(f"找不到骨架注册表: {SKELETONS_FILE}")
    data = load_yaml(SKELETONS_FILE)
    if not isinstance(data, dict) or not isinstance(data.get("skeletons"), list):
        die("skeletons.yaml 结构错误：缺少 skeletons 列表")
    registry = {}
    for item in data["skeletons"]:
        if not isinstance(item, dict) or "id" not in item:
            die("skeletons.yaml 中存在缺少 id 的条目")
        registry[str(item["id"])] = {
            "name": item.get("name", ""),
            "primitive": item.get("primitive", ""),
            "status": item.get("status", ""),
        }
    return registry


def sha256(path):
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def main():
    registry = load_skeletons()
    if not YAML_DIR.is_dir():
        die(f"找不到学科壳目录: {YAML_DIR}")
    files = sorted(list(YAML_DIR.glob("*.yaml")) + list(YAML_DIR.glob("*.yml")))
    if not files:
        die(f"学科壳目录为空: {YAML_DIR}")

    JSON_DIR.mkdir(exist_ok=True)
    scenarios = []
    for path in files:
        data = load_yaml(path)
        if not isinstance(data, dict):
            die(f"{path.name}: 顶层必须是映射")
        for field in ("scenario_name", "domain", "skeleton"):
            if field not in data or data[field] in (None, ""):
                die(f"{path.name}: 缺少必填字段 {field}")
        sid = str(data["skeleton"])
        if sid not in registry:
            die(f"{path.name}: 未知骨架 id '{sid}'")
        executable_raw = data.get("executable")
        if executable_raw is None:
            executable = False
            missing_flag = True
        elif isinstance(executable_raw, bool):
            executable = executable_raw
            missing_flag = False
        else:
            die(f"{path.name}: executable 必须是 true/false")

        out = JSON_DIR / (path.stem + ".json")
        out.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        scenarios.append({
            "file": out.name,
            "source_yaml": path.name,
            "skeleton": sid,
            "scenario_name": str(data["scenario_name"]),
            "domain": str(data["domain"]),
            "executable": executable,
            "missing_executable_field": missing_flag,
            "sha256": sha256(out),
        })

    by_skeleton = {}
    for sid, meta in registry.items():
        items = [s for s in scenarios if s["skeleton"] == sid]
        by_skeleton[sid] = {
            "name": meta["name"],
            "primitive": meta["primitive"],
            "status": meta["status"],
            "count": len(items),
            "executable": sum(1 for s in items if s["executable"]),
            "scenarios": [
                {"file": s["file"], "scenario_name": s["scenario_name"],
                 "domain": s["domain"], "executable": s["executable"],
                 "sha256": s["sha256"]}
                for s in items
            ],
        }

    total = len(scenarios)
    executable_total = sum(1 for s in scenarios if s["executable"])
    index = {
        "schema_version": "shell_index_v1",
        "generated_at": date.today().isoformat(),
        "source": "shells/*.yaml",
        "generator": "export_shells_json.py",
        "totals": {
            "scenarios": total,
            "executable": executable_total,
            "non_executable": total - executable_total,
            "coverage_percent": round(executable_total / total * 100, 1) if total else 0.0,
        },
        "by_skeleton": by_skeleton,
    }
    INDEX_FILE.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # 导航表
    lines = [
        "# 矩阵 · 场景对照表",
        "",
        f"生成日期：{date.today().isoformat()}",
        f"来源：`shells/*.yaml`（{total} 个场景）",
        "",
        "| 骨架 | 内核状态 | 场景数 | 可执行 | 场景（点击文件查看） |",
        "|---|---|---:|---:|---|",
    ]
    for sid, block in by_skeleton.items():
        names = "、".join(
            f"[{s['scenario_name']}](shells/{s['source_yaml']})" if "source_yaml" in s else f"[{s['scenario_name']}](shells_json/{s['file']})"
            for s in block["scenarios"]
        ) or "—"
        lines.append(f"| {sid} {block['name']} | {block['status']} | {block['count']} | {block['executable']} | {names} |")
    lines += [
        "",
        f"**合计：** {total} 个场景，{executable_total} 个可执行"
        f"（{index['totals']['coverage_percent']}%）。",
        "",
        "> 本表由 `export_shells_json.py` 自动生成，请勿手改。",
        "",
    ]
    NAV_FILE.write_text("\n".join(lines), encoding="utf-8")

    print(f"exported {total} shells -> {JSON_DIR}")
    print(f"executable: {executable_total}/{total} ({index['totals']['coverage_percent']}%)")
    print(f"index: {INDEX_FILE}")
    print(f"navigation: {NAV_FILE}")


if __name__ == "__main__":
    main()
