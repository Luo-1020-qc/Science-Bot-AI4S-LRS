"""Persistent G2 plan executor; pure bounded tools, one committed result per node."""
import hashlib
import json
from pathlib import Path
import platform
import uuid

from ...util import canonical, digest, write_json
from .experiment import ExperimentSpec, ExecutionPlan
from .adapters import tabular


def _read(path):
    if path.resolve() != path:
        raise ValueError("实验记录不能重定向")
    return json.loads(path.read_text(encoding="utf-8"))


def _bounded_bytes(path):
    from ..workspace import MAX_TEXT_BYTES
    if path.resolve() != path:
        raise ValueError("实验输入不能重定向")
    with path.open("rb") as stream:
        raw = stream.read(MAX_TEXT_BYTES+1)
    if len(raw) > MAX_TEXT_BYTES:
        raise ValueError("CSV 超出128 KiB边界")
    return raw


class TabularExperiment:
    def __init__(self, parent, folder):
        self.parent, self.folder = parent, Path(folder)
        if self.folder.resolve() != self.folder or not self.folder.is_relative_to(parent.folder/"experiments"):
            raise ValueError("Invalid tabular experiment folder")
        self.meta = _read(self.folder/"experiment.json")
        self.spec = ExperimentSpec.from_dict(self.meta["spec"])
        self.plan = ExecutionPlan(**self.meta["plan"])
        expected = ExecutionPlan.build(self.spec, self.meta["data_sha256"]).to_dict()
        if self.plan.to_dict() != expected or self.confirmation != self.meta["draft_hash"]:
            raise ValueError("Tabular specification or plan identity changed")

    @classmethod
    def create(cls, parent, spec):
        if parent.workspace is None:
            raise ValueError("请先绑定 CSV 所在工作区")
        source = parent.workspace.read_text(spec.data_path)
        if source["path"] != spec.data_path or not spec.data_path.casefold().endswith(".csv"):
            raise ValueError("data_path 必须为当前项目的规范相对 CSV 路径")
        data = tabular.validate_data(spec, source["text"])
        plan = ExecutionPlan.build(spec, source["sha256"])
        needed = len(plan.nodes)
        if parent.limits["tool_calls"]-parent.meta["tool_attempts"] < needed:
            raise ValueError(f"剩余工具预算不足，计划还需{needed}次执行工具；请新建会话或减少其他工具调用")
        folder = parent.folder/"experiments"/uuid.uuid4().hex
        folder.mkdir(parents=True)
        # Store the actual bytes, including BOM, so the snapshot hash is the
        # same identity that was inspected and will be checked at confirmation.
        path = parent.workspace.resolve_file(spec.data_path)
        raw = _bounded_bytes(path)
        if hashlib.sha256(raw).hexdigest() != source["sha256"]:
            raise ValueError("CSV 在准备过程中变化，请重新检查")
        (folder/"input.csv").write_bytes(raw)
        meta = {"engine_version": "tabular_v1", "id": folder.name, "spec": spec.to_dict(), "plan": plan.to_dict(),
                "protocol": spec.protocol(), "data_sha256": source["sha256"], "workspace": parent.workspace.binding,
                "draft_hash": digest([spec.to_dict(), plan.to_dict()]), "confirmed": None, "phase": "draft",
                "completed": {}, "report_ref": None, "error": None,
                "validation": {key: data[key] for key in ("retained_indices", "omitted_indices", "units", "missing_units")},
                "tool_budget": {"required": needed, "remaining_at_draft": parent.limits["tool_calls"]-parent.meta["tool_attempts"]}}
        write_json(folder/"experiment.json", meta)
        return cls(parent, folder)

    @property
    def confirmation(self):
        return digest([self.spec.to_dict(), self.plan.to_dict()])

    @property
    def done(self):
        return self.meta["phase"] == "complete"

    def save(self):
        write_json(self.folder/"experiment.json", self.meta)

    def check_identity(self):
        if self.parent.workspace.binding != self.meta["workspace"]:
            raise ValueError("实验工作区身份改变")
        source = self.parent.workspace.read_text(self.spec.data_path)
        raw = _bounded_bytes(self.folder/"input.csv")
        if source["sha256"] != self.meta["data_sha256"] or hashlib.sha256(raw).hexdigest() != self.meta["data_sha256"]:
            raise ValueError("CSV 或实验快照自草案后发生变化，请创建新草案并重新确认")
        return tabular.validate_data(self.spec, raw.decode("utf-8-sig"))

    def confirm(self, value):
        if value != self.confirmation or self.meta["phase"] == "cancelled":
            raise ValueError("确认哈希无效或该实验已取消，请重新准备")
        self.check_identity()
        self.meta.update(confirmed=value, phase="confirmed")
        self.save()

    def result(self, node_id):
        record = self.meta["completed"].get(node_id)
        if not record or record["ref"] != f"nodes/{node_id}.json":
            raise ValueError("Dependency result is not committed")
        result = _read(self.folder/record["ref"])
        if digest(result) != record["sha256"]:
            raise ValueError("Committed node result has changed")
        return result

    def report(self):
        return self.result("report") if "report" in self.meta["completed"] else None

    def execute_node(self, tool, arguments):
        node = next((node for node in self.plan.nodes if node["id"] == arguments["node_id"]), None)
        if (node is None or tool != node["tool"] or self.meta["confirmed"] != self.confirmation
                or self.meta["phase"] != "running"):
            raise ValueError("Tool does not match the confirmed running plan")
        if node["id"] in self.meta["completed"]:
            return self.result(node["id"])
        for dependency in node["depends_on"]:
            self.result(dependency)
        data = self.check_identity()
        name = node["id"]
        if name == "compare":
            return tabular.compare(self.spec, data)
        if name == "partition":
            return tabular.partition(self.spec, data)
        if name == "fit":
            return tabular.fit(self.spec, data, self.result("partition"))
        if name == "select":
            return tabular.select(self.spec, data, self.result("partition"), self.result("fit"))
        if name == "evaluate":
            return tabular.evaluate(self.spec, data, self.result("partition"), self.result("fit"), self.result("select"))
        if name == "report":
            import numpy, scipy
            outcome = self.result("evaluate" if self.spec.design == "prediction" else "compare")
            # Exclude row-level observations from the summary; the evaluate
            # artifact retains them for independent recomputation.
            metrics = {key: value for key, value in outcome.items() if key not in {"observed", "predicted", "indices", "evidence_ref"}}
            return {"schema_version": "tabular_report_v1", "complete": True, "experiment_id": self.meta["id"],
                    "spec": self.spec.to_dict(), "protocol": self.spec.protocol(), "data_sha256": self.meta["data_sha256"],
                    "plan_hash": digest(self.plan.to_dict()), "draft_hash": self.confirmation,
                    "sample": self.meta["validation"], "metrics": metrics,
                    "scientific_success": None, "execution_success": True,
                    "interpretation": "报告为已声明设计下的探索性比较；显著性不证明因果，也不证明假设为真。" if self.spec.design != "prediction"
                                      else "按验证集选择后冻结；测试结果不用于更改特征、模型或参数。",
                    "limitations": ["来源、独立性和随机化由用户声明，未通过列检查验证",
                                    "未进行事先功效/样本量计算；小样本、异常值或依赖结构会限制推断",
                                    "当前不支持多因素、聚类、时间序列、多重比较或自动超参数搜索"],
                    "versions": {"python": platform.python_version(), "numpy": numpy.__version__, "scipy": scipy.__version__},
                    "artifacts": {key: value["ref"] for key, value in self.meta["completed"].items()}}
        raise ValueError("Unregistered plan node")

    def run(self, *, max_steps=None):
        if self.done:
            return self.report()
        if self.meta["confirmed"] != self.confirmation or self.meta["phase"] == "cancelled":
            raise ValueError("请先确认当前表格实验草案")
        if max_steps is not None and (type(max_steps) is not int or max_steps < 1):
            raise ValueError("max_steps 必须为正整数")
        self.check_identity()
        self.meta.update(phase="running", error=None)
        self.save()
        steps = 0
        try:
            for node in self.plan.nodes:
                if node["id"] in self.meta["completed"]:
                    self.result(node["id"])
                    continue
                if self.parent.cancel_requested.is_set() or self.parent.pause_requested.is_set():
                    self.meta["phase"] = "cancelled" if self.parent.cancel_requested.is_set() else "paused"
                    break
                if max_steps is not None and steps >= max_steps:
                    self.meta["phase"] = "paused"
                    break
                key = f"tabular_{self.meta['id']}_{node['id']}"
                result = self.parent._execute_tool(node["tool"], {"node_id": node["id"]},
                                                  {"tabular_experiment": self}, key)
                ref = f"nodes/{node['id']}.json"
                write_json(self.folder/ref, result)
                self.meta["completed"][node["id"]] = {"ref": ref, "sha256": digest(result)}
                self.save()
                self.parent.emit("tabular_step", {"experiment_id": self.meta["id"], "node": node["id"], "result_ref": ref})
                steps += 1
            else:
                self.meta.update(phase="complete", report_ref="nodes/report.json")
                report = self.report()
                write_json(self.folder/"report.json", report)
                (self.folder/"report.md").write_text(
                    "# 表格实验报告\n\n"+self.spec.research_question+"\n\n"+report["interpretation"]+
                    "\n\n```json\n"+json.dumps(report, ensure_ascii=False, indent=2)+"\n```\n", encoding="utf-8")
        except Exception as exc:
            self.meta.update(phase="paused", error={"type": type(exc).__name__, "detail": str(exc)[:300]})
            raise
        finally:
            self.save()
        return self.report()


