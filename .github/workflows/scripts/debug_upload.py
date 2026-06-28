import os, requests, sys, json

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

with open('data/about-me.md', 'rb') as f:
    content = f.read()
print(f'Fil: {len(content)} bytes, Regel 1 present:', b'Regel 1' in content)

drive_id = 'b!l3-EhhmboESLtqZs3mskwcfYgAb0uTBJtdZFBL1IqyUao41S6zySS6Rj_0KgtpbJ'
item_id = '01Y5SFS4DAHA6BW32YAJA3DSKD74JVC5EW'

hdrs = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/octet-stream'}
url = f'https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{item_id}/content'
print('URL:', url)
r2 = requests.put(url, headers=hdrs, data=content)
print('HTTP Status:', r2.status_code)
try:
    d = r2.json()
    print('Response JSON:')
    print('  id:', d.get('id'))
    print('  name:', d.get('name'))
    print('  size:', d.get('size'))
    print('  lastModified:', d.get('lastModifiedDateTime'))
    print('  webUrl:', d.get('webUrl'))
    if 'parentReference' in d:
        print('  parent path:', d['parentReference'].get('path'))
    if 'error' in d:
        print('  ERROR:', d['error'])
except Exception as e:
    print('Response text:', r2.text[:400])
    print('Parse error:', e)
