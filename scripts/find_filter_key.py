import os, requests
key = os.getenv('BLOCKBERRY_API_KEY') or os.getenv('SUI_API_KEY') or os.getenv('BLOCKVISION_API_KEY')
base = 'https://api.blockberry.one/sui/v1'
headers = {'accept':'*/*', 'x-api-key': key, 'Content-Type': 'application/json'}
# pick a recent checkpoint from /transactions
r = requests.post(f"{base}/transactions?page=0&size=1&orderBy=DESC&sortBy=AGE", headers=headers, timeout=10)
j = r.json()
cp = j.get('content')[0].get('checkpoint')
print('target checkpoint', cp)
page_size = 10
candidates = []
# simple
candidates.append({'checkpoint': cp, 'page': 0, 'size': page_size})
candidates.append({'checkpointNumber': cp, 'page': 0, 'size': page_size})
candidates.append({'checkpointSequence': cp, 'page': 0, 'size': page_size})
candidates.append({'checkpoint_seq': cp, 'page': 0, 'size': page_size})
# filters wrappers
candidates.append({'filters': [{'field': 'checkpoint', 'op': 'eq', 'value': cp}], 'page': 0, 'size': page_size})
candidates.append({'filters': [{'field': 'checkpointNumber', 'op': 'eq', 'value': cp}], 'page': 0, 'size': page_size})
candidates.append({'filters': [{'field': 'checkpointSequence', 'op': 'eq', 'value': cp}], 'page': 0, 'size': page_size})
candidates.append({'filter': {'checkpoint': cp}, 'page': 0, 'size': page_size})
candidates.append({'where': {'checkpoint': cp}, 'page': 0, 'size': page_size})
candidates.append({'queries': [{'name': 'checkpoint', 'value': cp}], 'page': 0, 'size': page_size})
candidates.append({'checkpointNumber': str(cp), 'page': 0, 'size': page_size})

url = f"{base}/transactions?page=0&size={page_size}&orderBy=DESC&sortBy=AGE"

for i, body in enumerate(candidates):
    r = requests.post(url, headers=headers, json=body, timeout=10)
    ok = r.status_code
    print('\n', i, 'body', body, 'status', ok)
    try:
        j = r.json()
        content = j.get('content') or []
        print(' content len', len(content))
        match = False
        for tx in content:
            if int(tx.get('checkpoint') or 0) == int(cp):
                match = True
                print('  FOUND matching tx hash', tx.get('txHash'))
                break
        print('  matched?', match)
    except Exception as e:
        print(' json err', e, (r.text or '')[:300])

print('\nDone')
