import os, requests, json
key = os.getenv('BLOCKBERRY_API_KEY') or os.getenv('SUI_API_KEY') or os.getenv('BLOCKVISION_API_KEY')
base = 'https://api.blockberry.one/sui/v1'
headers = {'accept':'*/*', 'x-api-key': key, 'Content-Type':'application/json'}
cp = 199941921
page_size = 5
url = f"{base}/transactions?page=0&size={page_size}&orderBy=DESC&sortBy=AGE"
body = {"filters": [{"field": "checkpoint", "op": "eq", "value": int(cp)}], "page": 0, "size": page_size}
print('POST to', url, 'body', body)
r = requests.post(url, headers=headers, json=body, timeout=12)
print('status', r.status_code)
try:
    j = r.json()
    print('keys', list(j.keys()))
    content = j.get('content') or []
    print('len content', len(content))
    for i, tx in enumerate(content):
        print(i, 'checkpoint raw:', repr(tx.get('checkpoint')))
        print(i, 'txhash:', tx.get('txHash'))
        print(i, 'balanceChanges:', tx.get('balanceChanges'))
except Exception as e:
    print('json error', e)
    print('text snippet', (r.text or '')[:1000])
