"""Read-only research bridge. One fixed action in one isolated process."""
import hashlib
import json
import os
from pathlib import Path
import sys

HUB = Path(__file__).resolve().parent
STUDIES = ("g2_2", "g2_3", "g2_4")
sys.dont_write_bytecode = True


def strict(text):
    def pairs(items):
        out = {}
        for k, v in items:
            if k in out:
                raise ValueError("Duplicate JSON key")
            out[k] = v
        return out
    def invalid(_):
        raise ValueError("Nonfinite JSON")
    return json.loads(text, object_pairs_hook=pairs, parse_constant=invalid)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def filehash(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1048576), b""):
            h.update(block)
    return h.hexdigest()


def read(folder, relative):
    path = folder/relative
    if path.resolve() != path or not path.is_relative_to(folder) or path.stat().st_size > 8*1024*1024:
        raise ValueError("Invalid fixed artifact")
    return strict(path.read_text(encoding="utf-8"))


def install_guard():
    def audit(event, args):
        if event.startswith("socket.") or event in {"subprocess.Popen", "os.system", "os.startfile", "os.posix_spawn", "os.exec", "os.spawn"}:
            raise PermissionError("Research bridge has no network or process tools")
        if event == "import" and str(args[0]).split(".")[0] in {"rut_science", "dynamic_cvit"}:
            raise PermissionError("Live Agent/CViT imports forbidden in the research worker")
        if event == "open":
            path, mode, flags = args
            if (isinstance(mode, str) and any(c in mode for c in "wax+")) or (
                    isinstance(flags, int) and flags & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND)):
                raise PermissionError("Read-only research worker")
            if isinstance(path, (str, bytes)) and Path(os.fsdecode(path)).name.casefold() == "api_key_agent.json":
                raise PermissionError("Research worker cannot read credentials")
        if event in {"os.mkdir", "os.remove", "os.rmdir", "os.rename", "os.replace", "os.chmod", "os.utime", "os.truncate", "os.link", "os.symlink"}:
            raise PermissionError("Read-only research worker")
    sys.addaudithook(audit)


def integrity(study):
    manifest = read(HUB, "online_artifacts.json")["studies"][study]
    folder = HUB/"studies"/study
    bad = [name for name, checksum in manifest.items() if not (folder/name).is_file() or filehash(folder/name) != checksum]
    if bad:
        raise ValueError("Research artifact integrity mismatch: "+str(bad[:5]))
    return {"study": study, "passed": True, "artifacts_checked": len(manifest), "scope": "Frozen artifacts and online dependencies; does not certify expert validity"}


def results(study):
    folder = HUB/"studies"/study
    if study == "g2_2":
        value = read(folder, "evidence/benchmark.json")
        return {"historical": True, "metrics": {k: v["success_rate"] for k, v in value["heldout"].items()},
                "pending_expert_reviews": 72, "human_expert_labels": 0,
                "interpretation": "Synthetic frozen benchmark; BC is not the default interview policy"}
    if study == "g2_3":
        value = read(folder, "evidence/scoring_audit.json")
        trial = read(folder, "experiments/feedback_v2/final.json")
        return {"historical": True, "strict_public_evidence_metrics": {k: v["strict_success_rate"] for k, v in value["reports"].items()},
                "corrective_trial": trial["summary"], "interpretation": "Original rewards overcredit hidden stop reasons; use strict results, no policy promotion"}
    value = read(folder, "evidence/development_diagnostics.json")
    return {"historical": True, "development_cases": value["cases"], "matched_scripted_expectations": value["matched"],
            "pending_expert_reviews": 42, "human_expert_labels": 0, "heldout_records_scored": False,
            "interpretation": "Synthetic verifier regression diagnostics, not expert accuracy or agent performance"}


