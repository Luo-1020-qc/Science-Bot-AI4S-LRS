"""Saved local acceptance session, synthetic research only, no model API."""
import json
from pathlib import Path
import sys
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
sys.dont_write_bytecode = True
from rut_science.science_bot.general.conversation import GeneralSession


def main():
    if (HERE/"entry_acceptance.json").exists():
        raise ValueError("Acceptance record already exists; never silently replace it")
    project = HERE/"acceptance_project"
    project.mkdir(exist_ok=True)
    with patch("rut_science.science_bot.general.provider.load_api_config", side_effect=AssertionError("No API during research acceptance")):
        session = GeneralSession.create(HERE/"acceptance_sessions", backend="api", workspace=project)
        items = []
        for command in ("/research", "/doe demo", "/research simulate g2_2 --policy bc --seed 37",
                        "/research compare g2_3 --seed 37", "/research results g2_3", "/doe recheck", "/doe review-export"):
            response = session.message(command)
            if response.get("research_error"):
                raise ValueError(response["answer"])
            items.append({"command": command, "intent": response["intent"], "result_ref": response.get("result_ref"),
                          "execution_authorized": response.get("execution_authorized", False)})
        before = session.resources()
        restored = GeneralSession.restore(session.folder, workspace=project)
        restored.message("/research results g2_3")
        if restored.resources() != before:
            raise ValueError("Saved-result replay spent additional resources")
        blocked = []
        for operation in (lambda: restored.confirm(None), lambda: restored.run()):
            try:
                operation()
            except ValueError:
                blocked.append(True)
        result = {"version": "research_online_entry_acceptance_v1", "date": "2026-10-27", "passed": len(blocked) == 2,
            "session": str(restored.folder.relative_to(HERE)), "backend": "api", "model_requests_used": before["llm_requests"],
            "resources": before, "commands": items, "restore_and_replay_no_extra_spend": True,
            "confirm_and_resume_blocked": len(blocked) == 2, "doe_result_survives_study_switch": restored.status()["research"]["doe"]["ready_for_review"],
            "real_tool_executions": 0, "real_gpu_jobs": 0, "formal_training_transitions": 0}
        (HERE/"entry_acceptance.json").write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
        print(json.dumps({"passed": result["passed"], "commands": len(items), "model_requests_used": result["model_requests_used"], "session": result["session"]}))


if __name__ == "__main__":
    main()
