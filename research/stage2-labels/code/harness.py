"""Stage 2 label-extraction test harness.

Runs a local model (Ollama) over the test set, cleans and optionally grounds the
output, and scores any run against a reference. Report text is fetched from ORKL
and held in memory only; nothing but labels, timings and token counts is written.

    python harness.py run   --model gemma4:12b --prompt v3 --variant base --out RUN.json
    python harness.py score --pred RUN.json --ref claude_v3.json [--split dev|test|all]

Set OLLAMA_HOST (default http://localhost:11434). Run from the repository root so
the pipeline's country table can be imported.
"""
import argparse, json, os, re, sys, time, urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT.parents[1] / 'pipeline'))
from aptx.build.countries import COUNTRIES, _ALIASES  # noqa: E402

ORKL = 'https://orkl.eu/api/v1/library/entry/sha1/'
UA = 'apt-explorer-research (non-commercial; github.com/hi-im-pod/apt-explorer)'
SECTORS = ['agriculture', 'aerospace', 'automotive', 'chemical', 'commercial', 'communications', 'construction', 'defense',
           'education', 'energy', 'entertainment', 'financial-services', 'government', 'government-national', 'government-regional',
           'government-local', 'government-public-services', 'emergency-services', 'healthcare', 'hospitality-leisure',
           'infrastructure', 'dams', 'nuclear', 'water', 'insurance', 'manufacturing', 'mining', 'non-profit', 'pharmaceuticals',
           'retail', 'technology', 'telecommunications', 'transportation', 'utilities']
IA = ['T1566.001', 'T1566.002', 'T1566.003', 'T1566.004', 'T1566', 'T1190', 'T1133', 'T1078', 'T1189', 'T1195', 'T1199',
      'T1091', 'T1200', 'T1659', 'T1669']
# UN M49 regions and sub-regions, plus two terms vendors use constantly.
REGIONS = ['Africa', 'Northern Africa', 'Sub-Saharan Africa', 'Eastern Africa', 'Middle Africa', 'Southern Africa', 'Western Africa',
           'Americas', 'Latin America and the Caribbean', 'Caribbean', 'Central America', 'South America', 'Northern America',
           'Asia', 'Central Asia', 'Eastern Asia', 'South-eastern Asia', 'Southern Asia', 'Western Asia',
           'Europe', 'Eastern Europe', 'Northern Europe', 'Southern Europe', 'Western Europe',
           'Oceania', 'Australia and New Zealand', 'Melanesia', 'Micronesia', 'Polynesia', 'Middle East', 'Worldwide']
REPORT_TYPES = ['campaign', 'malware-analysis', 'actor-profile', 'advisory', 'news', 'attribution', 'survey', 'methodology']
SKIP_TYPES = {'attribution', 'survey', 'methodology'}
NAMES = sorted(COUNTRIES.values())
BYNAME = {v: k for k, v in COUNTRIES.items()}
FIELDS = ('victim_countries', 'victim_regions', 'target_sectors', 'initial_access')


def schema(variant):
    arr = lambda enum: {'type': 'array', 'items': {'type': 'string', 'enum': enum}}
    props = {'report_type': {'type': 'string', 'enum': REPORT_TYPES},
             'victim_countries': arr(NAMES), 'victim_regions': arr(REGIONS), 'target_sectors': arr(SECTORS),
             'individuals_targeted': {'type': 'boolean'}, 'initial_access': arr(IA)}
    order = ['report_type']
    if variant in ('decoy', 'decoy-ground'):
        # Somewhere to put countries that are not victims, so they do not leak into victim_countries.
        props['attacker_countries'] = arr(NAMES)
        props['other_countries_mentioned'] = arr(NAMES)
        order += ['attacker_countries', 'other_countries_mentioned']
    order += ['victim_countries', 'victim_regions', 'target_sectors', 'individuals_targeted', 'initial_access']
    return {'type': 'object', 'additionalProperties': False, 'properties': {k: props[k] for k in order}, 'required': order}


def fetch_text(report_id):
    req = urllib.request.Request(ORKL + report_id, headers={'User-Agent': UA})
    return json.load(urllib.request.urlopen(req, timeout=60))['data'].get('plain_text') or ''


