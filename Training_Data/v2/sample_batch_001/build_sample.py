"""Build an executable synthetic extension without modifying frozen v2 data."""
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(HERE.parent))
from protocol import VERSION, digest, sha, write, read_tasks, ACTION_IDS, expected_reward
from build_dataset import task_for, reference_episode
from expert_import import import_tasks
from preflight import preflight


def main():
    if (HERE/"tasks.jsonl").exists():
        raise ValueError("Sample already exists; validate it or create a new batch version")
    now = datetime.now(timezone.utc).isoformat()
    tasks = [task_for("darcy", "wrong_model", "train", 101),
             task_for("cvit", "wrong_model", "train", 102),
             task_for("cvit", "none", "train", 103, unknown=True)]
    requests = [
        "在同一批声明为独立的数据实现区组内，比较mean_field与ridge_field的测试relative_l2；候选减基线，越低越好。预设实际意义阈值0.01，规划效应0.02，合成标准差0.02。检查草案是否遗漏区组，修订后重新复核、冻结，再运行模拟并评估证据。只使用离线工具；不宣称真实Darcy实验或跨来源泛化。",
        "设计CViT架构baseline_small/candidate_small与学习率0.0001/0.0003的2×2区组实验，保留交互项，主要检验架构效应；以独立训练运行为单位，数据实现为区组，主要响应为测试relative_l2。检查错误模型，修订、复核并完成模拟闭环；阴性结果也应如实报告。不执行真实CViT训练。",
        "为相同CViT架构×学习率研究规划功效并给出可复核方案。目前没有sigma和方差来源；先询问依据。此示例用户无法补充，禁止把模板默认值当成先导证据；在当前有界环境中有依据地停止并记录缺失信息。不得虚构样本量已经充分。"
    ]
    for index, task in enumerate(tasks):
        task["task_id"] = ("sample001_darcy_block_repair_v1", "sample001_cvit_interaction_repair_v1", "sample001_cvit_variance_unavailable_v1")[index]
        task["public"]["user_request"] = requests[index]
        task["expert_review"] = {"status": "approved", "reviewer": "automated_synthetic_fixture_author_NOT_A_HUMAN_EXPERT",
            "reason": "Approved only as an explicitly synthetic protocol/training fixture. No human scientific approval; sigma/effect/budget are illustrative assumptions. Reuses source_A template lineage; no independent scientific dataset added.",
            "reviewed_at": now}
    write(HERE/"tasks.jsonl", tasks, lines=True, fresh=True)
    for task in tasks:
        write(HERE/"tasks"/(task["task_id"]+".json"), task, fresh=True)
    imported = import_tasks(tasks, HERE/"tasks_imported.json")
    certificate = preflight(HERE/"tasks_imported.json")
    if not certificate["passed"]: raise ValueError("Sample preflight failed")
    loaded = read_tasks("train", purpose="ppo", extension=HERE/"tasks_imported.json")
    assert {t["task_id"] for t in tasks}.issubset({t["task_id"] for t in loaded})
    episodes = [reference_episode(task) for task in tasks]
    labels, pending = [], []
    for ep in episodes:
        milestones = set()
        for step in ep["steps"]:
            assert abs(step["reward"]-expected_reward(step, milestones)) < 1e-9
            labels.append({"task_id": ep["task_id"], "episode_id": ep["episode_id"], "decision_index": step["decision_index"],
                "observation_hash": step["observation_hash"], "features": step["features"], "action_mask": step["action_mask"],
                "target_action_index": step["action_index"], "target_tool_call": step["action"],
                "source": "scripted_reference_not_expert", "review_status": "pending"})
        first = ep["steps"][0]
        pending.append({"schema_version": "expert_decision_review_v2", "review_id": digest([ep["episode_id"], 0, first["observation_hash"]]),
            "task_id": ep["task_id"], "policy_split": "train", "episode_id": ep["episode_id"], "decision_index": 0,
            "observation": deepcopy(first["observation"]), "observation_hash": first["observation_hash"], "proposed_action_index": first["action_index"],
            "review": {"status": "pending", "acceptable_action_ids": [], "rejected_action_ids": [], "reason": None, "reviewer": None, "reviewed_at": None}})
    write(HERE/"reference_episodes.jsonl", episodes, lines=True, fresh=True)
    write(HERE/"bc_reference.jsonl", labels, lines=True, fresh=True)
    write(HERE/"decisions_pending.jsonl", pending, lines=True, fresh=True)
    for task, episode in zip(tasks, episodes):
        write(HERE/"examples"/(task["task_id"]+".json"), {"task": task, "episode": episode}, fresh=True)
    artifacts = [p for p in HERE.rglob("*.json*") if p.is_file()]
    manifest = {"version": VERSION, "batch_id": "sample_batch_001", "tasks": len(tasks),
        "reference_decisions": sum(len(ep["steps"]) for ep in episodes), "bc_scripted_labels": len(labels),
        "human_expert_labels": 0, "task_approval_scope": "automated_synthetic_fixture_compatibility_only",
        "real_scientific_data_added": False, "independent_source_count_added": 0,
        "shared_lineage": "synthetic_darcy_source_A; intentionally shares the existing training template ancestry",
        "blind_test_tasks_added": 0, "all_examples_public": True,
        "reference_traces_are_ppo_rollouts": False,
        "decisions_pending_import_status": "Batch-local new states: current global decision importer does not register these IDs; requires explicit queue extension before human label import",
        "import_result": imported, "preflight_passed": True,
        "artifact_sha256": {p.relative_to(HERE).as_posix(): sha(p) for p in artifacts}}
    write(HERE/"manifest.json", manifest, fresh=True)
    print({"tasks": len(tasks), "reference_decisions": manifest["reference_decisions"], "preflight_passed": True, "human_expert_labels": 0})


if __name__ == "__main__": main()
