import csv, json, glob, re, random, sys, collections
sp = sys.argv[1]; N = 60


def norm(s):
    return re.sub(r'[^a-z0-9]+', '', (s or '').lower())


def has(v):
    v = (v or '').strip()
    return bool(v) and v.lower() not in ('not mentioned', 'n/a', 'none', 'nan')


paper = {}
for r in csv.DictReader(open(sp + '/apt/Information_Retrieved_Collection.csv', encoding='utf-8-sig')):
    for k in (r['Title'], r['Filename']):
        paper.setdefault(norm(re.sub(r'\.pdf$', '', k or '')), r)
cands = []; seen = set()
for f in glob.glob('data/reports/[0-9]*.json'):
    for r in json.load(open(f, encoding='utf-8')):
        if 'paper' in r['sources'] and 'orkl' in r['sources']:
            p = paper.get(norm(r['title']))
            if p and r['id'] not in seen and (has(p['Victim_country']) or has(p['Target_sector']) or has(p['Attack_vector'])):
                seen.add(r['id']); cands.append((r, p))
random.seed(7); random.shuffle(cands)
tuned = {r['id'] for r, _ in cands[:200]}          # every report any prompt so far has seen
pool = cands[200:]
random.seed(2026); random.shuffle(pool)
by_year = collections.defaultdict(list)
for r, p in pool:
    by_year[(r['published'] or '0000')[:4]].append((r, p))
years = sorted(y for y in by_year if y != '0000')
pub_count = collections.Counter(); picked = []
i = 0
while len(picked) < N:
    y = years[i % len(years)]; i += 1
    while by_year[y]:
        r, p = by_year[y].pop()
        org = r.get('organisation') or 'unknown'
        if pub_count[org] >= 4:
            continue
        pub_count[org] += 1
        picked.append({'id': r['id'], 'title': r['title'], 'year': y, 'publisher': org,
                       'paper': {k: p[k] for k in ('Victim_country', 'Target_sector', 'Attack_vector')}})
        break
    if i > 10000:
        break
assert not tuned & {x['id'] for x in picked}
json.dump(picked, open(sp + '/spike/testset.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print(len(picked), 'reports; years', collections.Counter(x['year'] for x in picked))
print('publishers', pub_count.most_common(8))
