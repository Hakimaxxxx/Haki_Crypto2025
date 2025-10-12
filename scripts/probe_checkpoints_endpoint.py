import requests
key='Y1CcambMPLreF9NiuJ8JeZlfmHqpZY'
base='https://api.blockberry.one/sui/v1'
headers={'accept':'*/*','x-api-key':key}

print('Trying GET /checkpoints')
try:
    r = requests.get(f"{base}/checkpoints?page=0&size=10&orderBy=DESC&sortBy=AGE", headers=headers, timeout=10)
    print('GET status', r.status_code)
    try:
        j=r.json()
        print('GET keys', list(j.keys()) if isinstance(j,dict) else type(j))
    except Exception as e:
        print('GET json err', e, (r.text or '')[:400])
except Exception as e:
    print('GET err', e)

print('\nTrying POST /checkpoints no body')
try:
    r2 = requests.post(f"{base}/checkpoints?page=0&size=10&orderBy=DESC&sortBy=AGE", headers=headers, timeout=10)
    print('POST status', r2.status_code)
    try:
        j2=r2.json()
        print('POST keys', list(j2.keys()) if isinstance(j2,dict) else type(j2))
    except Exception as e:
        print('POST json err', e, (r2.text or '')[:400])
except Exception as e:
    print('POST err', e)

print('\nTrying POST /checkpoints with body')
try:
    body={'page':0,'size':10}
    r3 = requests.post(f"{base}/checkpoints", headers={**headers,'Content-Type':'application/json'}, json=body, timeout=10)
    print('POST body status', r3.status_code)
    try:
        j3=r3.json()
        print('POST body keys', list(j3.keys()) if isinstance(j3,dict) else type(j3))
    except Exception as e:
        print('POST body json err', e, (r3.text or '')[:400])
except Exception as e:
    print('POST body err', e)
