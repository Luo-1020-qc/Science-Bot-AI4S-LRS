"""G1 routing and tool-boundary checks, using real temporary project files."""
import hashlib
from pathlib import Path
import tempfile
import unittest

from rut_science.science_bot.general.contracts import ToolSpec
from rut_science.science_bot.general.registry import ToolRegistry
from rut_science.science_bot.general.router import route_request
from rut_science.science_bot.workspace import Workspace


class GeneralToolTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.root = self.base/"project"
        self.root.mkdir()
        (self.root/"model.py").write_bytes("第一行\nsecond = 2\nthird = 3\n".encode("utf-8"))
        (self.root/"README.md").write_text("# Project\nEvidence only.\n", encoding="utf-8")
        self.workspace = Workspace.open(self.root)
        self.registry = ToolRegistry()
        self.context = {"workspace": self.workspace, "allowed_paths": {"model.py"}, "max_read_bytes": 32768}

    def test_list_metadata_does_not_authorize_file_contents(self):
        result = self.registry.execute("project_list", {}, self.context)
        self.assertEqual({item["path"] for item in result["files"]}, {"README.md", "model.py"})
        self.assertNotIn("text", str(result))
        with self.assertRaisesRegex(ValueError, "explicitly selected"):
            self.registry.execute("project_read", {"path": "README.md"}, self.context)

    def test_read_range_preserves_line_evidence_and_full_file_identity(self):
        result = self.registry.execute("project_read", {"path": "model.py", "start_line": 2, "end_line": 3}, self.context)
        self.assertEqual(result["text"], "second = 2\nthird = 3\n")
        self.assertEqual(result["line_numbers"], [2, 3])
        self.assertEqual(result["sha256"], hashlib.sha256((self.root/"model.py").read_bytes()).hexdigest())
        self.assertEqual(result["evidence_ref"], f"model.py:L2-L3#{result['sha256'][:12]}")
        self.assertEqual(self.context["remaining_read_bytes"], 32768-result["bytes"])

    def test_unknown_names_extra_keys_and_boolean_integers_are_rejected(self):
        cases = [("shell", {}), ("project_read", {"path": "model.py", "command": "run"}),
                 ("project_read", {"path": "model.py", "start_line": True}),
                 ("project_list", {"limit": "4"}), ("project_list", {"limit": 201}),
                 ("project_read", {"path": "model.py", "start_line": 0}),
                 ("project_read", {"path": "model.py", "start_line": 3, "end_line": 1})]
        for name, arguments in cases:
            with self.subTest(name=name, arguments=arguments), self.assertRaises(ValueError):
                self.registry.execute(name, arguments, self.context)

    def test_total_context_budget_is_enforced_before_disclosure(self):
        context = {**self.context, "max_read_bytes": 11}
        first = self.registry.execute("project_read", {"path": "model.py", "start_line": 2, "end_line": 2}, context)
        self.assertEqual(first["bytes"], 11)
        with self.assertRaisesRegex(ValueError, "byte budget"):
            self.registry.execute("project_read", {"path": "model.py", "start_line": 3, "end_line": 3}, context)
        self.assertEqual(context["remaining_read_bytes"], 0)

    def test_scope_missing_workspace_and_parent_paths_are_rejected(self):
        for context, path in [({}, "model.py"), ({"workspace": self.workspace}, "model.py"),
                              (self.context, "../project/model.py")]:
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.registry.execute("project_read", {"path": path}, context)

    def test_sensitive_binary_and_outside_files_cannot_be_selected(self):
        for name, raw in [(".env", b"secret"), ("binary.txt", b"x\x00y"), ("terminal.txt", b"\x1b[2J")]:
            (self.root/name).write_bytes(raw)
            context = {**self.context, "allowed_paths": {name}}
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.registry.execute("project_read", {"path": name}, context)
        outside = self.base/"outside.txt"
        outside.write_text("outside", encoding="utf-8")
        with self.assertRaises(ValueError):
            self.registry.execute("project_read", {"path": str(outside)}, {**self.context, "allowed_paths": {str(outside)}})

    def test_link_target_cannot_escape_workspace(self):
        outside = self.base/"outside.txt"
        outside.write_text("outside", encoding="utf-8")
        link = self.root/"linked.txt"
        try:
            link.symlink_to(outside)
        except OSError:
            self.skipTest("Windows account cannot create symlinks")
        with self.assertRaises(ValueError):
            self.registry.execute("project_read", {"path": "linked.txt"}, {**self.context, "allowed_paths": {"linked.txt"}})

    def test_third_tool_registration_uses_same_validation_and_provider_schema(self):
        spec = ToolSpec("label_length", "Count characters in a label; no filesystem access.",
                        {"type": "object", "properties": {"label": {"type": "string", "maxLength": 20}},
                         "required": ["label"], "additionalProperties": False},
                        {"type": "object", "properties": {"length": {"type": "integer"}},
                         "required": ["length"], "additionalProperties": False}, domain="utility")
        self.registry.register(spec, lambda arguments, context: {"length": len(arguments["label"])})
        self.assertEqual(self.registry.execute("label_length", {"label": "中文"}, {}), {"length": 2})
        self.assertIn("label_length", [item["function"]["name"] for item in self.registry.provider_tools()])
        with self.assertRaises(ValueError):
            self.registry.execute("label_length", {"label": "ok", "path": "model.py"}, {})
        with self.assertRaises(ValueError):
            self.registry.register(spec, lambda arguments, context: {})

    def test_numeric_preparation_is_host_authorized_and_does_not_accept_new_methods(self):
        called = []
        arguments = {"dataset": "darcy", "budget": 6, "quality_threshold": 0.15}
        context = {"numeric_dataset": "darcy", "prepare_numeric": lambda args: called.append(args) or {"status": "draft"}}
        self.assertEqual(self.registry.execute("prepare_numeric_experiment", arguments, context), {"status": "draft"})
        self.assertEqual(called, [arguments])
        for value in [dict(arguments, dataset="new"), dict(arguments, quality_threshold=0),
                      dict(arguments, budget=True), dict(arguments, method="CViT")]:
            with self.assertRaises(ValueError):
                self.registry.execute("prepare_numeric_experiment", value, context)
        with self.assertRaises(ValueError):
            self.registry.execute("prepare_numeric_experiment", arguments, {**context, "numeric_dataset": "generated"})
        self.assertEqual(len(called), 1)


