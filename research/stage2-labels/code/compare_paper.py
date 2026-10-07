"""Score the CCS '25 released labels (GPT-4-Turbo output) and our models against the same
reference, at the paper's category level, so the comparison uses one yardstick.

Our labels are mapped up to the paper's categories (docs/stage2-labels.md section 5).
The paper has no regions, so countries are compared as countries only.
"""
import json, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import harness  # noqa: E402

D = HERE.parent / 'data'
GOV = ['government', 'government-national', 'government-regional', 'government-local', 'government-public-services', 'emergency-services', 'defense']
UP = {v: 'Government and Defense Agencies' for v in GOV}
UP.update({'education': 'Education and Research Institutions', 'financial-services': 'Financial Institutions', 'insurance': 'Financial Institutions',
           'energy': 'Energy and Utilities', 'utilities': 'Energy and Utilities', 'communications': 'Media and Entertainment Companies',
           'entertainment': 'Media and Entertainment Companies', 'non-profit': 'Non-Governmental Organizations (NGOs) and Nonprofits',
           'healthcare': 'Healthcare', 'pharmaceuticals': 'Healthcare'})
UP.update({v: 'Critical Infrastructure' for v in ['infrastructure', 'dams', 'nuclear', 'water', 'telecommunications', 'transportation']})
UP.update({v: 'Manufacturing' for v in ['manufacturing', 'automotive', 'chemical', 'aerospace']})
UP.update({v: 'Corporations and Businesses' for v in ['commercial', 'retail', 'technology', 'hospitality-leisure', 'agriculture', 'construction', 'mining']})
VEC = {'Spear Phishing': 'phish', 'Phishing': 'phish', 'Malicious Documents': 'phish', 'Social Engineering': 'phish', 'Exploit Vulnerability': 'exploit',
       'Watering Hole': 'driveby', 'Drive-by Download': 'driveby', 'Website Equipping': 'driveby', 'Credential Reuse': 'creds', 'Removable Media': 'usb'}
IAF = {'T1190': 'exploit', 'T1189': 'driveby', 'T1078': 'creds', 'T1133': 'creds', 'T1091': 'usb'}


def pset(v):
    v = (v or '').strip()
    return set() if not v or v.lower() in ('not mentioned', 'n/a', 'none', 'nan') else {x.strip() for x in v.split(',') if x.strip()}


def ours_up(lab):
    sect = {UP[s] for s in lab['target_sectors'] if s in UP} | ({'Individuals'} if lab['individuals_targeted'] else set())
    ia = {('phish' if t.startswith('T1566') else IAF.get(t)) for t in lab['initial_access']} - {None}
    return {'countries': set(lab['victim_countries']), 'sectors': sect, 'vectors': ia}


def paper_up(p):
    return {'countries': {c.upper() for c in pset(p['Victim_country'])}, 'sectors': pset(p['Target_sector']) - {'Cloud/IoT Services'},
            'vectors': {VEC[v] for v in pset(p['Attack_vector']) if v in VEC}}


tests = json.load(open(D / 'testset.json', encoding='utf-8'))
paper = {t['id']: paper_up(t['paper']) for t in tests}
ref = {k: ours_up(v) for k, v in harness.load_labels(D / 'runs' / 'testset_claude_v3.json').items()}
named = json.load(open(D / 'runs' / 'testset_named_countries.json', encoding='utf-8'))
g = harness.load_labels(D / 'runs' / 'v3_gemma4-12b_base.json')
gg = {i: v | {'victim_countries': sorted(set(v['victim_countries']) & set(named[i]))} for i, v in g.items()}
q = harness.load_labels(D / 'runs' / 'v3_qwen35-35b_base.json')
systems = {'CCS 25 labels (GPT-4-Turbo)': paper, 'gemma4:12b v3 + grounding': {k: ours_up(v) for k, v in gg.items()},
           'qwen3.5:35b v3': {k: ours_up(v) for k, v in q.items()}}
out = {}
for split in ('all', 'test'):
    ids = [i for i in harness.split_ids(tests, split) if all(i in s for s in systems.values()) and i in ref]
    print(f'\nsplit={split} reports={len(ids)}  reference=Claude v3, mapped to the paper categories')
    print(f"{'system':30} {'countries':>22} {'sectors':>22} {'vectors':>22} {'avg countries':>14}")
    for name, s in systems.items():
        row = {f: harness.prf([(s[i][f], ref[i][f]) for i in ids]) for f in ('countries', 'sectors', 'vectors')}
        avg = sum(len(s[i]['countries']) for i in ids) / len(ids)
        out[f'{split}:{name}'] = row | {'avg_countries': round(avg, 2)}
        fmt = lambda r: f"{r['precision']:.2f}/{r['recall']:.2f}/{r['f1']:.2f}"
        print(f"{name:30} {fmt(row['countries']):>22} {fmt(row['sectors']):>22} {fmt(row['vectors']):>22} {avg:>14.2f}")
    print(f"{'(reference, Claude v3)':30} {'':>22} {'':>22} {'':>22} {sum(len(ref[i]['countries']) for i in ids)/len(ids):>14.2f}")
json.dump(out, open(D / 'paper_comparison.json', 'w', encoding='utf-8'), indent=1)
