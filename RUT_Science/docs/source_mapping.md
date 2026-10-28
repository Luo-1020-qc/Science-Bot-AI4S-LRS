# Source and schema mapping

Reviewed on 2026-10-12. Primary paper: user-provided PDF, *Beyond Ideal Instruction: A Comprehensive Framework for Evaluating LLMs in Realistic Interactions*, arXiv:2606.03318v2, 28 pages. [Paper](https://arxiv.org/abs/2606.03318v2).

## Attribution

| Concept | Source location | Local representation |
|---|---|---|
| Seven behaviors | Paper §3 / Figure 1 | `contracts.BEHAVIORS` |
| Stateful environment / five gold dimensions | §4.1 | `environment`, `TaskSpec`, `GoldAction` |
| Controlled paired rewriting / no hidden IDs | §4.2–4.3 | authored two-turn `benchmark.build_dialogues` |
| Coverage AND dependencies AND terminal state | §5.2 | `evaluator.evaluate` primary metric |
| Honesty / discipline / clarification diagnostic | §5.2 / Appendix I | null, not run; response rubric is a separate extension |
| Failure priority R4, R1a/R1b, R2, R3 | Appendix J | deterministic classifier; not the original LLM classifier |
| Sealed testing, scientific recomputation, cluster bootstrap | Project proposal / framework extension | project-specific checks and analysis |

## Actual upstream fields inspected

[`eval/completion.py`](https://github.com/Miaow-Lab/RUT-Bench/blob/main/eval/completion.py) reads `runtime.tools`, `gold_action_graph`, `final_state_assertions`, `expected_state_diff`, and `forbidden_actions`. Its graph uses `required_read_equivalence_sets`, `required_write_nodes`, `precedence_edges`, `clarify_nodes`, and `refuse_nodes`. We checked argument-aware matching and state-change assertions. The inspected Git blob SHA for this file was `6bdb44508ec3c62540523ff5505215dcb222287e`.

[`eval/run_eval.py`](https://github.com/Miaow-Lab/RUT-Bench/blob/main/eval/run_eval.py) uses runtime class code/name, `init_config`, and `user_turns[].user_message`; later user turns follow an assistant response. Its summary computes a relaxed primary success rate and retains strict scores. This differs from the paper's stated three-check success definition. Local `execution_success` follows the paper-level definition with additional project constraints; `state_only_success_extension` is a diagnostic, not an exact copy of the upstream relaxed metric.

The public README specifies separate benchmark and task-blueprint files. This delivery did **not** download or execute the official dataset, pin a full upstream commit, or reproduce the reported model scores. A paper reproduction requires those steps before comparing numerical results. [Official repository](https://github.com/Miaow-Lab/RUT-Bench).

## Implementation differences

- Synthetic regression data instead of original multi-domain environments; Chinese authored dialogue fixtures instead of the original English data.
- Agent decisions use one JSON action per step; the optional HTTP adapter uses JSON mode instead of native function calling. Transport follows the provider's documented JSON chat endpoint. [DeepSeek API contract](https://api-docs.deepseek.com/api/create-chat-completion/).
- First-turn write prohibition is a declared interaction rule in every paired sample. Contradictions resolve in the second turn; unresolved cases are a separate response-only suite.
- This MVP admits one frozen split/model/evaluation and a fixed six-stage workflow. General equivalent plans, branching, asynchronous jobs and dynamic goals are future work.
- Rejected tool attempts are retained. The project uses strict tool legality: any tool error fails logical compliance, even if the final state later recovers. Successful action coverage alone does not erase a prior violation.
- The environment is an in-process deterministic container, not a security sandbox against arbitrary Python or shell code.
- Rule controllers are instrument controls, not measured LLM baselines. Five tasks are a development set, with shared synthetic datasets and no held-out generalization claim.
