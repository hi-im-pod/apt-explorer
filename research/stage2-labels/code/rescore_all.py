"""Recompute every score reported in the write-up from the saved outputs.

Writes data/scores.json. Run from the repository root.
"""
import json, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import harness  # noqa: E402

D = HERE.parent / 'data'
SPIKE_FIELDS = (('Victim_country', 'victim_countries'), ('Target_sector', 'target_sectors'), ('Attack_vector', 'attack_vectors'))


def paper_set(v):
    v = (v or '').strip()
    return None if not v or v.lower() in ('not mentioned', 'n/a', 'none', 'nan') else {x.strip() for x in v.split(',') if x.strip()}


def spike_scores(path, ids=None):
    rows = json.load(open(path, encoding='utf-8'))
    if ids is not None:
        rows = [r for r in rows if r['id'] in ids]
    out = {'reports': len(rows)}
    for col, key in SPIKE_FIELDS:
        pairs = [({v.upper() for v in r['out'][key]}, {v.upper() for v in paper_set(r['labels'][col])}) for r in rows if paper_set(r['labels'][col])]
        out[key] = harness.prf(pairs) | {'n': len(pairs)}
    return out


scores = {'spike_200_vs_paper': {}, 'spike_local_100_vs_paper': {}, 'standard_labels_100_vs_mapped_paper': {}, 'testset_v1_agreement': {}, 'testset_v3_vs_claude': {}}
for name in ('results.json', 'results_v2.json'):
    scores['spike_200_vs_paper'][name] = spike_scores(D / 'spike' / name)
local_ids = {r['id'] for r in json.load(open(D / 'spike' / 'results_local_qwen3.5_35b.json', encoding='utf-8'))}
for name in ('results.json', 'results_v2.json', 'results_local_qwen3_8b.json', 'results_local_qwen3_14b.json',
             'results_local_qwen3.5_35b.json', 'results_localc_qwen3.5_35b.json', 'results_localv2_qwen3.5_35b.json'):
    scores['spike_local_100_vs_paper'][name] = spike_scores(D / 'spike' / name, local_ids)

# Standard labels mapped up to the paper's categories (see docs/stage2-labels.md section 5).
sys.path.insert(0, str(HERE / 'legacy'))
std = [r for r in json.load(open(D / 'spike' / 'results_std.json', encoding='utf-8')) if r['local'] is not None]
from importlib import util
spec = util.spec_from_file_location('score_std', HERE / 'legacy' / 'score_std.py')
src = (HERE / 'legacy' / 'score_std.py').read_text(encoding='utf-8').split("print('== Against")[0].replace("res = json.load(open(sys.argv[1], encoding='utf-8'))\nres = [r for r in res if r['local'] is not None]", '')
ns = {}
exec(src, ns)
for who in ('haiku', 'local'):
    c = [(set(r[who]['victim_countries']), ns['g'](r['labels']['Victim_country'])) for r in std if ns['g'](r['labels']['Victim_country'])]
    s = [(ns['sect_up'](r[who]), ns['g'](r['labels']['Target_sector']) - {'Cloud/IoT Services'}) for r in std if ns['g'](r['labels']['Target_sector'])]
    v = [({ns['ia_fam'](t) for t in r[who]['initial_access']} - {None}, {ns['VEC_FAM'][x] for x in ns['g'](r['labels']['Attack_vector']) if x in ns['VEC_FAM']}) for r in std if ns['g'](r['labels']['Attack_vector'])]
    scores['standard_labels_100_vs_mapped_paper'][who] = {'victim_countries': harness.prf(c), 'target_sectors': harness.prf(s), 'initial_access_family': harness.prf(v)}

# Test set, v1 rules: agreement between the three labellers.
tests = json.load(open(D / 'testset.json', encoding='utf-8'))
claude1 = {json.loads(l)['id']: json.loads(l) for l in open(D / 'runs' / 'testset_claude_v1.jsonl', encoding='utf-8')}
q1 = {k: v for k, v in json.load(open(D / 'runs' / 'testset_qwen35_35b_v1.json', encoding='utf-8')).items() if v}
g1 = {k: v for k, v in json.load(open(D / 'runs' / 'testset_gemma4_12b_v1.json', encoding='utf-8')).items() if v}
ids = [t['id'] for t in tests if t['id'] in q1 and t['id'] in g1]
named = json.load(open(D / 'runs' / 'testset_named_countries.json', encoding='utf-8'))
for a, b, A, B in (('claude', 'qwen', claude1, q1), ('claude', 'gemma', claude1, g1), ('qwen', 'gemma', q1, g1)):
    scores['testset_v1_agreement'][f'{a}_vs_{b}'] = {
        f: harness.prf([(harness.parent(f, B[i][f]), harness.parent(f, A[i][f])) for i in ids])['f1'] for f in ('victim_countries', 'target_sectors', 'initial_access')}
for m, M in (('qwen', q1), ('gemma', g1)):
    scores['testset_v1_agreement'][f'{m}_grounded_countries_vs_claude'] = harness.prf(
        [(set(M[i]['victim_countries']) & set(named[i]), set(claude1[i]['victim_countries'])) for i in ids])['f1']

ref3 = harness.load_labels(D / 'runs' / 'testset_claude_v3.json')
for p in sorted((D / 'runs').glob('*.json')):
    if p.name.startswith(('v3_', 'dev_', 'test_', 'final_')):
        d = json.load(open(p, encoding='utf-8'))
        split = d.get('meta', {}).get('split', 'all')
        s = harness.score(harness.load_labels(p), ref3, harness.split_ids(tests, split))
        t = [v['seconds'] for v in d.get('timing', {}).values()]
        s['seconds_per_report'] = round(sum(t) / len(t), 1) if t else None
        s['split'] = split
        s['meta'] = {k: d['meta'].get(k) for k in ('model', 'prompt', 'variant', 'ctx', 'maxch', 'think', 'failed', 'elapsed_seconds')}
        scores['testset_v3_vs_claude'][p.stem] = s
json.dump(scores, open(D / 'scores.json', 'w', encoding='utf-8'), indent=1)
print('wrote', D / 'scores.json')
for k, v in scores['spike_200_vs_paper'].items():
    print(k, {f: v[f]['f1'] for f in ('victim_countries', 'target_sectors', 'attack_vectors')})
for k, v in scores['spike_local_100_vs_paper'].items():
    print('100', k, {f: v[f]['f1'] for f in ('victim_countries', 'target_sectors', 'attack_vectors')})
print(scores['standard_labels_100_vs_mapped_paper'])
print(scores['testset_v1_agreement'])
