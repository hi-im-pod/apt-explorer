"""Print a compact score table for several runs against one reference."""
import json, sys, subprocess
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import harness
ref = harness.load_labels(sys.argv[1]); split = sys.argv[2]
tests = json.load(open(HERE.parent / 'data' / 'testset.json', encoding='utf-8'))
ids = harness.split_ids(tests, split)
print(f"{'run':38} {'n':>3} {'country':>7} {'region':>7} {'locat':>6} {'sector':>6} {'sect-p':>6} {'access':>6} {'acc-p':>6} {'type':>5} {'indiv':>5} {'s/rep':>5}")
for p in sys.argv[3:]:
    d = json.load(open(p, encoding='utf-8')); pred = harness.load_labels(p); s = harness.score(pred, ref, ids)
    t = [v['seconds'] for k, v in d.get('timing', {}).items() if k in ids]
    f = lambda k: s[k]['f1']
    print(f"{Path(p).stem[:38]:38} {s['reports']:>3} {f('victim_countries'):>7} {f('victim_regions'):>7} {f('location'):>6} {f('target_sectors'):>6} {f('target_sectors_parent'):>6} {f('initial_access'):>6} {f('initial_access_parent'):>6} {s['report_type_accuracy']:>5} {s['individuals_accuracy']:>5} {round(sum(t)/len(t),1) if t else '-':>5}")
