# PAT-fornyelse

GitHub Personal Access Token'et udløber periodisk. Sådan fornyer du:

1. Gå til [GitHub Personal Access Tokens](https://github.com/settings/personal-access-tokens)
2. Find "fast-as-50 fine-grained" i listen (eller opret nyt hvis udløbet)
3. Klik **Regenerate** eller **Generate new token**
4. Indstillinger:
   - **Repository access:** kun `hammerbamsen/fast-as-50`
   - **Expiration:** 1 år frem
   - **Permissions:** Contents (Read+Write), Actions (Read+Write), Metadata (Read)
5. Copy tokenet
6. **Opdater 3 steder:**
   - `data/config.json` → felt `patExpiry` opdateres til ny udløbsdato
   - eva.html/af.html/checkin.html på iPhone → tap Token, indsæt nyt token, Gem (Safari overskriver Keychain-værdi). plan.html bruger ikke længere denne PAT — se `workers/webhook-dispatch/README.md` for dens delte hemmelighed i stedet.
   - Send til Claude → memory opdateres
