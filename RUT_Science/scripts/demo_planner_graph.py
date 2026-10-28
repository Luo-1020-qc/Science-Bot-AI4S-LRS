"""Official Graph API pattern: observable state -> policy -> tool -> observe.

Architecture control only. No learned policy or LLM-performance claim.
"""
import argparse
from dataclasses import replace
import json
from pathlib import Path
from typing import TypedDict

from langgraph.graph import START, END, StateGraph
from langgraph.checkpoint.memory import InMemorySaver
from rut_science.adaptive_workflow import SelectionDarcyEnvironment, selection_reference, score_selection_episode
from rut_science.plan_spec import public_control_plan, resolve_node, accept_result
from rut_science.research_spec import ResearchSpec
from rut_science.util import write_json


class State(TypedDict):
    completed: list[str]
    results: dict
    observation: dict
    action: str
    calls: int
    failed: bool
    trace: list[dict]


def build_graph(env, spec, choose, budget=8):
    """choose sees public observations only; it must return a legal candidate ID."""
    plan = public_control_plan(spec)
    plan.validate(spec, env.available_tools(), budget)
    nodes = {n.node_id: n for n in plan.nodes}

    def observe(state):
        ready = [n for n in plan.nodes if n.node_id not in state['completed'] and set(n.depends_on) <= set(state['completed'])]
        return {'observation': {'research_spec': spec.to_dict(), 'remaining_tool_calls': budget-state['calls'],
            'evidence': state['results'], 'candidates': [
                {'id': n.node_id, 'tool': n.tool, 'arguments': resolve_node(n, state['results'])} for n in ready]}}

    def decide(state):
        action = choose(json.loads(json.dumps(state['observation'])))
        if action not in {c['id'] for c in state['observation']['candidates']}:
            raise ValueError('Policy chose an action outside the legal candidate set')
        return {'action': action}

    def execute(state):
        node = nodes[state['action']]
        arguments = resolve_node(node, state['results'])
        result = env.invoke(node.tool, arguments)
        ok = accept_result(node, result)
        return {'calls': state['calls']+1, 'failed': not ok,
            'completed': state['completed']+[node.node_id] if ok else state['completed'],
            'results': {**state['results'], node.node_id: result},
            'trace': state['trace']+[{'node': node.node_id, 'tool': node.tool, 'arguments': arguments, 'result': result}]}

    graph = StateGraph(State)
    graph.add_node('observe', observe)
    graph.add_node('planner', decide)
    graph.add_node('execute_tool', execute)
    graph.add_edge(START, 'observe')
    graph.add_conditional_edges('observe', lambda s: END if s['failed'] or s['calls'] >= budget or not s['observation']['candidates'] else 'planner')
    graph.add_edge('planner', 'execute_tool')
    graph.add_edge('execute_tool', 'observe')
    return graph.compile(checkpointer=InMemorySaver())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', type=Path, default=Path(__file__).resolve().parents[1]/'data/darcy_cpu_v1')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--policy', choices=['first_ready', 'last_ready'], default='first_ready')
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Use a new output directory')
    spec = replace(ResearchSpec(**json.loads((args.data/'research_spec.json').read_text(encoding='utf-8-sig'))),
                   model='validation_select', max_train_calls=2)
    env = SelectionDarcyEnvironment(args.data)
    initial = env.snapshot()
    env.confirm_research_spec(spec, source='operator_config', reference='architecture_demo_fixed_spec')
    choose = lambda observation: observation['candidates'][0 if args.policy == 'first_ready' else -1]['id']
    graph = build_graph(env, spec, choose)
    result = graph.invoke({'completed': [], 'results': {}, 'observation': {}, 'action': '', 'calls': 0,
                           'failed': False, 'trace': []}, {'configurable': {'thread_id': 'architecture-demo'}, 'recursion_limit': 64})
    # Independent evaluator gets private state only after policy execution ends.
    episode = {'initial_state': initial, 'final_state': env.snapshot(), 'termination': 'completed_dialogue' if len(result['completed']) == 8 else 'incomplete',
        'events': [{'event_type': 'tool_call', 'tool_name': e['tool'], 'arguments': e['arguments'], 'tool_result': e['result']} for e in result['trace']]}
    reference = selection_reference(args.data, spec)
    score = score_selection_episode(args.data, spec, episode, reference)
    args.output.mkdir(parents=True)
    write_json(args.output/'result.json', {'policy': args.policy, 'state': result, 'score': score,
        'scope': 'architecture_control_not_RL_training_or_LLM_evaluation', 'checkpoint': 'in_memory_not_cross_process'})
    (args.output/'graph.mmd').write_text(graph.get_graph().draw_mermaid(), encoding='utf-8')
    print(json.dumps({'policy': args.policy, 'calls': result['calls'], 'scientific_success': score['execution_success'],
        'output': str(args.output)}, ensure_ascii=False))
    return 0 if score['execution_success'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
