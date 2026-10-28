"""Validate the single Agent configuration; optional one-request live check.

No credentials or provider response bodies are printed or copied to artifacts.
"""
import argparse
import hashlib
from pathlib import Path

from rut_science.agents import JSONHTTPAgent, ModelServiceError
from rut_science.budget import RunBudget, RunLimitError
from rut_science.configuration import DEFAULT_API_CONFIG, load_api_config
from rut_science.contracts import SYSTEM_PROMPT
from rut_science.util import digest, write_json


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model")
    parser.add_argument("--live", action="store_true", help="Issue exactly one bounded model request")
    parser.add_argument("--output", type=Path, default=Path("outputs/agent_api_config_check_v031.json"))
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error("Select a new output path to preserve prior checks")
    before = hashlib.sha256(DEFAULT_API_CONFIG.read_bytes()).hexdigest()
    config = load_api_config()
    model = args.model or config["model"]
    result = {"status": "passed", "api_config_file": DEFAULT_API_CONFIG.name, "endpoint": config["endpoint"],
              "model": model, "credential_present": bool(config["api_key"]), "live_check": args.live}
    if args.live:
        if not model:
            parser.error("--model is required when API_key_Agent.json has no model field")
        budget = RunBudget(max_requests=1, max_tokens=5000, max_context_bytes=8000)
        # Direct adapter construction exercises its default credential file path.
        agent = JSONHTTPAgent(config["endpoint"], model, budget=budget)
        agent.reset(SYSTEM_PROMPT, [], 0)
        try:
            reply = agent.step([{"role": "user", "content": '无需科研写入或工具调用。请回复一个 message 动作 JSON，type 必须为 message，content 为“连接检查完成”，response_mode 为 answer。'}])
            valid = isinstance(reply, dict) and reply.get("type") == "message" and bool(reply.get("content"))
            result.update(status="passed" if valid else "failed", actual_model=agent.actual_model,
                          connectivity_passed=all(c.get("status") == "ok" for c in agent.call_records),
                          decision_type=reply.get("type") if isinstance(reply, dict) else None,
                          response_schema_valid=valid, tokens=agent.usage,
                          request_hash_verified=all(digest(c["request_body"]) == c["request_body_hash"] for c in agent.call_records))
        except (ModelServiceError, RunLimitError) as exc:
            result.update(status="failed", error=str(exc))
        usage = budget.snapshot()
        result.update(requests=usage["requests"], unresolved_token_reservations=usage["unresolved_token_reservations"])
    result["credential_file_unchanged"] = hashlib.sha256(DEFAULT_API_CONFIG.read_bytes()).hexdigest() == before
    if not result["credential_file_unchanged"]:
        result["status"] = "failed"
    write_json(args.output, result)
    print(f"{result['api_config_file']}: {result['status']}; live={args.live}; requests={result.get('requests', 0)}")
    return 0 if result["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
