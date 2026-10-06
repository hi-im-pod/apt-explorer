import json, sys, collections

res = json.load(open(sys.argv[1], encoding='utf-8'))
res = [r for r in res if r['local'] is not None]

SECT_UP = {}
for v in ['government', 'government-national', 'government-regional', 'government-local', 'government-public-services', 'emergency-services', 'defense']:
    SECT_UP[v] = 'Government and Defense Agencies'
for v, p in {'education': 'Education and Research Institutions', 'financial-services': 'Financial Institutions', 'insurance': 'Financial Institutions',
             'energy': 'Energy and Utilities', 'utilities': 'Energy and Utilities', 'communications': 'Media and Entertainment Companies',
             'entertainment': 'Media and Entertainment Companies', 'non-profit': 'Non-Governmental Organizations (NGOs) and Nonprofits',
             'healthcare': 'Healthcare', 'pharmaceuticals': 'Healthcare'}.items():
    SECT_UP[v] = p
for v in ['infrastructure', 'dams', 'nuclear', 'water', 'telecommunications', 'transportation']:
    SECT_UP[v] = 'Critical Infrastructure'
for v in ['manufacturing', 'automotive', 'chemical', 'aerospace']:
    SECT_UP[v] = 'Manufacturing'
for v in ['commercial', 'retail', 'technology', 'hospitality-leisure', 'agriculture', 'construction', 'mining']:
    SECT_UP[v] = 'Corporations and Businesses'
VEC_FAM = {'Spear Phishing': 'phish', 'Phishing': 'phish', 'Malicious Documents': 'phish', 'Social Engineering': 'phish',
           'Exploit Vulnerability': 'exploit', 'Watering Hole': 'driveby', 'Drive-by Download': 'driveby', 'Website Equipping': 'driveby',
           'Credential Reuse': 'creds', 'Removable Media': 'usb'}
IA_FAM = {'T1190': 'exploit', 'T1189': 'driveby', 'T1078': 'creds', 'T1133': 'creds', 'T1091': 'usb'}


def ia_fam(t):
    return 'phish' if t.startswith('T1566') else IA_FAM.get(t)


def g(v):
    v = (v or '').strip()
    return None if not v or v.lower() in ('not mentioned', 'n/a', 'none', 'nan') else {x.strip() for x in v.split(',') if x.strip()}


def prf(pairs):
    tp = fp = fn = 0
    for p, q in pairs:
        tp += len(p & q); fp += len(p - q); fn += len(q - p)
    pr = tp / (tp + fp) if tp + fp else 0; rc = tp / (tp + fn) if tp + fn else 0
    f = 2 * pr * rc / (pr + rc) if pr + rc else 0
    return f'P{pr:.2f} R{rc:.2f} F1 {f:.3f} (n={len(pairs)})'


def sect_up(o, drop_corp=False):
    s = {SECT_UP[v] for v in o['target_sectors'] if v in SECT_UP}
    if o['individuals_targeted']:
        s.add('Individuals')
    if drop_corp:
        s.discard('Corporations and Businesses')
    return s


def parent(v):
    return 'government' if v.startswith('government') else v


print('== Against the paper labels, mapped up (secondary reference)')
for who in ('haiku', 'local'):
    c = [(set(r[who]['victim_countries']), g(r['labels']['Victim_country'])) for r in res if g(r['labels']['Victim_country'])]
    s = [(sect_up(r[who]), g(r['labels']['Target_sector']) - {'Cloud/IoT Services'}) for r in res if g(r['labels']['Target_sector'])]
    s2 = [(sect_up(r[who], True), g(r['labels']['Target_sector']) - {'Cloud/IoT Services', 'Corporations and Businesses'}) for r in res if g(r['labels']['Target_sector'])]
    v = [({ia_fam(t) for t in r[who]['initial_access']} - {None}, {VEC_FAM[x] for x in g(r['labels']['Attack_vector']) if x in VEC_FAM}) for r in res if g(r['labels']['Attack_vector'])]
    print(f' {who:6} countries {prf(c)}')
    print(f' {who:6} sectors   {prf(s)}')
    print(f' {who:6} sectors without the Corporations catch-all {prf(s2)}')
    print(f' {who:6} initial access (families) {prf(v)}')

print('== Haiku vs local agreement (both models, new labels, every report)')
for k in ('victim_countries', 'target_sectors', 'initial_access'):
    exact = [(set(r['haiku'][k]), set(r['local'][k])) for r in res]
    print(f' {k:18} exact {prf(exact)}')
    if k == 'target_sectors':
        par = [({parent(x) for x in r['haiku'][k]}, {parent(x) for x in r['local'][k]}) for r in res]
        print(f' {k:18} parent {prf(par)}')
    if k == 'initial_access':
        fam = [({t.split('.')[0] for t in r['haiku'][k]}, {t.split('.')[0] for t in r['local'][k]}) for r in res]
        print(f' {k:18} technique {prf(fam)}')
ind = sum(r['haiku']['individuals_targeted'] == r['local']['individuals_targeted'] for r in res)
print(f' individuals_targeted agree {ind}/{len(res)}')

print('== Adjudication load: share of labels the two models disagree on')
tot = dis = 0
for r in res:
    for k in ('victim_countries', 'target_sectors', 'initial_access'):
        a, b = set(r['haiku'][k]), set(r['local'][k])
        tot += len(a | b); dis += len(a ^ b)
print(f' {dis} of {tot} labels ({dis / tot:.0%}) need a human decision')
print('== Label use')
for who in ('haiku', 'local'):
    cnt = collections.Counter(x for r in res for x in r[who]['target_sectors'])
    ia = collections.Counter(x for r in res for x in r[who]['initial_access'])
    print(f' {who} sectors {cnt.most_common(10)}')
    print(f' {who} access  {ia.most_common(8)}')
    print(f' {who} empty initial_access {sum(not r[who]["initial_access"] for r in res)}, avg countries {sum(len(r[who]["victim_countries"]) for r in res) / len(res):.1f}')
