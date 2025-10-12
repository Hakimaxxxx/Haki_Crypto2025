import os, requests
key = os.getenv('BLOCKBERRY_API_KEY') or os.getenv('SUI_API_KEY') or os.getenv('BLOCKVISION_API_KEY')
base = 'https://api.blockberry.one/sui/v1'
headers = {'accept':'*/*', 'x-api-key': key, 'Content-Type': 'application/json'}
cp = 199941921
page_size = 5
max_pages = 8
for page in range(0, max_pages):
    url = f"{base}/transactions?page={page}&size={page_size}&orderBy=DESC&sortBy=AGE"
    body = {"filters": [{"field": "checkpoint", "op": "eq", "value": int(cp)}], "page": page, "size": page_size}
    r = requests.post(url, headers=headers, json=body, timeout=12)
    print('PAGE', page, 'STATUS', r.status_code)
    try:
        j = r.json()
        content = j.get('content') or []
        print('  content len', len(content))
        for i, tx in enumerate(content):
            print('   idx', i, 'checkpoint', tx.get('checkpoint'))
    except Exception as e:
        print('  json err', e, (r.text or '')[:200])

print('done')
