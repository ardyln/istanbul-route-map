"""Each İETT line's stop order, from iett.istanbul (one request a second, resumable: done lines are skipped)."""
import json, re, time, urllib.request, urllib.parse, os
HERE = os.path.dirname(os.path.abspath(__file__))
hat = json.load(open(f'{HERE}/data/hat.json'))
UA = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) route-map'}
done = fail = 0
for h in hat:
    line = h['SHATKODU']; out = f'{HERE}/data/lines/{urllib.parse.quote(line, safe="")}.json'
    if os.path.exists(out):
        done += 1; continue
    parts = re.split(r'\s*-\s*', h['SHATADI'].strip(), maxsplit=1)
    q = {'hatkod': line, 'hatstart': parts[0], 'hatend': parts[1] if len(parts) > 1 else '', 'langid': 1}
    page, err = None, None
    for attempt in range(3):
        try:
            time.sleep(1.0 + attempt * 5)
            page = urllib.request.urlopen(urllib.request.Request(
                'https://iett.istanbul/tr/RouteStation/GetStationForRoute?' + urllib.parse.urlencode(q), headers=UA),
                timeout=30).read().decode('utf-8')
            break
        except Exception as e:
            err = e
    if page is None:
        fail += 1; print('FAIL', line, err, flush=True); continue
    dirs = [re.findall(r'dkod=(\d+)', part) for part in re.split(r'line-pass-header">', page)[1:]]
    tmp = out + '.part'
    json.dump({'line': line, 'name': h['SHATADI'], 'dirs': [d for d in dirs if d]}, open(tmp, 'w'))
    os.replace(tmp, out)
    done += 1
    if done % 50 == 0: print(done, 'of', len(hat), flush=True)
print('done', done, 'failed', fail, flush=True)