# Names, aliases and demonyms used by the grounding check.
DEMONYM = {'US': ['American'], 'GB': ['British'], 'RU': ['Russian'], 'CN': ['Chinese'], 'KR': ['South Korean', 'Korean'],
           'KP': ['North Korean'], 'IR': ['Iranian'], 'IL': ['Israeli'], 'UA': ['Ukrainian'], 'JP': ['Japanese'], 'IN': ['Indian'],
           'PK': ['Pakistani'], 'SA': ['Saudi'], 'AE': ['Emirati', 'Emirates'], 'PS': ['Palestinian'], 'TW': ['Taiwanese'],
           'VN': ['Vietnamese'], 'DE': ['German'], 'FR': ['French'], 'PL': ['Polish'], 'TR': ['Turkish'], 'AF': ['Afghan'],
           'PH': ['Philippine', 'Filipino'], 'MM': ['Burmese'], 'CO': ['Colombian'], 'BD': ['Bangladeshi'], 'JO': ['Jordanian'],
           'IQ': ['Iraqi'], 'EG': ['Egyptian'], 'SY': ['Syrian'], 'LB': ['Lebanese'], 'QA': ['Qatari'], 'KW': ['Kuwaiti'],
           'AL': ['Albanian'], 'KZ': ['Kazakh']}
_names = {c: [n] for c, n in COUNTRIES.items()}
for _a, _c in _ALIASES.items():
    _names.setdefault(_c, []).append(_a)
for _c, _d in DEMONYM.items():
    _names.setdefault(_c, []).extend(_d)
PATTERNS = {c: re.compile(r'\b(' + '|'.join(re.escape(x) for x in v if len(x) > 2) + r')\b', re.I) for c, v in _names.items()}


def named_countries(text):
    return {c for c, p in PATTERNS.items() if p.search(text)}


def clean(o, text=None, ground=False):
    out = {'report_type': o.get('report_type') if o.get('report_type') in REPORT_TYPES else 'campaign',
           'victim_countries': sorted({BYNAME[n] for n in o.get('victim_countries', []) if n in BYNAME}),
           'victim_regions': sorted(set(o.get('victim_regions', [])) & set(REGIONS)),
           'target_sectors': sorted(set(o.get('target_sectors', [])) & set(SECTORS)),
           'individuals_targeted': bool(o.get('individuals_targeted')),
           'initial_access': sorted(set(o.get('initial_access', [])) & set(IA))}
    if ground and text is not None:
        out['victim_countries'] = sorted(set(out['victim_countries']) & named_countries(text))
    if 'commercial' in out['target_sectors'] and len(out['target_sectors']) > 1:
        out['target_sectors'].remove('commercial')
    if out['report_type'] in SKIP_TYPES:
        for f in FIELDS:
            out[f] = []
        out['individuals_targeted'] = False
    return out


