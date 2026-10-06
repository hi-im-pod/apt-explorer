import sys, os, csv, json, glob, re, time, random, urllib.request
sys.path.insert(0, 'pipeline')
from aptx.build.countries import COUNTRIES
import anthropic

sp = sys.argv[1]; N = int(sys.argv[2]); MAXUSD = float(os.environ.get('MAXUSD', '1.3'))
OUT = os.environ.get('OUT', 'results_std.json')
HAIKU = 'claude-haiku-4-5'; LOCAL = os.environ.get('LOCAL_MODEL', 'qwen3.5:35b'); HOST = os.environ.get('OLLAMA_HOST', 'http://localhost:11434')
MAXCH = 40000
SECTORS = ['agriculture', 'aerospace', 'automotive', 'chemical', 'commercial', 'communications', 'construction', 'defense', 'education', 'energy', 'entertainment', 'financial-services', 'government', 'government-national', 'government-regional', 'government-local', 'government-public-services', 'emergency-services', 'healthcare', 'hospitality-leisure', 'infrastructure', 'dams', 'nuclear', 'water', 'insurance', 'manufacturing', 'mining', 'non-profit', 'pharmaceuticals', 'retail', 'technology', 'telecommunications', 'transportation', 'utilities']
IA = ['T1566.001', 'T1566.002', 'T1566.003', 'T1566.004', 'T1566', 'T1190', 'T1133', 'T1078', 'T1189', 'T1195', 'T1199', 'T1091', 'T1200', 'T1659', 'T1669']
NAMES = sorted(COUNTRIES.values()); BYNAME = {v: k for k, v in COUNTRIES.items()}
SCHEMA = {'type': 'object', 'additionalProperties': False,
          'properties': {
              'victim_countries': {'type': 'array', 'items': {'type': 'string', 'enum': NAMES}},
              'target_sectors': {'type': 'array', 'items': {'type': 'string', 'enum': SECTORS}},
              'individuals_targeted': {'type': 'boolean'},
              'initial_access': {'type': 'array', 'items': {'type': 'string', 'enum': IA}}},
          'required': ['victim_countries', 'target_sectors', 'individuals_targeted', 'initial_access']}
SYSTEM = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'std_prompt.txt'), encoding='utf-8').read()


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
                seen.add(r['id']); cands.append((r['id'], r['title'], p))
random.seed(7); random.shuffle(cands)

client = anthropic.Anthropic(api_key=os.environ['ANTHROPIC_API_KEY'])
tin = tout = 0


def spent():
    return tin / 1e6 * 1.0 + tout / 1e6 * 5.0


def clean(o):
    o = dict(o)
    o['victim_countries'] = sorted({BYNAME[n] for n in o.get('victim_countries', []) if n in BYNAME})
    o['target_sectors'] = sorted(set(o.get('target_sectors', [])) & set(SECTORS))
    o['initial_access'] = sorted(set(o.get('initial_access', [])) & set(IA))
    o['individuals_targeted'] = bool(o.get('individuals_targeted'))
    return o


res = []; t0 = time.time()
for rid, title, p in cands:
    if len(res) >= N:
        break
    if spent() >= MAXUSD:
        print('cost cap reached', round(spent(), 2)); break
    try:
        req = urllib.request.Request(f'https://orkl.eu/api/v1/library/entry/sha1/{rid}', headers={'User-Agent': 'apt-explorer-spike (research; contact via github hi-im-pod)'})
        text = json.load(urllib.request.urlopen(req, timeout=30))['data'].get('plain_text') or ''
    except Exception as e:
        print('skip', rid, e, flush=True); time.sleep(1); continue
    if len(text) < 500:
        time.sleep(1); continue
    user = 'Report title: ' + title + '\n\n<report>\n' + text[:MAXCH] + '\n</report>'
    try:
        hr = client.messages.create(model=HAIKU, max_tokens=1500, system=SYSTEM, messages=[{'role': 'user', 'content': user}],
                                    output_config={'format': {'type': 'json_schema', 'schema': SCHEMA}})
        tin += hr.usage.input_tokens; tout += hr.usage.output_tokens
        hout = clean(json.loads(next(b.text for b in hr.content if b.type == 'text')))
    except Exception as e:
        print('haiku error', type(e).__name__, str(e)[:300], flush=True); break
    try:
        body = {'model': LOCAL, 'stream': False, 'think': False, 'format': SCHEMA,
                'options': {'temperature': 0, 'num_ctx': 16384, 'num_predict': 400},
                'messages': [{'role': 'system', 'content': SYSTEM}, {'role': 'user', 'content': user}]}
        lr = json.load(urllib.request.urlopen(urllib.request.Request(HOST + '/api/chat', data=json.dumps(body).encode(), headers={'Content-Type': 'application/json'}), timeout=600))
        lout = clean(json.loads(lr['message']['content']))
    except Exception as e:
        print('local error', type(e).__name__, str(e)[:200], flush=True); lout = None
    res.append({'id': rid, 'haiku': hout, 'local': lout, 'labels': {k: p[k] for k in ('Victim_country', 'Target_sector', 'Attack_vector')}})
    if len(res) % 10 == 0:
        print(len(res), 'spent $', round(spent(), 2), 'elapsed', int(time.time() - t0), flush=True)
json.dump(res, open(sp + '/spike/' + OUT, 'w', encoding='utf-8'), ensure_ascii=False)
print(f'reports {len(res)} haiku in {tin} out {tout} spent ${spent():.3f}; elapsed {int(time.time() - t0)}s')
