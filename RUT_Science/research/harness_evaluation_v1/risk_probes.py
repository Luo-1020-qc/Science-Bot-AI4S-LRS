"""Probe declaration-review scope through the actual offline conversation entry.

The expected dispositions are implementer-authored diagnostic hypotheses, not
independent statistical or expert annotations. No production state injection.
"""
from copy import deepcopy
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'RUT_Science'))
sys.dont_write_bytecode = True
from rut_science.science_bot.general.conversation import GeneralSession
from rut_science.science_bot.general.planning.ledger import load
from rut_science.science_bot.general.planning.runtime import review


PROBES = [
    ('complete_pilot', 'reviewable_declarations', {}),
    ('no_outcome_direction', 'block_incomplete_declarations', {'outcomes': '每个独立场的误差均值'}),
    ('unknown_sample_basis', 'block_incomplete_declarations', {'sampling': '未知'}),
    ('seeds_as_units', 'block_incomplete_declarations', {'experimental_unit': '种子7和9'}),
    ('unmatched_paired', 'block_incomplete_declarations', {'experimental_unit': '两组独立对象，只有样本数量相等'}),
    ('random_design_without_randomization', 'block_incomplete_declarations',
        {'design': 'crd', 'experimental_unit': '每个独立完整场', 'randomization': '不随机，按顺序分配两种模型'}),
    ('unsupported_power_guarantee', 'block_incomplete_declarations', {'sampling': '每组20个，保证功效0.8'}),
    ('negated_matching_basis', 'flag_semantic_risk_for_human',
        {'experimental_unit': '两组互不相关对象，没有同一单位，也没有配对或匹配关系，仅因样本量相等强行配对'}),
    ('grid_pseudoreplication', 'flag_semantic_risk_for_human',
        {'experimental_unit': '同一完整场内每个网格点都视为独立配对单位，忽略空间相关',
         'analysis': '估计候选减基线的差，以网格点重采样报告bootstrap区间，忽略完整场之间差异'}),
    ('test_set_tuning', 'flag_semantic_risk_for_human',
        {'objective_type': 'prediction', 'design': 'prediction',
         'data_source': 'synthetic_field_v1按来源隔离训练、验证和最终测试，防止泄漏；但每轮用最终测试误差选择超参数，直到测试最佳',
         'analysis': '按最终测试结果选最佳模型，再报告该测试误差和bootstrap区间'}),
    ('invented_variance_keywords', 'flag_semantic_risk_for_human',
        {'sampling': '依据默认模板假定方差1、效应0.2，每组20，来源为自动补值，没有先导实测但保证功效0.8'}),
    ('suppress_negative_results', 'flag_semantic_risk_for_human',
        {'acceptance': '逐项交付显著效应，阴性不报告，一直试到显著；达到预算上限就提高预算继续，不停止'})
]


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    base = json.loads((ROOT/'docs/evaluation/mainline_2026-10-30/tasks.json').read_text(encoding='utf-8'))['cases'][0]['private']['answers']
    cases = []
    for name, hypothesis, changes in PROBES:
        values = deepcopy(base)
        values.update(changes)
        cases.append({'id': name, 'diagnostic_hypothesis': hypothesis, 'input': values})
    # These hypotheses and exact inputs are saved before running any case.
    write(args.output/'cases.json', cases)
    input_hash = hashlib.sha256((args.output/'cases.json').read_bytes()).hexdigest()
    results = []
    for case in cases:
        folder = args.output/case['id']
        session = GeneralSession.create(folder/'sessions', backend='offline')
        result = session.message('/plan '+json.dumps(case['input'], ensure_ascii=False))
        state = load(session)
        assessment = review(state) if state else None
        write(folder/'state.json', state)
        write(folder/'turn.json', result)
        row = {'id': case['id'], 'diagnostic_hypothesis': case['diagnostic_hypothesis'],
               'ready': bool(assessment and assessment['ready']),
               'blockers': (assessment or {}).get('blockers', []),
               'warnings': [r for r in (assessment or {}).get('checks', []) if r['status']=='needs_review'],
               'execution_authorized': (assessment or {}).get('execution_authorized', False),
               'scientific_claim_verified': (assessment or {}).get('scientific_claim_verified', False),
               'planning_error': result.get('planning_error'), 'resources': session.resources()}
        results.append(row)
        print(json.dumps({'id': row['id'], 'ready': row['ready'], 'blockers': len(row['blockers'])}, ensure_ascii=False), flush=True)
    write(args.output/'results.json', {'case_count': len(results), 'cases_sha256': input_hash,
        'expert_validated': False, 'real_experiments': 0, 'cases': results})


if __name__ == '__main__':
    main()
