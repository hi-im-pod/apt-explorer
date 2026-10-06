import sys, json
sp = sys.argv[1]; i = int(sys.argv[2]); c, s, ind, ia, note = sys.argv[3:8]
t = json.load(open(sp + '/spike/testset.json', encoding='utf-8'))[i - 1]
rec = {'n': i, 'id': t['id'], 'victim_countries': [x for x in c.split(',') if x], 'target_sectors': [x for x in s.split(',') if x],
       'individuals_targeted': ind == '1', 'initial_access': [x for x in ia.split(',') if x], 'note': note}
open(sp + '/spike/testset_claude.jsonl', 'a', encoding='utf-8').write(json.dumps(rec) + '\n')
print('saved', i)
