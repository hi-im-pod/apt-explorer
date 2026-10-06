"""Keep a predicted country only if the report names it (or a common alias or demonym). Text stays in memory."""
import sys, os, json, re, time, urllib.request
sys.path.insert(0, 'pipeline')
from aptx.build.countries import COUNTRIES, _ALIASES

sp = sys.argv[1] + '/spike/'
DEMONYM = {'US': ['American'], 'GB': ['British'], 'RU': ['Russian'], 'CN': ['Chinese'], 'KR': ['South Korean', 'Korean'],
           'KP': ['North Korean'], 'IR': ['Iranian'], 'IL': ['Israeli'], 'UA': ['Ukrainian'], 'JP': ['Japanese'], 'IN': ['Indian'],
           'PK': ['Pakistani'], 'SA': ['Saudi'], 'AE': ['Emirati', 'Emirates'], 'PS': ['Palestinian'], 'TW': ['Taiwanese'],
           'VN': ['Vietnamese'], 'DE': ['German'], 'FR': ['French'], 'PL': ['Polish'], 'TR': ['Turkish'], 'AF': ['Afghan'],
           'PH': ['Philippine', 'Filipino'], 'MM': ['Myanmar', 'Burmese'], 'CO': ['Colombian'], 'BD': ['Bangladeshi'],
           'JO': ['Jordanian'], 'IQ': ['Iraqi'], 'EG': ['Egyptian'], 'SY': ['Syrian'], 'LB': ['Lebanese'], 'QA': ['Qatari'],
           'KW': ['Kuwaiti'], 'AL': ['Albanian'], 'KZ': ['Kazakh'], 'HK': ['Hong Kong']}
names = {c: [n] for c, n in COUNTRIES.items()}
for a, c in _ALIASES.items():
    names.setdefault(c, []).append(a)
for c, d in DEMONYM.items():
    names.setdefault(c, []).extend(d)
pat = {c: re.compile(r'\b(' + '|'.join(re.escape(x) for x in v if len(x) > 2) + r')\b', re.I) for c, v in names.items()}

tests = json.load(open(sp + 'testset.json', encoding='utf-8'))
labs = {'qwen': json.load(open(sp + 'testset_qwen35_35b.json', encoding='utf-8')),
        'gemma': json.load(open(sp + 'testset_gemma4_12b.json', encoding='utf-8'))}
claude = {json.loads(l)['id']: json.loads(l) for l in open(sp + 'testset_claude.jsonl', encoding='utf-8')}
named = {}
for t in tests:
    req = urllib.request.Request(f"https://orkl.eu/api/v1/library/entry/sha1/{t['id']}", headers={'User-Agent': 'apt-explorer-spike (research; contact via github hi-im-pod)'})
    text = (json.load(urllib.request.urlopen(req, timeout=30))['data'].get('plain_text') or '')[:40000]
    named[t['id']] = {c for c, p in pat.items() if p.search(text)}
    time.sleep(1)


def f1(pairs):
    tp = fp = fn = 0
    for p, g in pairs:
        tp += len(p & g); fp += len(p - g); fn += len(g - p)
    pr = tp / (tp + fp) if tp + fp else 0; rc = tp / (tp + fn) if tp + fn else 0
    return round(2 * pr * rc / (pr + rc), 3) if pr + rc else 0.0


ids = [t['id'] for t in tests if labs['qwen'].get(t['id']) and labs['gemma'].get(t['id'])]
mine_ok = sum(set(claude[i]['victim_countries']) <= named[i] for i in ids)
print(f'my labels fully grounded in {mine_ok}/{len(ids)} reports')
for m in labs:
    raw = [(set(labs[m][i]['victim_countries']), set(claude[i]['victim_countries'])) for i in ids]
    gr = [(set(labs[m][i]['victim_countries']) & named[i], set(claude[i]['victim_countries'])) for i in ids]
    avg_raw = sum(len(p) for p, _ in raw) / len(ids); avg_gr = sum(len(p) for p, _ in gr) / len(ids)
    print(f'{m}: vs me raw F1 {f1(raw)} (avg {avg_raw:.2f}) -> grounded F1 {f1(gr)} (avg {avg_gr:.2f})')
qg = [(set(labs['qwen'][i]['victim_countries']) & named[i], set(labs['gemma'][i]['victim_countries']) & named[i]) for i in ids]
print('qwen vs gemma grounded', f1(qg))
json.dump({i: sorted(v) for i, v in named.items()}, open(sp + 'testset_named_countries.json', 'w'))