def policy_for(study, policy, seed):
    folder = HUB/"studies"/study
    if seed not in (21, 37, 59):
        raise ValueError("Only frozen seeds 21/37/59 are registered")
    if study == "g2_2":
        from lab.policies import RuleV2, BCPolicy
        if policy == "rule":
            return RuleV2(), "context_rule_v2"
        if policy != "bc":
            raise ValueError("G2.2 policies: rule / bc")
        value = read(folder, f"models/bc_seed_{seed}/policy.json")
        return BCPolicy(value), digest(value)
    from lab.adapter_v3 import SuiteRule, encode, ACTIONS_V3, FEATURES_V3, VERSION_V3
    if policy == "rule":
        return SuiteRule(), "context_rule_v3"
    if policy not in ("bc", "bc_ppo", "ppo_scratch", "feedback_baseline", "feedback_ppo"):
        raise ValueError("Unknown frozen experimental policy")
    path = (f"experiments/feedback_v2/models/seed_{seed}/{'baseline' if policy == 'feedback_baseline' else 'ppo'}.json"
            if policy.startswith("feedback_") else f"models/seed_{seed}/{policy}/policy.json")
    value = read(folder, path)
    if value["version"] != VERSION_V3 or value["actions"] != list(ACTIONS_V3) or value["features"] != list(FEATURES_V3):
        raise ValueError("Frozen network protocol mismatch")
    import numpy as np
    weights = {k: np.asarray(v, dtype=np.float32) for k, v in value["parameters"].items()}
    if any(not np.isfinite(v).all() for v in weights.values()):
        raise ValueError("Nonfinite network weights")
    class FrozenCPUActor:
        def choose(self, observation):
            x = np.asarray(encode(observation), dtype=np.float32)
            for layer in ("body.0", "body.2"):
                x = np.tanh(weights[layer+".weight"]@x+weights[layer+".bias"])
            logits = weights["actor.weight"]@x+weights["actor.bias"]
            return ACTIONS_V3[int(np.argmax(np.where(observation["mask"], logits, -np.inf)))]
    return FrozenCPUActor(), digest(value)


def simulate(study, payload):
    if study not in {"g2_2", "g2_3"}:
        raise ValueError("Policy simulation exists only for G2.2/G2.3")
    folder = HUB/"studies"/study
    domain = payload.get("domain", "tabular" if study == "g2_2" else "cvit")
    if domain not in ("tabular", "cvit") or study == "g2_2" and domain != "tabular":
        raise ValueError("Unsupported simulation domain")
    bank = "bank/development.jsonl" if study == "g2_2" else "bank_v3/development.jsonl"
    tasks = [strict(line) for line in (folder/bank).read_text(encoding="utf-8").splitlines() if line]
    tasks = [task for task in tasks if task.get("domain", "tabular") == domain]
    scenario = payload.get("scenario") or ("ordinary_comparison" if domain == "tabular" else "existing_running")
    available = sorted({task["scenario"] for task in tasks})
    selected = [task for task in tasks if task["scenario"] == scenario]
    if not selected:
        raise ValueError("Unknown development scenario; choose: "+", ".join(available))
    task = selected[0]
    policy, identity = policy_for(study, payload.get("policy", "rule"), payload.get("seed", 21))
    if study == "g2_2":
        from lab.benchmark import rollout
        row = rollout(policy, task)
        return {"policy_hash": identity, "policy": payload.get("policy", "rule"), "domain": domain, "scenario": scenario,
            "split": "development", "decisions": row["decisions"], "success": row["success"], "actions": [s["action"] for s in row["trace"]],
            "trace": row["trace"], "mock_launches": row["simulated_executions"], "metric": None, "state_restore_checked": False}
    from lab.adapter_v3 import SuiteEnvironment
    from lab.reporting_v3 import stop_evidence
    from lab.cvit_mock import CViTMockEnvironment
    env = SuiteEnvironment(task, record=True)
    observation = env.reset()
    restored = False
    while not env.inner.done:
        action = policy.choose(observation)
        observation, _, done, info = env.step(action)
        if domain == "cvit" and env.inner.state["reconciled"] and not done and not restored:
            snapshot = env.inner.snapshot()
            env.inner = CViTMockEnvironment.restore(snapshot)
            observation = env.wrap(env.inner.observe())
            restored = True
        if len(env.trace) > 40:
            raise ValueError("Simulation decision limit")
    strict_success = bool(info["success"] and (env.trace[-1]["action"] != "stop" or stop_evidence(env.trace[-1]["observation"])))
    return {"policy_hash": identity, "policy": payload.get("policy", "rule"), "domain": domain, "scenario": scenario,
        "split": "development", "decisions": len(env.trace), "success": strict_success, "legacy_success": info["success"],
        "score": "public_evidence_strict", "actions": [s["action"] for s in env.trace], "trace": env.trace,
        "mock_launches": env.inner.state.get("launches", env.inner.state.get("simulated_executions", 0)),
        "metric": None, "state_restore_checked": restored}