def ollama(model, system, sch, user, ctx, predict, think):
    host = os.environ.get('OLLAMA_HOST', 'http://localhost:11434')
    body = {'model': model, 'stream': False, 'think': think, 'format': sch, 'keep_alive': '30m',
            'options': {'temperature': 0, 'num_ctx': ctx, 'num_predict': predict},
            'messages': ([{'role': 'system', 'content': system}] if system else []) + [{'role': 'user', 'content': user}]}
    req = urllib.request.Request(host + '/api/chat', data=json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
    r = json.load(urllib.request.urlopen(req, timeout=1200))
    return json.loads(r['message']['content']), r


def split_ids(tests, split):
    # Reports were picked round-robin by year, so odd and even positions are both stratified by year.
    if split == 'all':
        return [t['id'] for t in tests]
    want = 1 if split == 'dev' else 0
    return [t['id'] for n, t in enumerate(tests, 1) if n % 2 == want]


def run(a):
    tests = json.load(open(ROOT / 'data' / 'testset.json', encoding='utf-8'))
    ids = set(split_ids(tests, a.split))
    # --prompt none sends no system prompt, for models with the rules built in (deploy/Modelfile).
    system = '' if a.prompt == 'none' else (ROOT / 'prompts' / f'{a.prompt}.txt').read_text(encoding='utf-8')
    sch = schema(a.variant)
    ground = a.variant.endswith('ground')
    out = {'meta': vars(a) | {'started': time.strftime('%Y-%m-%dT%H:%M:%S')}, 'labels': {}, 'raw': {}, 'timing': {}}
    t0 = time.time()
    for t in tests:
        if t['id'] not in ids:
            continue
        text = fetch_text(t['id'])
        user = 'Report title: ' + t['title'] + '\n\n<report>\n' + text[:a.maxch] + '\n</report>'
        res = None
        for predict in (a.predict, a.predict * 2):
            try:
                s = time.time()
                raw, r = ollama(a.model, system, sch, user, a.ctx, predict, a.think)
                res = clean(raw, text, ground)
                out['raw'][t['id']] = raw
                out['timing'][t['id']] = {'seconds': round(time.time() - s, 1), 'prompt_tokens': r.get('prompt_eval_count'),
                                          'output_tokens': r.get('eval_count')}
                break
            except Exception as e:  # malformed JSON or a timeout: retry once with more room
                print('retry', t['id'], type(e).__name__, str(e)[:120], flush=True)
        out['labels'][t['id']] = res
        print(len(out['labels']), 'elapsed', int(time.time() - t0), flush=True)
        time.sleep(1)
    out['meta']['elapsed_seconds'] = int(time.time() - t0)
    out['meta']['failed'] = sum(v is None for v in out['labels'].values())
    json.dump(out, open(a.out, 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
    print('done', len(out['labels']), 'failed', out['meta']['failed'], 'elapsed', out['meta']['elapsed_seconds'])


def load_labels(path):
    d = json.load(open(path, encoding='utf-8'))
    return {k: v for k, v in (d['labels'] if 'labels' in d else d).items() if v is not None}


def parent(field, values):
    s = set(values)
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
    pr = tp / (tp + fp) if tp + fp else 0.0
    rc = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * pr * rc / (pr + rc) if pr + rc else 0.0
    return {'precision': round(pr, 3), 'recall': round(rc, 3), 'f1': round(f1, 3), 'tp': tp, 'fp': fp, 'fn': fn}


def score(pred, ref, ids):
    ids = [i for i in ids if i in pred and i in ref]
    res = {'reports': len(ids)}
    for f in FIELDS:
        res[f] = prf([(set(pred[i][f]), set(ref[i][f])) for i in ids])
        if f in ('target_sectors', 'initial_access'):
            res[f + '_parent'] = prf([(parent(f, pred[i][f]), parent(f, ref[i][f])) for i in ids])
    # Location: a country or a region, so a correct region counts when the reference has no country, and vice versa.
    res['location'] = prf([(set(pred[i]['victim_countries']) | set(pred[i]['victim_regions']),
                            set(ref[i]['victim_countries']) | set(ref[i]['victim_regions'])) for i in ids])
    res['report_type_accuracy'] = round(sum(pred[i]['report_type'] == ref[i]['report_type'] for i in ids) / len(ids), 3)
    res['individuals_accuracy'] = round(sum(pred[i]['individuals_targeted'] == ref[i]['individuals_targeted'] for i in ids) / len(ids), 3)
    return res


def score_cmd(a):
    tests = json.load(open(ROOT / 'data' / 'testset.json', encoding='utf-8'))
    print(json.dumps(score(load_labels(a.pred), load_labels(a.ref), split_ids(tests, a.split)), indent=1))


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest='cmd', required=True)
    r = sub.add_parser('run')
    r.add_argument('--model', required=True)
    r.add_argument('--prompt', default='v3')
    r.add_argument('--variant', default='base', choices=['base', 'ground', 'decoy', 'decoy-ground'])
    r.add_argument('--ctx', type=int, default=16384)
    r.add_argument('--maxch', type=int, default=40000)
    r.add_argument('--predict', type=int, default=500)
    r.add_argument('--think', action='store_true')
    r.add_argument('--split', default='all', choices=['dev', 'test', 'all'])
    r.add_argument('--out', required=True)
    s = sub.add_parser('score')
    s.add_argument('--pred', required=True)
    s.add_argument('--ref', required=True)
    s.add_argument('--split', default='all', choices=['dev', 'test', 'all'])
    a = p.parse_args()
    run(a) if a.cmd == 'run' else score_cmd(a)
