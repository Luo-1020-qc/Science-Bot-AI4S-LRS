"""G2 scientific validity, train/test separation and durable plan execution."""
import csv
from dataclasses import replace
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from scipy import stats

from rut_science.util import digest, write_json
from rut_science.science_bot.general.conversation import GeneralSession
from rut_science.science_bot.general.experiment import ExperimentSpec, ExecutionPlan
from rut_science.science_bot.general.adapters import tabular
from rut_science.science_bot.general.planner import authorize_spec
from rut_science.science_bot.general.router import route_request
from rut_science.science_bot.session import ScienceSession


def csv_text(columns, rows):
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(columns)
    writer.writerows(rows)
    return stream.getvalue()


class TabularG2Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.project = self.root/"project"
        self.project.mkdir()
        self.group = [[f"u{i}", "A" if i < 5 else "B", y] for i, y in enumerate([1, 2, 4, 6, 7, 4, 7, 8, 10, 13])]
        (self.project/"groups.csv").write_text(csv_text(["id", "group", "y"], self.group), encoding="utf-8")
        pairs = [[f"u{i}", level, y] for i, values in enumerate([(3, 2), (6, 4), (7, 4), (8, 4), (10, 8)])
                 for level, y in zip(["before", "after"], values)]
        (self.project/"paired.csv").write_text(csv_text(["id", "group", "y"], pairs[::-1]), encoding="utf-8")
        rng = np.random.default_rng(173)
        self.prediction = [[f"u{i}", i/7, float(2+3*i/7+rng.normal(0, .2))] for i in range(70)]
        (self.project/"prediction.csv").write_text(csv_text(["id", "x", "y"], self.prediction), encoding="utf-8")

    def spec(self, design="independent", **changes):
        values = dict(data_path="groups.csv", research_question="比较两个组的平均响应", design=design,
                      response="y", unit="id", provenance="synthetic", sampling_note="全部现有合成样本，探索性分析",
                      factor="group", levels=["A", "B"])
        if design == "paired":
            values.update(data_path="paired.csv", levels=["before", "after"])
        elif design == "prediction":
            values.update(data_path="prediction.csv", features=["x"], factor=None, levels=[])
        return ExperimentSpec(**{**values, **changes})

    def session(self, **kw):
        return GeneralSession.create(self.root/"sessions", backend="offline", planner="adaptive", workspace=self.project, **kw)

    def prepare(self, session, spec):
        result = session.message("/design "+json.dumps(spec.to_dict(), ensure_ascii=False))
        self.assertEqual(result["intent"], "tabular", result)
        self.assertTrue(result["requires_confirmation"])
        return result

    def test_csv_inspection_uses_real_hash_without_raw_numeric_values(self):
        session = self.session()
        result = session.message("检查 groups.csv 的列和缺失值")
        profile = result["profile"]
        self.assertEqual(profile["rows"], 10)
        self.assertEqual(profile["sha256"], hashlib.sha256((self.project/"groups.csv").read_bytes()).hexdigest())
        self.assertEqual(profile["columns"][1]["levels"], ["A", "B"])
        self.assertNotIn("means", profile)
        self.assertNotIn("text", profile)
        self.assertIsNone(session.tabular)
        self.assertIsNone(session.env)
        self.assertEqual(session.resources()["llm_requests"], 0)

    def test_independent_matches_scipy_welch_and_explicit_confirmation(self):
        session = self.session()
        self.prepare(session, self.spec())
        with self.assertRaises(ValueError):
            session.run()
        self.assertFalse(session.tabular.meta["completed"])
        session.confirm(session.confirmation)
        report = session.run()
        expected = stats.ttest_ind([1, 2, 4, 6, 7], [4, 7, 8, 10, 13], equal_var=False)
        self.assertAlmostEqual(report["metrics"]["p_value"], expected.pvalue, places=13)
        self.assertAlmostEqual(report["metrics"]["mean_difference"], -4.4)
        self.assertTrue(report["execution_success"])
        self.assertIsNone(report["scientific_success"])
        self.assertEqual(session.resources()["tool_attempts"], 4)

    def test_paired_matches_by_unit_not_row_position(self):
        session = self.session()
        self.prepare(session, self.spec("paired"))
        session.confirm(session.confirmation)
        report = session.run()
        expected = stats.ttest_rel([3, 6, 7, 8, 10], [2, 4, 4, 4, 8])
        self.assertAlmostEqual(report["metrics"]["p_value"], expected.pvalue)
        self.assertAlmostEqual(report["metrics"]["mean_difference"], 2.4)
        self.assertEqual(report["sample"]["units"], 5)

    def test_prediction_metrics_and_parameters_independently_recompute(self):
        session = self.session()
        self.prepare(session, self.spec("prediction"))
        session.confirm(session.confirmation)
        report = session.run()
        experiment = session.tabular
        split, model, selection, evaluation = [experiment.result(name) for name in ("partition", "fit", "select", "evaluate")]
        self.assertFalse(set(split["train"]) & set(split["test"]))
        self.assertFalse(set(split["validation"]) & set(split["test"]))
        self.assertEqual(set(split["train"]+split["validation"]+split["test"]), set(range(70)))
        x = np.asarray([row[1] for row in self.prediction])
        y = np.asarray([row[2] for row in self.prediction])
        train = split["train"]
        coef = np.linalg.lstsq(np.column_stack([np.ones(len(train)), x[train]]), y[train], rcond=None)[0]
        pred = coef[0]+coef[1]*x[split["test"]]
        expected = float(np.mean((pred-y[split["test"]])**2))
        self.assertEqual(selection["selected"], "ols")
        self.assertAlmostEqual(model["center"][0], float(x[train].mean()))
        self.assertAlmostEqual(report["metrics"]["test_mse"], expected, places=12)
        np.testing.assert_allclose(evaluation["predicted"], pred)
        self.assertEqual(report["metrics"]["test_evaluations"], 1)
        before = session.resources()
        self.assertEqual(session.run(), report)
        self.assertEqual(session.resources(), before)
        self.assertEqual(before["tool_attempts"], 7)

    def test_holdout_changes_cannot_affect_train_fit_or_validation_choice(self):
        spec = self.spec("prediction")
        text = (self.project/spec.data_path).read_text(encoding="utf-8")
        data = tabular.validate_data(spec, text)
        split = tabular.partition(spec, data)
        model = tabular.fit(spec, data, split)
        selection = tabular.select(spec, data, split, model)
        for i in split["test"]:
            data["rows"][i]["x"] = "1000000"
            data["rows"][i]["y"] = "-100000000"
        self.assertEqual(tabular.fit(spec, data, split), model)
        self.assertEqual(tabular.select(spec, data, split, model), selection)

    def test_pause_restore_resume_and_completed_report_is_read_only(self):
        session = self.session()
        self.prepare(session, self.spec("prediction"))
        session.confirm(session.confirmation)
        session.run(max_steps=2)
        self.assertEqual(session.meta["phase"], "paused")
        self.assertEqual(list(session.tabular.meta["completed"]), ["partition", "fit"])
        restored = ScienceSession.restore(session.folder, workspace=self.project)
        restored.run()
        self.assertEqual(restored.meta["phase"], "complete")
        self.assertEqual(restored.resources()["tool_attempts"], 7)
        before = {p: p.read_bytes() for p in restored.folder.rglob("*") if p.is_file()}
        restored.status(); restored.research_report(); restored.model_output("list")
        self.assertEqual(before, {p: p.read_bytes() for p in restored.folder.rglob("*") if p.is_file()})

    def test_cache_reconciles_crash_between_tool_commit_and_plan_commit(self):
        session = self.session()
        self.prepare(session, self.spec())
        session.confirm(session.confirmation)
        original = session.tabular.save
        def crash():
            if "compare" in session.tabular.meta["completed"]:
                raise OSError("simulated plan-save interruption")
            original()
        with patch.object(session.tabular, "save", side_effect=crash), self.assertRaises(OSError):
            session.run()
        self.assertEqual(session.resources()["tool_attempts"], 3)
        restored = ScienceSession.restore(session.folder)
        with patch.object(tabular, "compare", side_effect=AssertionError("must not repeat completed tool")):
            restored.run()
        self.assertEqual(restored.resources()["tool_attempts"], 4)

    def test_modified_input_or_snapshot_invalidates_confirmation(self):
        for target in ("source", "snapshot"):
            with self.subTest(target=target):
                session = self.session()
                self.prepare(session, self.spec())
                path = self.project/"groups.csv" if target == "source" else session.tabular.folder/"input.csv"
                original = path.read_bytes()
                path.write_bytes(original.replace(b"u0", b"v0"))
                with self.assertRaises(ValueError):
                    session.confirm(session.confirmation)
                self.assertFalse(session.tabular.meta["completed"])
                path.write_bytes(original)

    def test_missing_data_pairwise_drop_requires_explicit_policy(self):
        spec = self.spec("paired")
        path = self.project/spec.data_path
        path.write_text(path.read_text(encoding="utf-8").replace("before,3", "before,NA"), encoding="utf-8")
        text = path.read_text(encoding="utf-8")
        with self.assertRaises(ValueError):
            tabular.validate_data(spec, text)
        data = tabular.validate_data(replace(spec, missing_policy="drop_complete_case"), text)
        self.assertEqual(data["units"], 4)
        self.assertEqual(len(data["omitted_indices"]), 2)

    def test_duplicate_units_incomplete_pairs_extra_groups_and_non_numeric_reject(self):
        cases = [(self.spec(), [["u0", "A", 1], ["u0", "B", 2]]),
                 (self.spec("paired"), [["u0", "before", 1], ["u1", "after", 2]]),
                 (self.spec(), self.group+[["extra", "C", 4]]),
                 (self.spec(), self.group+[["extra", "A", "infinity"]]),
                 (self.spec(), self.group+[["extra", "A", "words"]])]
        for spec, rows in cases:
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                tabular.validate_data(spec, csv_text(["id", "group", "y"], rows))

    def test_malformed_csv_and_duplicate_columns_reject(self):
        for text in ("", "a,a\n1,2\n", "a,b\n1,2,3\n", "a,b\n", 'a,b\n"unclosed,1\n', "a,b\n1,2\n\n"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                tabular.parse_csv(text)

    def test_invalid_specs_and_leaky_features_reject(self):
        for changes in (dict(unit="y"), dict(levels=["A", "A"]), dict(alpha=True), dict(alpha=float("nan")),
                        dict(seed=True), dict(provenance="invented"), dict(provenance="randomized"),
                        dict(design="anova"), dict(missing_policy="mean_impute")):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.spec(**changes)
        for features in (["y"], ["id"], ["x", "x"]):
            with self.subTest(features=features), self.assertRaises(ValueError):
                self.spec("prediction", features=features)
        with self.assertRaises(ValueError):
            ExperimentSpec.from_dict({**self.spec().to_dict(), "learning_rate": .1})

    def test_plan_dependency_and_saved_identity_checks(self):
        spec = self.spec()
        plan = ExecutionPlan.build(spec, "a"*64)
        with self.assertRaises(ValueError):
            ExecutionPlan([{**plan.nodes[0], "depends_on": ["future"]}], digest(spec.to_dict()), "a"*64)
        session = self.session()
        self.prepare(session, spec)
        meta = session.tabular.meta
        meta["plan"]["nodes"][0]["tool"] = "tabular_fit"
        write_json(session.tabular.folder/"experiment.json", meta)
        with self.assertRaises(ValueError):
            ScienceSession.restore(session.folder)

    def test_tool_scope_and_execution_cannot_be_authorized_by_model(self):
        session = self.session()
        context = {"workspace": session.workspace, "allowed_paths": {"groups.csv"}}
        for tool, args in (("csv_inspect", {"path": "prediction.csv"}),
                           ("prepare_tabular_experiment", {k: v for k, v in self.spec().to_dict().items() if k != "schema_version"}),
                           ("tabular_compare", {"node_id": "compare"})):
            with self.subTest(tool=tool), self.assertRaises(ValueError):
                session.registry.execute(tool, args, context)

    def test_budget_insufficient_never_creates_draft(self):
        session = self.session(limits={"tool_calls": 3})
        result = session.message("/design "+json.dumps(self.spec("prediction").to_dict()))
        self.assertEqual(result["intent"], "clarify")
        self.assertIn("预算不足", result["answer"])
        self.assertIsNone(session.tabular)
        self.assertFalse((session.folder/"experiments").exists())

    def test_new_question_revokes_old_confirmation_and_retains_completed_report(self):
        session = self.session()
        self.prepare(session, self.spec())
        old = session.confirmation
        session.message("什么是Welch检验？")
        with self.assertRaises(ValueError):
            session.confirm(old)
        self.prepare(session, self.spec())
        session.confirm(session.confirmation)
        report = session.run()
        session.message("什么是配对设计？")
        self.assertEqual(session.research_report(), report)

    def test_cancel_cannot_resume_old_plan(self):
        session = self.session()
        self.prepare(session, self.spec())
        session.confirm(session.confirmation)
        session.cancel()
        with self.assertRaises(ValueError):
            session.run()
        self.assertFalse(session.tabular.meta["completed"])

    def test_natural_declarations_cannot_be_invented(self):
        spec = self.spec()
        for text in ("比较 groups.csv", "独立比较 groups.csv，y，id，group，A，B", "合成独立比较y id group A B"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                authorize_spec(spec, text)
        authorize_spec(spec, "合成数据，独立比较，y，id，group，A，B；全部现有合成样本，探索性分析")

    def test_route_missing_inputs_unsupported_tasks_and_legacy_numeric(self):
        session = self.session()
        self.assertEqual(route_request("分析 groups.csv", session.workspace).intent, "tabular")
        self.assertEqual(route_request("用XGBoost预测 prediction.csv", session.workspace).intent, "unsupported")
        self.assertEqual(route_request("不要分析 groups.csv", session.workspace).intent, "chat")
        self.assertEqual(route_request("分析 groups.csv").intent, "clarify")
        self.assertEqual(route_request("运行 generated 实验，预算6").intent, "numeric")
        self.assertEqual(session.message("设计一个实验")["intent"], "design")
        self.assertIsNone(session.tabular)

    def test_constant_groups_and_constant_paired_difference_fail_without_fake_p(self):
        for design, groups in (("independent", [[f"u{i}", "A" if i < 3 else "B", 1] for i in range(6)]),
                               ("paired", [[f"u{i}", level, i+offset] for i in range(4) for level, offset in (("before", 1), ("after", 2))])):
            spec = self.spec(design)
            data = tabular.validate_data(spec, csv_text(["id", "group", "y"], groups))
            with self.subTest(design=design), self.assertRaises(ValueError):
                tabular.compare(spec, data)

    def test_explicit_constraints_cannot_be_ignored_by_planner(self):
        base = "合成数据，独立比较，y，id，group，A，B；全部现有合成样本，探索性分析；"
        for addition in ("alpha=0.1", "seed=7", "drop_complete_case", "数据来自观察性研究"):
            with self.subTest(addition=addition), self.assertRaises(ValueError):
                authorize_spec(self.spec(), base+addition)
        with self.assertRaises(ValueError):
            authorize_spec(self.spec(), base.replace("id，", "patient_id，"))

    def test_scientific_free_text_followed_by_english_parameter_is_not_false_missing(self):
        spec = replace(self.spec(), sampling_note="全部现有合成样本，仅作探索性演示；未进行事先功效计算。")
        authorize_spec(spec, "独立比较，合成 synthetic，response=y，unit=id，factor=group，levels=[A,B]；"
                            "sampling_note=全部现有合成样本，仅作探索性演示；未进行事先功效计算。alpha=0.05，seed=42。")

    def test_protocol_overrides_and_unsupported_predictors_are_not_silent(self):
        session = self.session()
        for text in ("运行 prediction.csv 预测，只用 OLS", "预测 prediction.csv，训练集80%，测试集20%",
                     "预测 prediction.csv，以MAE选择模型"):
            with self.subTest(text=text):
                self.assertEqual(route_request(text, session.workspace).intent, "clarify")
        path = self.project/"prediction.csv"
        path.write_text(csv_text(["id", "x", "y"], [[f"u{i}", "category", i] for i in range(40)]), encoding="utf-8")
        with self.assertRaises(ValueError):
            tabular.validate_data(self.spec("prediction"), path.read_text(encoding="utf-8"))

    def test_pause_event_stops_at_boundary_and_resume_does_not_repeat(self):
        session = self.session()
        self.prepare(session, self.spec("prediction"))
        session.confirm(session.confirmation)
        session.event_callback = lambda event: session.pause() if event["kind"] == "tabular_step" else None
        session.run()
        self.assertEqual(session.meta["phase"], "paused")
        self.assertEqual(list(session.tabular.meta["completed"]), ["partition"])
        session.event_callback = None
        session.run()
        self.assertEqual(session.meta["phase"], "complete")
        self.assertEqual(session.resources()["tool_attempts"], 7)

    def test_committed_tool_result_and_plan_node_corruption_are_detected(self):
        session = self.session()
        self.prepare(session, self.spec())
        session.confirm(session.confirmation)
        session.run(max_steps=1)
        path = session.tabular.folder/"nodes/compare.json"
        value = json.loads(path.read_text(encoding="utf-8"))
        value["p_value"] = .00001
        write_json(path, value)
        with self.assertRaises(ValueError):
            ScienceSession.restore(session.folder).run()


if __name__ == "__main__":
    unittest.main()
