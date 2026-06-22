import os
import sys
import requests

def main():
    tenant = os.environ["AZURE_TENANT_ID"]
    client = os.environ["AZURE_CLIENT_ID"]
    secret = os.environ["AZURE_CLIENT_SECRET"]

    resp = requests.post(
        "https://login.microsoftonline.com/{}/oauth2/v2.0/token".format(tenant),
        data={
            "grant_type": "client_credentials",
            "client_id": client,
            "client_secret": secret,
            "scope": "https://graph.microsoft.com/.default",
        }
    )
    if resp.status_code != 200:
        print("Token fejl: {} {}".format(resp.status_code, resp.text), file=sys.stderr)
        sys.exit(1)
    token = resp.json()["access_token"]
    print("Token OK")

    DRIVE = "b!l3-EhhmboESLtqZs3mskwcfYgAb0uTBJtdZFBL1IqyUao41S6zySS6Rj_0KgtpbJ"
    FOLDER_ID = "01Y5SFS4EESRNSDGISBJCJQ5UURGEHA6FS"
    hdrs = {
        "Authorization": "Bearer " + token,
        "Content-Type": "application/octet-stream",
    }

    files = [
        ("data/Master_Plan.xlsx",                   "Master_Plan.xlsx"),
        ("data/Fast_as_Fifty_Masterplan_2026.docx", "Fast_as_Fifty_Masterplan_2026.docx"),
        ("data/Eva_Medoc_Traningsplan_2026.docx",   "Eva_Medoc_Traningsplan_2026.docx"),
        ("data/Eva_Medoc_Master.xlsx",              "Eva_Medoc_Master.xlsx"),
    ]

    ok = err = 0
    for local, remote in files:
        if not os.path.exists(local):
            print("SKIP " + local)
            continue
        # Korrekt Graph URL: /drives/{id}/items/{folderId}:/{filename}:/content
        url = "https://graph.microsoft.com/v1.0/drives/{}/items/{}:/{}:/content".format(
            DRIVE, FOLDER_ID, remote
        )
        with open(local, "rb") as fi:
            r = requests.put(url, headers=hdrs, data=fi)
        if r.status_code in (200, 201):
            size = os.path.getsize(local)
            print("OK {} ({} bytes)".format(remote, size))
            ok += 1
        else:
            print("FAIL {}: {} {}".format(remote, r.status_code, r.text[:300]))
            err += 1

    print("Resultat: {} ok, {} fejl".format(ok, err))
    if err:
        sys.exit(1)

if __name__ == "__main__":
    main()
