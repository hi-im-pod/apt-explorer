"""Revise the in-session Claude labels (v1) to the v3 rules agreed on 2026-10-07.

v3 changes: a report_type for every report; victim_regions when no victim country is
stated; countries implied by specific evidence now count; a malicious document or
file that reached victims through an unstated channel is T1566. Every change is listed
here so the revision can be audited against the v1 file.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
v1 = {json.loads(l)['n']: json.loads(l) for l in open(ROOT / 'data/runs/testset_claude_v1.jsonl', encoding='utf-8')}

TYPE = {n: 'campaign' for n in v1}
TYPE.update({2: 'malware-analysis', 3: 'malware-analysis', 7: 'survey', 9: 'advisory', 12: 'news', 15: 'malware-analysis',
             16: 'malware-analysis', 23: 'malware-analysis', 25: 'malware-analysis', 33: 'news', 35: 'attribution', 36: 'news',
             41: 'news', 42: 'methodology', 43: 'malware-analysis', 44: 'malware-analysis', 46: 'malware-analysis', 49: 'survey',
             55: 'actor-profile', 56: 'survey', 57: 'methodology', 58: 'malware-analysis', 59: 'malware-analysis'})
REGIONS = {3: ['Worldwide'], 6: ['Middle East', 'Northern Africa'], 10: ['Middle East'], 14: ['Middle East', 'Northern Africa'],
           18: ['Europe'], 32: ['Eastern Europe'], 40: ['Northern America', 'Europe'], 46: ['Middle East'],
           48: ['Middle East', 'South-eastern Asia'], 52: ['Europe'], 53: ['Eastern Europe'], 55: ['Middle East']}
ADD_COUNTRY = {11: ['VN'],   # Vietnamese-language lure (Thu moi) aimed at Vietnamese dissidents
               26: ['UA'],   # Ukrainian-language decoy impersonating the State Migration Service, aimed at its employees
               59: ['JO']}   # decoy shows a Jordanian government ministry logo after the macro runs
# A document or file reached the victims, but the report does not say how it was delivered.
ADD_T1566 = [1, 11, 15, 16, 18, 25, 26, 29, 30, 44, 46]

out = {}
for n, r in v1.items():
    lab = {'report_type': TYPE[n], 'victim_countries': sorted(set(r['victim_countries']) | set(ADD_COUNTRY.get(n, []))),
           'victim_regions': REGIONS.get(n, []), 'target_sectors': r['target_sectors'],
           'individuals_targeted': r['individuals_targeted'], 'initial_access': sorted(set(r['initial_access']) | ({'T1566'} if n in ADD_T1566 else set())),
           'note': r['note']}
    if TYPE[n] in ('attribution', 'survey', 'methodology'):
        lab.update(victim_countries=[], victim_regions=[], target_sectors=[], initial_access=[], individuals_targeted=False)
    out[r['id']] = lab
json.dump({'meta': {'labeller': 'claude-opus-5-5 in session', 'rules': 'v3', 'revised_from': 'testset_claude_v1.jsonl'}, 'labels': out},
          open(ROOT / 'data/runs/testset_claude_v3.json', 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
print('wrote', len(out), 'labels;', sum(bool(v['initial_access']) for v in out.values()), 'with initial access;',
      sum(bool(v['victim_regions']) for v in out.values()), 'with regions')
