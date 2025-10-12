import os, requests, json
key = os.getenv('BLOCKBERRY_API_KEY') or os.getenv('SUI_API_KEY') or os.getenv('BLOCKVISION_API_KEY')
base = 'https://api.blockberry.one/sui/v1'
headers = {'x-api-key': key, 'accept': '*/*', 'Content-Type': 'application/json'}
print('Using key:', bool(key))
# get recent tx to find a checkpoint
cp = None
try:
    r = requests.post(f"{base}/transactions?page=0&size=1&orderBy=DESC&sortBy=AGE", headers=headers, timeout=10)
    print('recent tx status', r.status_code)
    j = r.json()
    content = j.get('content') or []
    if content:
        cp = content[0].get('checkpoint')
    print('sample checkpoint:', cp)
except Exception as e:
    print('recent tx json err', e)
    cp = None

if cp is None:
    print('No checkpoint to test')
    exit(0)

bodies = []
# simple direct
bodies.append({'checkpoint': cp, 'page': 0, 'size': 1})
# string
bodies.append({'checkpoint': str(cp), 'page': 0, 'size': 1})
# filters array
bodies.append({'filters': [{'field': 'checkpoint', 'op': 'eq', 'value': cp}], 'page': 0, 'size': 1})
bodies.append({'filters': [{'field': 'checkpoint', 'op': 'EQ', 'value': cp}], 'page': 0, 'size': 1})
bodies.append({'filters': [{'field': 'checkpoint', 'operator': 'EQ', 'value': cp}], 'page': 0, 'size': 1})
# where clause
bodies.append({'where': {'checkpoint': cp}, 'page': 0, 'size': 1})
# filter wrapper
bodies.append({'filter': {'checkpoint': cp}, 'page': 0, 'size': 1})
# query list
bodies.append({'queries': [{'name': 'checkpoint', 'value': cp}], 'page': 0, 'size': 1})
# filters as dict
bodies.append({'filters': {'checkpoint': cp}, 'page': 0, 'size': 1})
# nested filter
bodies.append({'filter': [{'field':'checkpoint','value':cp,'op':'='}], 'page':0, 'size':1})
# operator spelled 'operator'
bodies.append({'filters': [{'field':'checkpoint','operator':'eq','value':cp}], 'page':0, 'size':1})
# using 'eq' uppercase
bodies.append({'filters': [{'field':'checkpoint','operator':'EQ','value':cp}], 'page':0, 'size':1})
# alternative key names
bodies.append({'checkpointNumber': cp, 'page':0, 'size':1})

url = f"{base}/transactions?page=0&size=1&orderBy=DESC&sortBy=AGE"

for i, b in enumerate(bodies):
    try:
        r = requests.post(url, headers=headers, json=b, timeout=10)
        print(i, 'POST', url, 'body', b, '=>', r.status_code)
        try:
            j = r.json()
            keys = list(j.keys()) if isinstance(j, dict) else type(j)
            print('  json keys/type:', keys)
            if isinstance(j, dict) and j.get('content'):
                print('  content len:', len(j.get('content')))
        except Exception as e:
            print('  json parse err:', e, 'snippet:', (r.text or '')[:300])
    except Exception as e:
        print('  request err', e)

print('Advanced probe complete')
