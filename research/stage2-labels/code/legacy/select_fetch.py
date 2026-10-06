import csv, json, glob, re, sys, time, random, urllib.request
sp=sys.argv[1]; N=int(sys.argv[2])
def norm(s): return re.sub(r'[^a-z0-9]+','',(s or '').lower())
def has(v):
    v=(v or '').strip(); return bool(v) and v.lower() not in ('not mentioned','n/a','none','nan')
paper={}
for r in csv.DictReader(open(sp+'/apt/Information_Retrieved_Collection.csv',encoding='utf-8-sig')):
    for k in (r['Title'], r['Filename']):
        paper.setdefault(norm(re.sub(r'\.pdf$','',k or '')),r)
cands=[]; seen=set()
for f in glob.glob('data/reports/[0-9]*.json'):
    for r in json.load(open(f,encoding='utf-8')):
        if 'paper' in r['sources'] and 'orkl' in r['sources']:
            p=paper.get(norm(r['title']))
            if p and r['id'] not in seen and (has(p['Victim_country']) or has(p['Target_sector']) or has(p['Attack_vector'])):
                seen.add(r['id']); cands.append((r['id'],r['title'],p))
print('matched candidates',len(cands))
random.seed(7); random.shuffle(cands)
out=open(sp+'/spike/sample.jsonl','w',encoding='utf-8'); got=0
for rid,title,p in cands:
    if got>=N: break
    try:
        req=urllib.request.Request(f'https://orkl.eu/api/v1/library/entry/sha1/{rid}',headers={'User-Agent':'apt-explorer-spike (research; contact via github hi-im-pod)'})
        d=json.load(urllib.request.urlopen(req,timeout=30))['data']
    except Exception as e:
        print('skip',rid,e); time.sleep(1); continue
    text=d.get('plain_text') or ''
    if len(text)<500: time.sleep(1); continue
    lab={k:p[k] for k in ('Victim_country','Target_sector','Attack_vector','Malware','Attack_start_date','Attack_end_date')}
    out.write(json.dumps({'id':rid,'title':title,'chars':len(text),'text':text,'labels':lab},ensure_ascii=False)+'\n'); got+=1
    if got%25==0: print(got,flush=True)
    time.sleep(1)
print('saved',got)
