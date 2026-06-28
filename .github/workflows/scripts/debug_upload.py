import os, requests, sys, json, base64 as b64

r = requests.post(
    'https://login.microsoftonline.com/' + os.environ['AZURE_TENANT_ID'] + '/oauth2/v2.0/token',
    data={'grant_type':'client_credentials','client_id':os.environ['AZURE_CLIENT_ID'],
          'client_secret':os.environ['AZURE_CLIENT_SECRET'],'scope':'https://graph.microsoft.com/.default'}
)
if r.status_code != 200:
    print('TOKEN FEJL:', r.status_code); sys.exit(1)
token = r.json()['access_token']

# Decode roles
parts = token.split('.')
padding = 4 - len(parts[1]) % 4
claims = json.loads(b64.b64decode(parts[1] + '='*padding).decode('utf-8','replace'))
print('Token roles:', claims.get('roles', []))

with open('data/about-me.md', 'rb') as f:
    content = f.read()
print(f'Fil: {len(content)} bytes')

drive_id = 'b!l3-EhhmboESLtqZs3mskwcfYgAb0uTBJtdZFBL1IqyUao41S6zySS6Rj_0KgtpbJ'
folder_id = '01Y5SFS4HMOISMIYAKQBBLUE3OBQAYJVB6'  # About me undermappe
auth = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/octet-stream'}

# TEST: mappe-item-ID format (samme som xlsx)
url = f'https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{folder_id}:/about-me.md:/content'
print('URL:', url[:80])
rp = requests.put(url, headers=auth, data=content)
print('PUT status:', rp.status_code)
try:
    d = rp.json()
    if 'error' in d:
        print('ERROR code:', d['error'].get('code'))
        print('ERROR msg:', d['error'].get('message'))
    else:
        print('OK! name:', d.get('name'))
        print('OK! size:', d.get('size'))
        print('OK! id:', d.get('id'))
        print('OK! modified:', d.get('lastModifiedDateTime'))
except Exception as e:
    print('Raw:', rp.text[:300])

# Skriv til result
result = f'FOLDER_PUT={rp.status_code}'
gh = os.environ.get('GITHUB_TOKEN','')
if gh:
    enc = b64.b64encode(result.encode()).decode()
    rexist = requests.get('https://api.github.com/repos/hammerbamsen/fast-as-50/contents/data/debug_upload_result.txt',
                          headers={'Authorization': f'token {gh}'})
    payload = {'message':'debug result','content':enc}
    if rexist.status_code==200: payload['sha']=rexist.json()['sha']
    requests.put('https://api.github.com/repos/hammerbamsen/fast-as-50/contents/data/debug_upload_result.txt',
                 headers={'Authorization':f'token {gh}'},json=payload)