class GeneralRoutingTests(unittest.TestCase):
    def assert_intent(self, intent, texts):
        for text in texts:
            with self.subTest(text=text):
                self.assertEqual(route_request(text).intent, intent)

    def test_registered_numeric_execution_and_demo_shorthand(self):
        for text, dataset in [("运行Darcy实验，预算6，门槛0.15", "darcy"),
                              ("在 generated 数据集上预测 regression_output，预算10，门槛0.20", "generated"),
                              ("Darcy pressure_field", "darcy"), ("generated regression_output", "generated"),
                              ("请运行 Darcy 压力场预测，并解释结果", "darcy"),
                              ("请帮我运行 Darcy 实验，并说明结果", "darcy"),
                              ("run a generated regression experiment and explain the result", "generated")]:
            with self.subTest(text=text):
                request = route_request(text)
                self.assertEqual(request.intent, "numeric")
                self.assertEqual(request.dataset, dataset)
                self.assertEqual(request.to_dict()["schema_version"], "general_task_v1")

    def test_explanations_and_negation_do_not_execute(self):
        self.assert_intent("chat", ["解释 Darcy 压力场预测是什么", "Darcy实验是怎么训练的？", "如何运行Darcy实验",
                                    "目前这个darcy数据是不是用于训练的", "不要运行 Darcy 实验", "Don't run generated regression",
                                    "什么是区组设计？", "你好", "Darcy budget?", "比较 Darcy 和 generated 的方法"])

    def test_unknown_and_underspecified_requests_have_no_generated_fallback(self):
        self.assert_intent("clarify", ["asdfgh", "运行一个实验", "run an iris experiment", "Darcy", "今天Darcy实验很成功",
                                       "运行 generated 和 Darcy 实验", "用其他方法运行 Darcy 实验", "用模型训练generated"])

    def test_unsupported_methods_and_future_design_are_explicit(self):
        self.assert_intent("unsupported", ["用CViT训练Darcy", "train FNO on Darcy", "用XGBoost预测 generated",
                                           "删除这个文件", "运行 CNN 模型", "用GPR预测Darcy",
                                           "只用 FNO 在 Darcy 做预测", "请用 generated 数据集做分类实验",
                                           "generated 数据集预测 temperature", "Darcy预测温度", "generated 预测多变量输出",
                                           "run generated to predict regression_output and temperature",
                                           "generated 预测 pressure_field", "运行 Darcy 实验，目标是 temperature",
                                           "运行 generated 实验，目标指标为 RMSE", "用多项式回归预测 generated",
                                           "使用二次多项式回归在 Darcy 进行预测", "用贝叶斯线性回归预测 generated"])
        self.assert_intent("design", ["为比较两种处理设计实验", "design an experiment for two treatments", "设计一个 DOE"])
        self.assertEqual(route_request("分析 mydata.csv").intent, "clarify")

    def test_numeric_protocol_overrides_do_not_silently_keep_defaults(self):
        requests = ["运行 generated 实验，alpha=0.1", "运行 Darcy 实验，feature_grid=3",
                    "运行 generated 实验，fidelity=half", "run Darcy experiment with seed 42",
                    "运行 generated 实验，task_seed=7", "运行 generated 实验，随机种子设为42",
                    "运行 Darcy 实验，训练集80%，测试集20%", "run generated with train/test=80/20",
                    "run Darcy with 80/20 split", "run Darcy using full fidelity",
                    "运行 Darcy，训练80%测试20%", "运行 generated 实验，固定随机种子为四十二",
                    "运行 generated 实验，按8:2划分", "运行 generated 实验，split=test",
                    "运行 Darcy 实验，正则化系数取0.1", "运行 generated 实验，batch_size=16",
                    "运行 Darcy 实验，{\"feature_grid\": 5}", "运行 generated 实验，tool_attempts=3",
                    "运行 Darcy 实验，只用 ridge", "运行 generated 实验，仅用 mean",
                    "run Darcy experiment using only ridge"]
        for text in requests:
            with self.subTest(text=text):
                self.assertIn(route_request(text).intent, {"clarify", "unsupported"})

    def test_documented_catalog_request_and_fixed_fields_remain_numeric(self):
        self.assert_intent("numeric", ["运行 generated 实验，使用已注册 mean/ridge 候选，预算10，门槛0.2",
                                       "运行 Darcy 实验，只用 mean/ridge",
                                       "run generated experiment, budget=10, threshold=0.2",
                                       "运行 generated 实验，compute_units=10，quality_threshold=0.2"])
        self.assertEqual(route_request("解释 Darcy 实验中 alpha=0.1 的含义").intent, "chat")

    def test_project_file_selection_and_listing(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            (root/"dynamic_cvit.py").write_text("class Model: pass\n", encoding="utf-8")
            (root/"module.py").write_text("answer = 42\n", encoding="utf-8")
            (root/"folder").mkdir()
            (root/"folder"/"my model.py").write_text("x = 1\n", encoding="utf-8")
            (root/"source file 中文.md").write_text("# title\n", encoding="utf-8")
            workspace = Workspace.open(root)
            for text, expected in [("解释 dynamic_cvit.py 的模型结构", "dynamic_cvit.py"),
                                   ('阅读 "source file 中文.md" 并总结', "source file 中文.md"),
                                   ("读取dynamic_cvit.py", "dynamic_cvit.py"),
                                   ("解释dynamic_cvit.py的结构", "dynamic_cvit.py"),
                                   ("不要训练，只解释 module.py", "module.py"),
                                   ("解释 module.py 中 alpha=0.1 的含义", "module.py"),
                                   ('请分析 "folder/my model.py"', "folder/my model.py")]:
                with self.subTest(text=text):
                    request = route_request(text, workspace)
                    self.assertEqual(request.intent, "project_qa")
                    self.assertEqual(request.input_paths, [expected])
            self.assertEqual(route_request("列出项目文件", workspace).intent, "project_qa")
            self.assertEqual(route_request("阅读项目，解释模型结构", workspace).intent, "clarify")
            self.assertEqual(route_request("总结当前项目", workspace).intent, "clarify")
            self.assertEqual(route_request("阅读 missing.py", workspace).intent, "clarify")
            self.assertEqual(route_request("阅读 dynamic_cvit.py").intent, "clarify")
            self.assertEqual(route_request("不要读取 module.py，只解释训练原理", workspace).intent, "chat")


if __name__ == "__main__":
    unittest.main()
