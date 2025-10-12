import os, requests, json
key = os.getenv('BLOCKBERRY_API_KEY') or os.getenv('SUI_API_KEY') or os.getenv('BLOCKVISION_API_KEY')
base = 'https://api.blockberry.one/sui/v1'
headers = {'x-api-key': key, 'accept': '*/*'}
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

candidates = []
if cp is not None:
    candidates = [
        ('GET', f"{base}/transactions?checkpoint={cp}&page=0&size=1&orderBy=DESC&sortBy=AGE", None),
        ('GET', f"{base}/transactions?page=0&size=1&checkpoint={cp}&orderBy=DESC&sortBy=AGE", None),
        ('POST_JSON', f"{base}/transactions", {'checkpoint': cp, 'page': 0, 'size': 1}),
        ('POST_JSON', f"{base}/transactions?page=0&size=1", {'checkpoint': cp}),
        ('POST', f"{base}/transaction-blocks/{cp}/transactions?page=0&size=1", None),
        ('GET', f"{base}/transaction-blocks/{cp}/transactions?page=0&size=1", None),
        ('POST_JSON', f"{base}/transaction-blocks/{cp}/transactions", {'page':0,'size':1}),
    ]
else:
    candidates = [('POST', f"{base}/transactions?page=0&size=1&orderBy=DESC&sortBy=AGE", None)]

for method, url, body in candidates:
    try:
        if method == 'GET':
            r = requests.get(url, headers=headers, timeout=8)
            print('GET', url, '=>', r.status_code)
            try:
                print('JSON keys:', list(r.json().keys()))
            except Exception as e:
                print('GET json err', e, 'snippet', (r.text or '')[:200])
        elif method == 'POST_JSON':
            r = requests.post(url, headers={**headers, 'Content-Type':'application/json'}, json=body, timeout=8)
            print('POST_JSON', url, 'body', body, '=>', r.status_code)
            try:
                print('JSON keys:', list(r.json().keys()))
            except Exception as e:
                print('POST_JSON json err', e, 'snippet', (r.text or '')[:200])
        else:
            r = requests.post(url, headers=headers, timeout=8)
            print('POST', url, '=>', r.status_code)
            try:
                print('JSON keys:', list(r.json().keys()))
            except Exception as e:
                print('POST json err', e, 'snippet', (r.text or '')[:200])
    except Exception as e:
        print('Error', method, url, e)

print('\nProbe complete')
