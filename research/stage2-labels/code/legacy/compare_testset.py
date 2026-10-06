"""Compare the three labellers on the 60-report test set and list what needs a human decision."""
import json, sys, os, collections, itertools
sp = sys.argv[1] + '/spike/'
tests = {t['id']: t for t in json.load(open(sp + 'testset.json', encoding='utf-8'))}
claude = {}
for line in open(sp + 'testset_claude.jsonl', encoding='utf-8'):
    r = json.loads(line); claude[r['id']] = r
labellers = {'claude': claude}
for name, f in (('qwen', 'testset_qwen35_35b.json'), ('gemma', 'testset_gemma4_12b.json')):
    if os.path.exists(sp + f):
        labellers[name] = {k: v for k, v in json.load(open(sp + f, encoding='utf-8')).items() if v is not None}
FIELDS = ('victim_countries', 'target_sectors', 'initial_access')


def norm(field, vals, level):
    s = set(vals)
    if level == 'parent':
        if field == 'target_sectors':
            s = {'government' if v.startswith('government') or v == 'emergency-services' else v for v in s}
            s = {'infrastructure' if v in ('dams', 'nuclear', 'water') else v for v in s}
        if field == 'initial_access':
            s = {v.split('.')[0] for v in s}
    return s


def prf(pairs):
    tp = fp = fn = 0
    for p, g in pairs:
        tp += len(p & g); fp += len(p - g); fn += len(g - p)
    pr = tp / (tp + fp) if tp + fp else 0; rc = tp / (tp + fn) if tp + fn else 0
    return round(2 * pr * rc / (pr + rc), 3) if pr + rc else 0.0


ids = [i for i in tests if all(i in lab for lab in labellers.values())]
print(f'reports labelled by all of {list(labellers)}: {len(ids)}')
print('\n== Pairwise agreement (F1 between two labellers, exact | parent level)')
for a, b in itertools.combinations(labellers, 2):
    row = []
    for f in FIELDS:
        ex = prf([(norm(f, labellers[a][i][f], 'exact'), norm(f, labellers[b][i][f], 'exact')) for i in ids])
        pa = prf([(norm(f, labellers[a][i][f], 'parent'), norm(f, labellers[b][i][f], 'parent')) for i in ids])
        row.append(f'{f.split("_")[1] if f != "victim_countries" else "countries"} {ex}|{pa}')
    ind = sum(bool(labellers[a][i]['individuals_targeted']) == bool(labellers[b][i]['individuals_targeted']) for i in ids)
    print(f' {a:6} vs {b:6}: ' + '  '.join(row) + f'  individuals {ind}/{len(ids)}')

print('\n== Each model scored against Claude as a provisional reference (parent level)')
for m in labellers:
    if m == 'claude':
        continue
    print(' ', m, {f: prf([(norm(f, labellers[m][i][f], 'parent'), norm(f, claude[i][f], 'parent')) for i in ids]) for f in FIELDS})

print('\n== Majority vote and the decisions a human must make')
need = []; auto = 0; total = 0
for i in ids:
    for f in FIELDS:
        votes = collections.Counter(v for lab in labellers.values() for v in set(lab[i][f]))
        for v, n in votes.items():
            total += 1
            if n == len(labellers):
                auto += 1
            else:
                need.append((tests[i]['title'][:70], f, v, n, sorted(k for k, lab in labellers.items() if v in lab[i][f])))
print(f' {auto} of {total} labels are unanimous; {len(need)} need a decision ({len(need) / max(1, total):.0%})')
by_field = collections.Counter(n[1] for n in need)
print(' by field:', dict(by_field))
json.dump([{'title': t, 'field': f, 'value': v, 'votes': n, 'by': who} for t, f, v, n, who in need],
          open(sp + 'testset_disagreements.json', 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
