"""Score every labeller against the owner's adjudicated decisions.

    python score_adjudicated.py DECISIONS_DIR

DECISIONS_DIR holds one JSON file per decided report, as exported from the review
page's database (`decisions/<report id>.json`). Only decided reports are scored.
"""
import json, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import harness  # noqa: E402
import compare_paper as cp  # noqa: E402  (runs its own table on import; harmless)

D = HERE.parent / 'data'
ref = {}
for f in Path(sys.argv[1]).glob('*.json'):
    d = json.load(open(f, encoding='utf-8'))
    d = d.get('data', d)
    if d.get('report_id') and 'report_type' in d:
        ref[d['report_id']] = d
ids = list(ref)
tests = {t['id']: t for t in json.load(open(D / 'testset.json', encoding='utf-8'))}
named = json.load(open(D / 'runs' / 'testset_named_countries.json', encoding='utf-8'))
claude = harness.load_labels(D / 'runs' / 'testset_claude_v3.json')
gemma = harness.load_labels(D / 'runs' / 'v3_gemma4-12b_base.json')
gemma = {i: v | {'victim_countries': sorted(set(v['victim_countries']) & set(named.get(i, [])))} for i, v in gemma.items()}
qwen = harness.load_labels(D / 'runs' / 'v3_qwen35-35b_base.json')

print(f'\nAdjudicated reports: {len(ids)} ({sum(tests[i]["paper"] is not None for i in ids)} with paper labels)\n')
print(f"{'labeller':26} {'country':>7} {'region':>7} {'locat':>6} {'sector':>6} {'sect-p':>6} {'access':>6} {'acc-p':>6} {'type':>5} {'indiv':>5}")
out = {}
for name, lab in (('Claude (v3)', claude), ('gemma4:12b v3 + grounding', gemma), ('qwen3.5:35b v3', qwen)):
    s = harness.score(lab, ref, ids)
    out[name] = s
    f = lambda k: s[k]['f1']
    print(f"{name:26} {f('victim_countries'):>7} {f('victim_regions'):>7} {f('location'):>6} {f('target_sectors'):>6} "
          f"{f('target_sectors_parent'):>6} {f('initial_access'):>6} {f('initial_access_parent'):>6} {s['report_type_accuracy']:>5} {s['individuals_accuracy']:>5}")

# The paper's released labels, on the paper's own categories.
refp = {i: cp.ours_up(ref[i]) for i in ids}
paper = {i: cp.paper_up(tests[i]['paper']) for i in ids}
print('\nOn the paper\'s categories (countries / sectors / vectors F1):')
for name, lab in (('CCS 25 labels (GPT-4-Turbo)', paper), ('Claude (v3)', {i: cp.ours_up(claude[i]) for i in ids}),
                  ('gemma4:12b v3 + grounding', {i: cp.ours_up(gemma[i]) for i in ids if i in gemma}),
                  ('qwen3.5:35b v3', {i: cp.ours_up(qwen[i]) for i in ids if i in qwen})):
    row = [harness.prf([(lab[i][k], refp[i][k]) for i in ids if i in lab])['f1'] for k in ('countries', 'sectors', 'vectors')]
    print(f'  {name:30} {row[0]:.2f} / {row[1]:.2f} / {row[2]:.2f}')

# Where the owner changed Claude's labels.
print('\nChanges from Claude\'s labels:')
for i in ids:
    c, r, diffs = claude[i], ref[i], []
    for k in ('victim_countries', 'victim_regions', 'target_sectors', 'initial_access'):
        add, rem = sorted(set(r[k]) - set(c[k])), sorted(set(c[k]) - set(r[k]))
        if add or rem:
            diffs.append(f"{k.split('_')[-1]}: " + ' '.join([f'+{x}' for x in add] + [f'-{x}' for x in rem]))
    if r['report_type'] != c['report_type']:
        diffs.append(f"type {c['report_type']}->{r['report_type']}")
    if bool(r['individuals_targeted']) != bool(c['individuals_targeted']):
        diffs.append(f"individuals {c['individuals_targeted']}->{r['individuals_targeted']}")
    note = (r.get('note') or '').strip()
    print(f"  #{tests[i] and r.get('n', '?'):>2} {'; '.join(diffs) or 'no change'}{('  | note: ' + note[:140]) if note else ''}")
json.dump(out, open(D / 'adjudicated_scores.json', 'w', encoding='utf-8'), indent=1)
