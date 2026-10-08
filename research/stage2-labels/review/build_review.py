"""Build the adjudication review page from the saved runs.

Embeds, per test-set report: title, year, publisher, links to the original and the
ORKL archive copy, and the labels from Claude (v3), gemma4:12b (v3 + grounding) and
qwen3.5:35b (v3). No report text. Writes the page to the path given as argv[1].

    python research/stage2-labels/review/build_review.py OUT.html   (from the repo root)
"""
import glob, json, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
REPO = ROOT.parents[1]
sys.path.insert(0, str(ROOT / 'code'))
import harness  # noqa: E402

tests = json.load(open(ROOT / 'data/testset.json', encoding='utf-8'))
ids = {t['id'] for t in tests}
links = {}
for f in glob.glob(str(REPO / 'data/reports/*.json')):
    if f.endswith('index.json'):
        continue
    for r in json.load(open(f, encoding='utf-8')):
        # A test-set report joined with a copy of it may now sit under the copy's ID.
        for rid in [r['id'], *r.get('merged_ids', [])]:
            if rid in ids:
                links[rid] = {'url': r.get('url'), 'archive': r.get('archive_url')}

claude_raw = json.load(open(ROOT / 'data/runs/testset_claude_v3.json', encoding='utf-8'))['labels']
named = json.load(open(ROOT / 'data/runs/testset_named_countries.json', encoding='utf-8'))
gemma = harness.load_labels(ROOT / 'data/runs/v3_gemma4-12b_base.json')
gemma = {i: v | {'victim_countries': sorted(set(v['victim_countries']) & set(named.get(i, [])))} for i, v in gemma.items()}
qwen = harness.load_labels(ROOT / 'data/runs/v3_qwen35-35b_base.json')
KEYS = ('report_type', 'victim_countries', 'victim_regions', 'target_sectors', 'individuals_targeted', 'initial_access')
pick = lambda d: {k: d[k] for k in KEYS} if d else None

reports = []
for n, t in enumerate(tests, 1):
    i = t['id']
    reports.append({'id': i, 'n': n, 'split': 'dev' if n % 2 else 'test', 'title': t['title'], 'year': t['year'],
                    'publisher': t['publisher'], 'url': links.get(i, {}).get('url'), 'archive': links.get(i, {}).get('archive'),
                    'paper': t['paper'], 'note': claude_raw[i].get('note', ''),
                    'labels': {'claude': pick(claude_raw[i]), 'gemma': pick(gemma.get(i)), 'qwen': pick(qwen.get(i))}})

IA_NAMES = {'T1566.001': 'Spearphishing attachment', 'T1566.002': 'Spearphishing link', 'T1566.003': 'Spearphishing via service',
            'T1566.004': 'Spearphishing voice', 'T1566': 'Phishing, channel not stated', 'T1190': 'Exploit public-facing application',
            'T1133': 'External remote services', 'T1078': 'Valid accounts', 'T1189': 'Drive-by compromise', 'T1195': 'Supply chain compromise',
            'T1199': 'Trusted relationship', 'T1091': 'Removable media', 'T1200': 'Hardware additions', 'T1659': 'Content injection',
            'T1669': 'Wi-Fi networks'}
vocab = {'countries': dict(sorted(harness.COUNTRIES.items(), key=lambda kv: kv[1])), 'regions': harness.REGIONS,
         'sectors': harness.SECTORS, 'ia': [[k, IA_NAMES[k]] for k in harness.IA], 'types': harness.REPORT_TYPES}
data = json.dumps({'reports': reports, 'vocab': vocab}, ensure_ascii=False, separators=(',', ':'))
page = (HERE / 'review_template.html').read_text(encoding='utf-8').replace('/*__DATA__*/null', data.replace('</', '<\\/'))
Path(sys.argv[1]).write_text(page, encoding='utf-8')
print('wrote', sys.argv[1], len(page) // 1024, 'KB,', len(reports), 'reports')
