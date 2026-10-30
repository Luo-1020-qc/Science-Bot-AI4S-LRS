"""Small, inspectable candidate ranker; it chooses fields, never scientific facts."""
import json
import math
from pathlib import Path

from .blueprint import FIELDS
from .ledger import IMPACTS

VERSION = 'question_ranker_v1'
KINDS = ('conflict', 'stale', 'proposal', 'evidence_plan', 'missing', 'refine')
PREREQUISITES = {
    'objective_type': ('research_question',), 'hypothesis': ('research_question', 'objective_type'),
    'scope': ('research_question',), 'exclusions': ('scope',), 'experimental_unit': ('scope',),
    'factors': ('objective_type',), 'outcomes': ('objective_type',), 'baseline': ('objective_type',),
    'data_source': ('scope',), 'design': ('experimental_unit', 'factors', 'objective_type'),
    'sampling': ('experimental_unit', 'design'), 'randomization': ('experimental_unit', 'design'),
    'analysis': ('design', 'outcomes'), 'acceptance': ('outcomes', 'analysis'),
    'risks': ('scope',), 'reproducibility': ('data_source',), 'deliverable': ('research_question',),
}
FEATURES = tuple('kind:'+k for k in KINDS)+tuple('field:'+f for f in FIELDS)+(
    'unresolved_prerequisites', 'affected_dependents', 'recently_asked', 'declared_fraction')
MODEL_PATH = Path(__file__).with_name('question_policy.json')


def features(state, candidate):
    field = candidate['field']
    def declared(f):
        return (state['facts'].get(f, {}).get('status') == 'declared'
                and f not in state['unknown'] and f not in state['conflicts'] and f not in state['stale'])
    missing = sum(not declared(f) for f in PREREQUISITES.get(field, ()))
    repeat = any(q['field'] == field for q in state.get('question_history', [])[-4:])
    return [float(candidate['kind'] == k) for k in KINDS]+[float(field == f) for f in FIELDS]+[
        missing/3, len(IMPACTS.get(field, ()))/5, float(repeat), sum(declared(f) for f in FIELDS)/len(FIELDS)]


def load_policy(path=MODEL_PATH):
    model = json.loads(path.read_text(encoding='utf-8'))
    weights = model.get('weights')
    if (model.get('version') != VERSION or model.get('features') != list(FEATURES)
            or model.get('training_source') != 'scripted_synthetic_not_expert'
            or not isinstance(weights, list) or len(weights) != len(FEATURES)
            or any(type(w) not in (int, float) or not math.isfinite(w) or abs(w) > 100 for w in weights)):
        raise ValueError('Question policy schema or finite weights invalid')
    return model


def score(vector, weights):
    return sum(a*b for a, b in zip(vector, weights, strict=True))
