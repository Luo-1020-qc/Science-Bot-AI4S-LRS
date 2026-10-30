"""Build 50 explicit synthetic scenarios without changing the frozen environment."""
from copy import deepcopy
from pathlib import Path
from datetime import datetime, timezone
import json
import sys

HERE = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(HERE.parent))
from protocol import VERSION, digest, sha, rows, write, expected_reward, read_tasks
from build_dataset import reference_episode
from expert_import import import_tasks
import preflight as preflight_module

AUTHOR = 'LLM_SYNTHETIC_CURATOR_NOT_A_HUMAN_EXPERT'
VARIANTS = [
    ('valid_null', 'none', False, None, False, 'null', '检查完整方案并如实报告零效应模拟结果'),
    ('repair_model', 'wrong_model', False, None, False, 'benefit', '修复错误分析模型，重新复核后冻结'),
    ('repair_response', 'wrong_response', False, None, False, 'harm', '将错误的 training_loss 修复为预先指定的响应，并如实报告反向结果'),
    ('repair_draft_budget', 'low_budget', False, None, False, 'null', '将初稿预算错误修复为已声明且足够的资源上限；不增加运行数'),
    ('resolve_stale_review', 'stale_review', False, None, False, 'benefit', '识别过期复核并对当前方案重新复核，不能沿用旧版复核'),
    ('variance_unavailable', 'none', True, None, False, 'null', '先询问方差来源；用户明确无法提供后引用该证据停止'),
    ('new_job_oom', 'none', False, 'mock_oom', False, 'harm', '对账确认无已有作业，启动模拟时获得 OOM 证据并停止'),
    ('reuse_job', 'none', False, None, True, 'null', '对账复用当前冻结方案的已有模拟作业，避免重复启动'),
]