def validate_doe(contract, request):
    from doe.validation import validate
    try:
        return validate(contract, request)
    except (ValueError, ArithmeticError) as exc:
        # Frozen SciPy diagnostics can produce non-finite tails at extreme
        # noncentralities. Never emit NaN or turn a numerical failure into a pass.
        return {"schema_version": "doe_online_validation_failure_v1", "ready_for_review": False,
            "checks": [{"code": "numerical_or_protocol_failure", "status": "blocked", "detail": str(exc)[:200]}],
            "diagnostics": None, "execution_authorized": False, "scientific_success": None, "expert_calibrated": False}


def execute(payload):
    if type(payload) is not dict or set(payload)-{"action", "study", "policy", "seed", "domain", "scenario", "contract", "request", "records", "family"}:
        raise ValueError("Closed research request required")
    study, action = payload.get("study"), payload.get("action")
    if study not in STUDIES:
        raise ValueError("Unknown registered research study")
    verified = integrity(study)
    sys.path.insert(0, str(HUB/"studies"/study))
    if action == "verify":
        return verified
    if action == "results":
        return results(study)
    if action == "simulate":
        return simulate(study, payload)
    if action == "compare":
        policies = ("rule", "bc") if study == "g2_2" else ("rule", "bc", "bc_ppo", "ppo_scratch", "feedback_baseline", "feedback_ppo")
        return {"comparisons": [{k: v for k, v in simulate(study, {**payload, "policy": policy}).items() if k != "trace"} for policy in policies],
                "interpretation": "Single development scenario comparison; no heldout evaluation or model selection"}
    if study == "g2_2" and action == "review-queue":
        path = HUB/"studies/g2_2/review/pending.jsonl"
        return {"records": [strict(line) for line in path.read_text(encoding="utf-8").splitlines() if line], "human_expert_labels": 0, "status": "pending"}
    if study == "g2_2" and action == "review-import":
        from lab.review import validate_reviews
        return {"records": validate_reviews(payload["records"]), "automatic_training": False,
                "expert_identity_independently_verified": False, "live_policy_promotion": False}
    if study != "g2_4":
        raise ValueError("Action is not registered for this study")
    if action in {"template", "demo"}:
        from doe.tasks import base_contract
        from doe.validation import validate
        from copy import deepcopy
        family = payload.get("family", "factorial_2x2")
        if family not in ("crd_two_arm", "rcbd_two_arm", "factorial_2x2"):
            raise ValueError("Only the three registered DOE families can be compiled")
        request, contract = base_contract(family, 73)
        value = {"request": request, "contract": contract, "synthetic_template": True, "validation": validate(contract, request)}
        if action == "demo":
            broken = deepcopy(contract); broken["analysis"]["model"] = "two_arm" if family != "crd_two_arm" else "full_factorial"
            value["initial_validation"] = validate(broken, request)
            value["scripted_repair"] = True
        return value
    if action == "validate":
        return {"request": payload["request"], "contract": payload["contract"], "validation": validate_doe(payload["contract"], payload["request"])}
    if action == "review-queue":
        from doe.review import queue_records
        return {"records": queue_records(), "human_expert_labels": 0, "status": "pending"}
    if action == "review-import":
        from doe.review import validate_reviews
        return {"records": validate_reviews(payload["records"]), "automatic_training": False,
                "expert_identity_independently_verified": False, "live_policy_promotion": False}
    raise ValueError("Research action unavailable; no training, shell, or live execution endpoint")


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")
    install_guard()
    try:
        raw = sys.stdin.read(512001)
        if len(raw) > 512000:
            raise ValueError("Research input too large")
        value = execute(strict(raw))
        print(json.dumps({"ok": True, "result": value, "real_tool_executions": 0, "real_model_requests": 0,
            "real_gpu_jobs": 0, "formal_training_transitions": 0}, ensure_ascii=False, allow_nan=False))
    except Exception as exc:
        print(json.dumps({"ok": False, "error_type": type(exc).__name__, "error": str(exc)[:1200]}, ensure_ascii=False))
        raise SystemExit(1)
