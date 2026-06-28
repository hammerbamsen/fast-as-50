import os, requests, sys, json, subprocess

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
    result = f'TOKEN FEJL: {r.status_code} {r.text[:200]}'
    print(result)
    sys.exit(1)
token = r.json()['access_token']

with open('data/about-me.md', 'rb') as f:
    content = f.read()

drive_id = 'b!l3-EhhmboESLtqZs3mskwcfYgAb0uTBJtdZFBL1IqyUao41S6zySS6Rj_0KgtpbJ'
item_id = '01Y5SFS4DAHA6BW32YAJA3DSKD74JVC5EW'

hdrs = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/octet-stream'}
url = f'https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{item_id}/content'

r2 = requests.put(url, headers=hdrs, data=content)

lines = []
lines.append(f'HTTP Status: {r2.status_code}')
lines.append(f'Fil bytes: {len(content)}')
lines.append(f'Har Regel 1: {b"Regel 1" in content}')
try:
    d = r2.json()
    lines.append(f'id: {d.get("id", "N/A")}')
    lines.append(f'name: {d.get("name", "N/A")}')
    lines.append(f'size: {d.get("size", "N/A")}')
    lines.append(f'lastModified: {d.get("lastModifiedDateTime", "N/A")}')
    lines.append(f'webUrl: {d.get("webUrl", "N/A")}')
    if 'parentReference' in d:
        lines.append(f'parent path: {d["parentReference"].get("path", "N/A")}')
    if 'error' in d:
        lines.append(f'ERROR: {json.dumps(d["error"])}')
except Exception as e:
    lines.append(f'Parse error: {e}')
    lines.append(f'Raw: {r2.text[:500]}')

output = '\n'.join(lines)
print(output)

# Skriv til debug-output fil via GitHub API
import base64 as b64

gh_token = os.environ.get('GITHUB_TOKEN', '')
if gh_token:
    output_content = b64.b64encode(output.encode()).decode()
    # Hent eksisterende SHA hvis filen findes
    rg = requests.get(
        'https://api.github.com/repos/hammerbamsen/fast-as-50/contents/data/debug_upload_result.txt',
        headers={'Authorization': f'token {gh_token}'}
    )
    payload = {
        'message': 'debug: upload result',
        'content': output_content
    }
    if rg.status_code == 200:
        payload['sha'] = rg.json()['sha']
    
    rp = requests.put(
        'https://api.github.com/repos/hammerbamsen/fast-as-50/contents/data/debug_upload_result.txt',
        headers={'Authorization': f'token {gh_token}'},
        json=payload
    )
    print(f'GitHub write: {rp.status_code}')
