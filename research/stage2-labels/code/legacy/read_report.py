"""Print the prose of test-set reports for labelling. Nothing is written to disk."""
import sys, json, re, urllib.request

sp = sys.argv[1]; a, b = int(sys.argv[2]), int(sys.argv[3]); MAXCH = 40000
tests = json.load(open(sp + '/spike/testset.json', encoding='utf-8'))


def prose(line):
    s = line.strip()
    if len(s) < 25 or '://' in s or re.search(r'[0-9a-fA-F]{16,}', s) or re.search(r'[{};$<>\\|]{2,}', s):
        return False
    letters = sum(c.isalpha() or c == ' ' for c in s)
    return letters / len(s) > 0.8


for i in range(a, b + 1):
    t = tests[i - 1]
    req = urllib.request.Request(f"https://orkl.eu/api/v1/library/entry/sha1/{t['id']}", headers={'User-Agent': 'apt-explorer-spike (research; contact via github hi-im-pod)'})
    text = json.load(urllib.request.urlopen(req, timeout=30))['data'].get('plain_text') or ''
    kept = [re.sub(r'\s+', ' ', l).strip() for l in text[:MAXCH].splitlines() if prose(l)]
    body = ' '.join(kept)
    print(f"##### REPORT {i} | {t['year']} | {t['publisher']} | {t['title']}\n{body[:14000]}\n")
