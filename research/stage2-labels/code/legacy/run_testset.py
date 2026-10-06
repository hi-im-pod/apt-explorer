"""Label the test set with one local model. Report text stays in memory; only labels are written."""
import sys, os, json, time, urllib.request
sys.path.insert(0, 'pipeline')
from aptx.build.countries import COUNTRIES

sp = sys.argv[1]; MODEL = sys.argv[2]; HOST = os.environ.get('OLLAMA_HOST', 'http://localhost:11434'); MAXCH = 40000
here = os.path.dirname(os.path.abspath(__file__))
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
SYSTEM = open(os.path.join(here, 'std_prompt.txt'), encoding='utf-8').read()


def clean(o):
    return {'victim_countries': sorted({BYNAME[n] for n in o.get('victim_countries', []) if n in BYNAME}),
            'target_sectors': sorted(set(o.get('target_sectors', [])) & set(SECTORS)),
            'individuals_targeted': bool(o.get('individuals_targeted')),
            'initial_access': sorted(set(o.get('initial_access', [])) & set(IA))}


def ask(user, predict):
    body = {'model': MODEL, 'stream': False, 'think': False, 'format': SCHEMA,
            'options': {'temperature': 0, 'num_ctx': 16384, 'num_predict': predict},
            'messages': [{'role': 'system', 'content': SYSTEM}, {'role': 'user', 'content': user}]}
    r = urllib.request.Request(HOST + '/api/chat', data=json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
    return json.loads(json.load(urllib.request.urlopen(r, timeout=900))['message']['content'])


tests = json.load(open(sp + '/spike/testset.json', encoding='utf-8'))
out = {}; t0 = time.time()
for i, t in enumerate(tests, 1):
    req = urllib.request.Request(f"https://orkl.eu/api/v1/library/entry/sha1/{t['id']}", headers={'User-Agent': 'apt-explorer-spike (research; contact via github hi-im-pod)'})
    text = json.load(urllib.request.urlopen(req, timeout=30))['data'].get('plain_text') or ''
    user = 'Report title: ' + t['title'] + '\n\n<report>\n' + text[:MAXCH] + '\n</report>'
    labels = None
    for predict in (400, 800):
        try:
            labels = clean(ask(user, predict)); break
        except Exception as e:
            print('retry', t['id'], type(e).__name__, str(e)[:100], flush=True)
    out[t['id']] = labels
    if i % 10 == 0:
        print(i, 'elapsed', int(time.time() - t0), flush=True)
    time.sleep(1)
name = MODEL.replace(':', '_').replace('.', '')
json.dump(out, open(sp + f'/spike/testset_{name}.json', 'w', encoding='utf-8'), indent=1)
print('done', len(out), 'failed', sum(v is None for v in out.values()), 'elapsed', int(time.time() - t0))
