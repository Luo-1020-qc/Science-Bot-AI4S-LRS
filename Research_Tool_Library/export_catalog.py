"""Export readable and machine-readable catalog from one set of contracts."""
from collections import Counter
import json
from core import ROOT
from catalog import CATALOG


def main():
    (ROOT/"tool_catalog.json").write_text(json.dumps({"version": "research_tool_catalog_v1", "date": "2026-10-28",
        "live_agent_registered": False, "tools": CATALOG}, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    providers = [{"type": "function", "function": {"name": row["name"], "description": row["purpose"], "parameters": row["input_schema"]}}
                 for row in CATALOG if row["implementation"] == "offline_implemented"]
    (ROOT/"provider_schemas.json").write_text(json.dumps(providers, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    lines = ["# 详细工具契约库", "", "由export_catalog.py生成。每个工具的状态是契约的一部分；未实现或真实执行工具不能调用。", "",
        "状态：offline_implemented=本目录可运行；existing_*=已有受限入口或复用数学检查；contract_only=仅设计；human_review_required=待人工流程；disabled_real_execution=本库禁用。", ""]
    for row in CATALOG:
        lines += ["## "+row["name"], "", row["purpose"], "", f"分组：`{row['group']}`；状态：`{row['implementation']}`。", "",
                  "前置条件："+"；".join(row["preconditions"] or ["无"]), "", "验收："+"；".join(row["acceptance"]), "",
                  "权限/作用："+row["authorization"]+"；"+row["effects"], "", "幂等："+row["idempotency"], "",
                  "失败处理："+"；".join(row["failure_contract"]), "", "输入：", "", "```json", json.dumps(row["input_schema"], ensure_ascii=False, indent=2), "```", "",
                  "输出：", "", "```json", json.dumps(row["output_schema"], ensure_ascii=False, indent=2), "```", "",
                  "下一步工具："+(", ".join("`"+name+"`" for name in row["next_tools"]) or "由上层计划决定"), ""]
    (ROOT/"详细工具契约.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"tools": len(CATALOG), "by_status": dict(Counter(row["implementation"] for row in CATALOG))}))


if __name__ == "__main__":
    main()