def register_tabular(registry):
    from .contracts import ToolSpec
    from .experiment import SPEC_SCHEMA
    from .registry import _workspace, _relative

    def inspect(arguments, context):
        workspace = _workspace(context)
        path = _relative(workspace, arguments["path"])
        if path not in context.get("allowed_paths", ()):
            raise ValueError("CSV 未被用户显式选择")
        result = tabular.inspect_csv(workspace, path)
        context.setdefault("csv_evidence", {})[path] = result
        return result

    def prepare(arguments, context):
        spec = ExperimentSpec.from_dict(arguments)
        evidence = context.get("csv_evidence", {}).get(spec.data_path)
        if not evidence:
            raise ValueError("请先 csv_inspect 检查当前显式选择的 CSV")
        callback = context.get("prepare_tabular")
        if not callable(callback):
            raise ValueError("本轮没有准备实验的权限")
        return callback(spec, evidence)

    registry.register(ToolSpec("csv_inspect", "Inspect an explicitly selected UTF-8 comma CSV: column names, types, missing counts, small categorical levels and data hash. No raw numeric observations or summary means. Does not fit or run an experiment.",
        {"type": "object", "properties": {"path": {"type": "string", "minLength": 1, "maxLength": 2048}},
         "required": ["path"], "additionalProperties": False}, domain="tabular", resource_estimate={"max_bytes": 131072, "max_rows": 20000}), inspect)
    registry.register(ToolSpec("prepare_tabular_experiment", "Prepare a reviewable G2 experiment draft from inspected CSV. Independent groups use Welch; paired groups match by unit ID; prediction compares mean/OLS on fixed 60/20/20 split. Requires explicitly declared provenance, unit and sample basis; never invent these. No execution before confirmation. No unregistered parameters, categorical predictors, causal claims or time/cluster designs.",
        SPEC_SCHEMA, domain="tabular", read_only=False, preconditions=("csv_inspected", "explicit_scientific_declarations")), prepare)
    for name in ("compare", "partition", "fit", "select", "evaluate", "report"):
        tool = "tabular_"+name
        def execute(arguments, context, tool=tool):
            experiment = context.get("tabular_experiment")
            if not isinstance(experiment, TabularExperiment):
                raise ValueError("Tabular execution requires a host-confirmed plan")
            return experiment.execute_node(tool, arguments)
        registry.register(ToolSpec(tool, "Execute one host-confirmed G2 plan node; unavailable to conversational tool selection.",
            {"type": "object", "properties": {"node_id": {"type": "string", "enum": [name]}},
             "required": ["node_id"], "additionalProperties": False}, domain="tabular_execution", read_only=False,
             preconditions=("confirmed_plan", "committed_dependencies")), execute)