def make_tasks():
    tasks, scenarios = [], []
    for domain in ('darcy', 'cvit'):
        for family in ('crd_two_arm', 'rcbd_two_arm', 'factorial_2x2'):
            variants = list(VARIANTS)
            if domain == 'darcy' and family == 'crd_two_arm':
                variants.append(('higher_score', 'none', False, None, False, 'harm', '对预先定义的负误差分数使用 higher 方向，不能颠倒效应方向'))
            if domain == 'darcy' and family == 'rcbd_two_arm':
                variants.append(('power_090', 'none', False, None, False, 'benefit', '在固定区组布局下验证 0.90 的预设名义功效目标'))
            for i, (name, fault, unknown, failure, existing, outcome, description) in enumerate(variants):
                factorial = family == 'factorial_2x2'
                first = 'predictor' if domain == 'darcy' else 'architecture'
                factors = [{'name': first, 'levels': ['baseline', 'candidate']}]
                second = 'resolution' if domain == 'darcy' else 'learning_rate'
                if factorial:
                    factors.append({'name': second, 'levels': ['32', '64'] if domain == 'darcy' else ['0.0001', '0.0003']})
                primary = (first+':'+second if i in (3,4,6) else second if i in (2,7) else first) if factorial else first
                interaction = ':' in primary
                # These are prospective toy-model assumptions, NOT estimated pilot evidence.
                # The interaction's difference-in-differences has a different variance scale.
                sigma, effect = .02, .05 if interaction else .03
                goal = {'domain': domain, 'user_request': '', 'family': family, 'factors': factors,
                    'unit_definition': ('One independently randomized synthetic predictor application on a distinct data realization' if domain == 'darcy'
                        else 'One independently seeded synthetic training run assigned to one treatment combination'),
                    'response': 'negative_relative_l2' if name == 'higher_score' else 'relative_l2',
                    'primary_term': primary, 'direction': 'higher' if name == 'higher_score' else 'lower',
                    'practical_margin': .01, 'minimum_effect': effect, 'sigma': None if unknown else sigma,
                    'variance_source': None if unknown else 'Prospectively declared synthetic Gaussian sigma=0.02; no pilot observations or empirical scientific evidence',
                    'target_power': .9 if name == 'power_090' else .8, 'resource_budget': 96 if name == 'repair_draft_budget' else 128,
                    'max_decisions': 40}
                if family != 'crd_two_arm':
                    goal['unit_definition'] += '; distinct treatment applications are grouped within declared data-realization blocks'
                goal['user_request'] = (f'仅使用离线模拟工具。研究 {domain}/{family}，主要对比为 {primary}；'
                    f'响应 {goal["response"]}，方向 {goal["direction"]}，实际意义阈值 0.01。'
                    '检查当前草案、复核版本和资源前提，必要时修正并重新复核；执行前对账，存在当前方案的作业则复用。'
                    '缺少必要信息时先提问；仅在已观察到合法阻断证据时停止。分析后按预先声明的结论规则如实报告。'
                    f'这是前瞻声明的合成模型：sigma={goal["sigma"]}，minimum_effect={effect}，功效目标 {goal["target_power"]}，'
                    '不代表真实先导数据或真实实验结论；阴性或反向结果不改变完成标准。')
                identity = f'syn050_{len(tasks)+1:03d}_{domain}_{family}_{name}_v2'
                task = {'schema_version': VERSION, 'task_id': identity, 'policy_split': 'train',
                    'root_group': 'synthetic_darcy_family_source_A',
                    'data_lineage': {'source_ancestor_ids': ['synthetic_darcy_source_A'],
                        'scientific_partitions': {k:f'mock://source_A/{k}' for k in ('train','validation','test')},
                        'source_kind': 'synthetic_reference_only'},
                    'public': goal, 'simulator': {'initial_fault': fault, 'outcome_scenario': outcome,
                        'user_variance_answer': None, 'existing_job': existing, 'job_failure': failure},
                    'expert_review': {'status':'approved', 'reviewer':AUTHOR, 'reviewed_at':datetime.now(timezone.utc).isoformat(),
                        'reason':'Synthetic fixture compatibility permission only, not human/expert scientific approval. Reuses source_A template ancestry; parameters are declared toy assumptions, no empirical variance/effect evidence. Environment preflight is independently required.'}}
                tasks.append(task)
                scenarios.append({'task_id':identity, 'description':description, 'primary_term':primary,
                    'expected_classification':'justified_stop' if unknown or failure else 'completed_mock_research_loop',
                    'expected_required_action': {'wrong_model':'model_'+{'crd_two_arm':'two_arm','rcbd_two_arm':'additive_blocks','factorial_2x2':'blocked_full_factorial'}[family],
                        'wrong_response':'repair_response','low_budget':'repair_budget','stale_review':'review'}.get(fault),
                    'requires_public_failure_evidence': bool(failure), 'requires_reuse': existing,
                    'synthetic_parameter_assumptions': {'sigma':goal['sigma'],'minimum_effect':effect,'power_target':goal['target_power']}})
    assert len(tasks)==50
    assert all(not any(word in t['public']['user_request'] for word in ('OOM','零效应模拟结果','如实报告反向结果','outcome_scenario')) for t in tasks)
    assert len({digest({'public':{k:v for k,v in t['public'].items() if k!='user_request'},'simulator':t['simulator']}) for t in tasks})==50
    return tasks, scenarios


