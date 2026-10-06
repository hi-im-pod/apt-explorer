"""Score candidate configurations on a split, including grounding applied after the fact.

Grounding only filters victim countries against the countries the report names, so it
can be applied to a finished run without calling the model again. The names per report
come from data/runs/testset_named_countries.json (first 40,000 characters, as the runs).

    python final_eval.py test
"""
import json, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import harness  # noqa: E402

D = HERE.parent / 'data'
split = sys.argv[1] if len(sys.argv) > 1 else 'test'
tests = json.load(open(D / 'testset.json', encoding='utf-8'))
ids = harness.split_ids(tests, split)
ref = harness.load_labels(D / 'runs' / 'testset_claude_v3.json')
named = json.load(open(D / 'runs' / 'testset_named_countries.json', encoding='utf-8'))


def grounded(labels):
    return {i: v | {'victim_countries': sorted(set(v['victim_countries']) & set(named.get(i, [])))} for i, v in labels.items()}


def composite(s):
    # Equal weight on where, who, how and what kind of report.
    return round((s['location']['f1'] + s['target_sectors_parent']['f1'] + s['initial_access_parent']['f1'] + s['report_type_accuracy']) / 4, 3)


configs = {}
for name, path, ground in (('gemma4:12b v3', 'v3_gemma4-12b_base.json', False),
                           ('gemma4:12b v3 + grounding', 'v3_gemma4-12b_base.json', True),
                           ('qwen3.5:35b v3', 'v3_qwen35-35b_base.json', False),
                           ('qwen3.5:35b v3 + grounding', 'v3_qwen35-35b_base.json', True)):
    lab = harness.load_labels(D / 'runs' / path)
    configs[name] = (grounded(lab) if ground else lab, json.load(open(D / 'runs' / path, encoding='utf-8')).get('timing', {}))
for p in sorted((D / 'runs').glob(f'{split}_*.json')):
    configs[p.stem] = (harness.load_labels(p), json.load(open(p, encoding='utf-8')).get('timing', {}))

out = {}
print(f"split={split}  reference=Claude v3")
print(f"{'configuration':34} {'n':>3} {'country':>7} {'region':>6} {'locat':>6} {'sect-p':>6} {'acc-p':>6} {'type':>5} {'indiv':>5} {'comp':>5} {'s/rep':>5}")
for name, (lab, timing) in configs.items():
    s = harness.score(lab, ref, ids)
    t = [v['seconds'] for k, v in timing.items() if k in ids]
    s['composite'] = composite(s)
    s['seconds_per_report'] = round(sum(t) / len(t), 1) if t else None
    out[name] = s
    print(f"{name:34} {s['reports']:>3} {s['victim_countries']['f1']:>7} {s['victim_regions']['f1']:>6} {s['location']['f1']:>6} "
          f"{s['target_sectors_parent']['f1']:>6} {s['initial_access_parent']['f1']:>6} {s['report_type_accuracy']:>5} "
          f"{s['individuals_accuracy']:>5} {s['composite']:>5} {s['seconds_per_report'] if s['seconds_per_report'] else '-':>5}")
json.dump(out, open(D / f'final_scores_{split}.json', 'w', encoding='utf-8'), indent=1)
