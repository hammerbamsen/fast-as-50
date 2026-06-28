import os, requests, sys, json, base64 as b64

r = requests.post(
    'https://login.microsoftonline.com/' + os.environ['AZURE_TENANT_ID'] + '/oauth2/v2.0/token',
    data={
        'grant_type': 'client_credentials',
        'client_id': os.environ['AZURE_CLIENT_ID'],
        'client_secret': os.environ['AZURE_CLIENT_SECRET'],
        'scope': 'https://graph.microsoft.com/.default'
    }
)
if r.status_code != 200:
    print('TOKEN FEJL:', r.status_code, r.text[:200])
    sys.exit(1)
token = r.json()['access_token']

# Decode JWT claims (middle part) for at se roller
import json as _json
parts = token.split('.')
if len(parts) >= 2:
    padding = 4 - len(parts[1]) % 4
    padded = parts[1] + '=' * padding
    claims = _json.loads(b64.b64decode(padded).decode('utf-8', errors='replace'))
    print('Token roles:', claims.get('roles', []))
    print('Token scp:', claims.get('scp', 'N/A'))
    print('Token oid:', claims.get('oid', 'N/A')[:8])

drive_id = 'b!l3-EhhmboESLtqZs3mskwcfYgAb0uTBJtdZFBL1IqyUao41S6zySS6Rj_0KgtpbJ'
item_id = '01Y5SFS4DAHA6BW32YAJA3DSKD74JVC5EW'
auth = {'Authorization': f'Bearer {token}'}

# TEST 1: GET item metadata
print('\n--- TEST 1: GET item metadata ---')
rg = requests.get(
    f'https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{item_id}',
    headers=auth
)
print(f'GET status: {rg.status_code}')
if rg.status_code == 200:
    d = rg.json()
    print(f'  name: {d.get("name")}')
    print(f'  size: {d.get("size")}')
    print(f'  lastModified: {d.get("lastModifiedDateTime")}')
else:
    print(f'  Error: {rg.text[:300]}')

# TEST 2: GET drive root
print('\n--- TEST 2: GET drive info ---')
rd = requests.get(
    f'https://graph.microsoft.com/v1.0/drives/{drive_id}',
    headers=auth
)
print(f'Drive GET status: {rd.status_code}')
if rd.status_code == 200:
    d = rd.json()
    print(f'  name: {d.get("name")}')
    print(f'  owner: {d.get("owner",{}).get("user",{}).get("displayName")}')
else:
    print(f'  Error: {rd.text[:200]}')

# TEST 3: PUT med lille test-indhold
print('\n--- TEST 3: PUT lille test ---')
with open('data/about-me.md', 'rb') as f:
    content = f.read()
rp = requests.put(
    f'https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{item_id}/content',
    headers={**auth, 'Content-Type': 'application/octet-stream'},
    data=content
)
print(f'PUT status: {rp.status_code}')
try:
    d = rp.json()
    if 'error' in d:
        print(f'  Error code: {d["error"].get("code")}')
        print(f'  Error msg: {d["error"].get("message")}')
        inner = d['error'].get('innerError', {})
        print(f'  Inner: {inner}')
    else:
        print(f'  OK name: {d.get("name")}')
        print(f'  OK size: {d.get("size")}')
        print(f'  OK modified: {d.get("lastModifiedDateTime")}')
except:
    print(f'  Raw: {rp.text[:300]}')

# Skriv resultat til fil
lines = [
    f'GET_STATUS={rg.status_code}',
    f'PUT_STATUS={rp.status_code}',
    f'DRIVE_STATUS={rd.status_code}',
]
output = '\n'.join(lines)

gh_token = os.environ.get('GITHUB_TOKEN', '')
if gh_token:
    enc = b64.b64encode(output.encode()).decode()
    rexist = requests.get(
        'https://api.github.com/repos/hammerbamsen/fast-as-50/contents/data/debug_upload_result.txt',
        headers={'Authorization': f'token {gh_token}'}
    )
    payload = {'message': 'debug: result', 'content': enc}
    if rexist.status_code == 200:
        payload['sha'] = rexist.json()['sha']
    requests.put(
        'https://api.github.com/repos/hammerbamsen/fast-as-50/contents/data/debug_upload_result.txt',
        headers={'Authorization': f'token {gh_token}'},
        json=payload
    )
    print('\nResult written to GitHub')