def prepare():
    if (HERE/'manifest.json').exists(): raise ValueError('Batch sealed; verify it or create a new version')
    tasks, scenarios = make_tasks()
    write(HERE/'tasks.jsonl', tasks, lines=True, fresh=True)
    write(HERE/'scenarios.json', scenarios, fresh=True)
    (HERE/'tasks_展开注释.jsonc').write_text('// 合成任务人工审阅视图，与 tasks.jsonl 对象完全一致。\n'
        '// public：公开目标；simulator：仅宿主可见；expert_review.approved 仅指合成夹具兼容许可。\n'
        '// 不包含专家审批、真实科学数据或 PPO 行为概率。\n'+json.dumps(tasks,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    import_tasks(tasks,HERE/'tasks_imported.json')
    episodes=[]
    by_id={s['task_id']:s for s in scenarios}
    def checked_reference(task):
        ep=reference_episode(task)
        spec=by_id[task['task_id']]
        assert ep['classification']==spec['expected_classification'], 'Wrong scenario terminal'
        actions=[s['action']['action_id'] for s in ep['steps']]
        if spec['expected_required_action']: assert spec['expected_required_action'] in actions
        if task['simulator']['initial_fault']=='stale_review':
            assert not ep['steps'][0]['observation']['flags']['review_current']
            assert any(s['next_observation']['flags']['review_current'] for s in ep['steps'])
        evidence=[e for s in ep['steps'] for e in s['next_observation']['evidence']]
        if spec['requires_public_failure_evidence']: assert any(e['kind']=='mock_tool_failure' for e in evidence)
        if spec['requires_reuse']:
            assert 'run_mock' not in actions
            assert any(s['action']['action_id']=='reconcile' and s['feedback']['result'].get('reused') for s in ep['steps'])
        milestones=set()
        for s in ep['steps']: assert abs(expected_reward(s,milestones)-s['reward'])<1e-9
        episodes.append(ep)
        print(json.dumps({'task':task['task_id'],'steps':len(actions),'terminal':ep['classification']}),flush=True)
        return ep
    preflight_module.reference_episode=checked_reference
    cert=preflight_module.preflight(HERE/'tasks_imported.json')
    if not cert['passed']: raise ValueError(str([r for r in cert['reports'] if not r['passed']]))
    loaded=read_tasks('train',purpose='ppo',extension=HERE/'tasks_imported.json')
    assert {t['task_id'] for t in tasks}.issubset({t['task_id'] for t in loaded})
    write(HERE/'reference_episodes.jsonl',episodes,lines=True,fresh=True)
    labels=[{'task_id':ep['task_id'],'decision_index':s['decision_index'],'features':s['features'],
        'observation_hash':s['observation_hash'],'action_mask':s['action_mask'],'target_action_index':s['action_index'],
        'source':'scripted_reference_not_expert','human_review_status':'pending','ppo_eligible':False}
        for ep in episodes for s in ep['steps']]
    write(HERE/'bc_reference.jsonl',labels,lines=True,fresh=True)
    source=HERE.parents[2].parent/'rl_training_50_tasks'
    provenance={'original_batch_files_sha256':{p.name:sha(p) for p in source.iterdir() if p.is_file()} if source.exists() else {},
        'replacement_policy':'New versioned batch; original files untouched. Fifty supported combinations replace unsupported text-only requests.',
        'human_expert_labels':0,'new_independent_sources':0,'generator':AUTHOR}
    write(HERE/'provenance.json',provenance,fresh=True)
    from environment import ToolEnvironment
    feature_count=len({tuple(ToolEnvironment.features(None,ep['steps'][0]['observation'])) for ep in episodes})
    files=['tasks.jsonl','scenarios.json','tasks_展开注释.jsonc','tasks_imported.json','reference_episodes.jsonl','bc_reference.jsonl','provenance.json']
    manifest={'batch_version':'synthetic_batch_050_v2','tasks':50,'structurally_distinct_tasks':50,
        'public_requests_exclude_private_scenario_expectations':True,
        'distinct_initial_actor_feature_vectors':feature_count,'reference_decisions':len(labels),'human_expert_labels':0,
        'new_independent_sources':0,'all_train':True,'all_scenario_semantics_checked':True,
        'preflight_passed':True,'artifact_sha256':{f:sha(HERE/f) for f in files},
        'scope':'50 supported synthetic scenario combinations, not 50 scientific domains or independently sourced experiments'}
    write(HERE/'manifest.json',manifest,fresh=True)
    print(json.dumps(manifest,ensure_ascii=False),flush=True)


if __name__=='__main__': prepare()
