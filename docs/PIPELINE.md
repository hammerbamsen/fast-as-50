# Pipeline — hvad kører, hvornår, og hvor fejl bliver synlige

Opdateret 7/9-2026 (blok 7). Læs denne side før du ændrer noget under `.github/workflows/`.

## Overblik

Dashboardet (`index.html`, PWA på hammerbamsen.github.io/fast-as-50) er ren læser. Al data skrives af GitHub Actions: `scripts/update_kpi.py` henter Intervals.icu (fitness, wellness, aktiviteter) og AI-coach-tekst, og skriver `data.json` i repo-roden via GitHub Contents API (`modules/github.gh_put` — retry, backoff, frisk SHA ved 409/422). Samme kørsel opdaterer `data/plan_view.json` (Friel-flags, CTL-projektion, readiness). Klientsiderne (index/af/checkin/plan/eva) taler aldrig direkte med GitHub — de kalder Cloudflare Worker'en (`workers/webhook-dispatch/`), som som GitHub App udløser `repository_dispatch`-events. Intervals.icu's aktivitets-webhook går samme vej, så en ny aktivitet står i `data.json` inden for ~10 sekunder.

Planen bor i `data/plan.json` (programmer → uger → dage → entries). Søndag bygger `build-workouts.yml` ugens pas i Intervals.icu og kalder derefter Outlook-synk som `workflow_call`. Kælderpas kommer altid fra `data/bike_library.json` via `libraryId` på entry'en.

## Workflows

| Workflow (`name:`) | Trigger | Skriver | Secrets |
|---|---|---|---|
| Daglig dashboard-opdatering (`update-kpi.yml`) | cron `*/30` + faste `04:30`/`05:15` UTC (morgen, hvor Garmin har synket HRV); manuelt | `data.json`, `data/plan_view.json` (Contents API) | INTERVALS_API_KEY, INTERVALS_ATHLETE_ID, ANTHROPIC_API_KEY, GITHUB_TOKEN |
| Intervals Webhook Receiver (`webhook-receiver.yml`) | `repository_dispatch: intervals-activity` (Worker: Intervals-webhook + OPDATÉR-knap) | `data.json`, `data/plan_view.json` | som ovenfor |
| Check-in registrering (`af-registrering.yml`) | `repository_dispatch: af-registrering, checkin` (af.html / checkin.html) | Intervals wellness (PUT); ved AF også `data.json` via git push | INTERVALS_API_KEY, INTERVALS_ATHLETE_ID, ANTHROPIC_API_KEY, GITHUB_TOKEN |
| Plan-redigering (fase 3a) (`plan-edit.yml`) | `repository_dispatch: plan-edit` (plan.html / eva.html) | `data/plan.json`, Intervals-events, Outlook, masters + OneDrive (`sync_to_onedrive.py`) | INTERVALS_API_KEY, AZURE_*, GITHUB_TOKEN |
| Byg workouts i Intervals.icu (`build-workouts.yml`) | cron søndag 05:00 UTC; manuelt (`week_only`) | Intervals-events (kommende uge); kalder Outlook-synk som `workflow_call` | INTERVALS_API_KEY + Outlook-synkens |
| Sync workouts til Outlook kalender (`create-outlook-events.yml`) | `workflow_call` fra build; cron søndag 18:00 UTC; `repository_dispatch: workouts-built`; manuelt (`week` = '3', '3-17' eller 'all' — sletter og genopretter Træning-events pr. uge; tomme uger springes over ved interval) | Outlook-kalender (Graph API) | AZURE_CLIENT_ID, AZURE_TENANT_ID, AZURE_CLIENT_SECRET, INTERVALS_* |
| Regenerér Word-master fra plan.json (`regen-docx.yml`) | push på `data/plan.json` / master-moduler; cron søndag 18:00 + dagligt 04:00 UTC; manuelt | `data/*.docx`, `data/*.xlsx` (git push), OneDrive | AZURE_*, GITHUB_TOKEN |
| Send daglig push-påmindelse (`send-push.yml`) | cron 05:00 (dagens pas) + 17:00 UTC (AF-nudge); manuelt | Web push til Kennet/Eva; rydder døde subscriptions i det private repo | VAPID_PRIVATE, VAPID_SUBJECT, PRIVATE_REPO, FAF_APP_ID + FAF_APP_PRIVATE_KEY (fallback PRIVATE_REPO_TOKEN), GITHUB_TOKEN |
| Modtag push-subscription (`push-subscribe.yml`) | `repository_dispatch: push-subscribe` (Worker) | `push_subscriptions.json` i det private repo | PRIVATE_REPO, FAF_APP_ID + FAF_APP_PRIVATE_KEY (fallback PRIVATE_REPO_TOKEN) |
| Sæt zoner i Intervals.icu (fra plan.json) (`set-zones.yml`) | manuelt (dry_run default) | Intervals-zoner, `data/zone_sync.json` | INTERVALS_API_KEY |
| Slet Outlook event (`delete-outlook-event.yml`) | manuelt (dato + subject) | Outlook-kalender | AZURE_* |
| CI — pytest (`ci-pytest.yml`) | alle push til main, alle PR'er | intet | ingen |
| Workflow-sundhed (`health.yml`) | `workflow_run: completed` for alle ovenstående; manuelt | `health.json` (Contents API); push-alert ved fejl | GITHUB_TOKEN + push-secrets (kun ved fejl) |

Slettet 7/9-2026 (blok 7): `debug-bike-ef.yml`, `debug-subs.yml`, `onedrive-reorg.yml`, `create-reminder.yml`, `sync-onedrive.yml` og deres scripts, samt mappen `debug/` (ingen workflow skriver længere debug-filer til repoet — output står i run-loggen).

## CI — hvad der tjekkes på hvert push

`ci-pytest.yml` kører fire trin: (a) `pytest scripts/modules/ scripts/test_health_report.py`, (b) `python3 schemas/validate.py` — `data/plan.json`, `data/bike_library.json` og `data.json` mod skemaerne i `schemas/` (kun de felter koden reelt læser; `additionalProperties: true`), (c) `node --check sw.js`, (d) `node --check` på hver inline `<script>` i `index.html`. Skemaerne er kontrakter: bryder en ændring dem, skal skemaet opdateres bevidst i samme commit.

## Sådan bliver fejl synlige

1. **health.json → System-kortet.** `health.yml` kører efter hver afsluttet kørsel og skriver `workflows[<navn>] = {lastRun, conclusion, event, runUrl, durationS, expectedEveryMin?}` samt `secrets` (App-token uden udløb, eller PAT'ens `expires`) og `generatedAt`. Dashboardets System-kort (Mere-fanen) læser filen med `cache: 'no-store'` og regner selv: grøn = success og ikke forældet, rød = failure/timed_out, gul = cancelled eller `lastRun` ældre end 2× `expectedEveryMin`, grå = aldrig kørt. Data-alder fra `data.json meta.updated`: grøn < 60 min, gul 60–180, rød > 180. Secret-udløb: grøn > 21 dage, gul ≤ 21, rød ≤ 7 eller udløbet.
2. **Push ved fejl.** Er `conclusion` hverken `success` eller `skipped`, sender `health_report.py` én notifikation til Kennet via `scripts/send_push.py --alert` (tag `fast50-alert`, renotify, link `./#more`). Fejler pushen, fejler health-kørslen ikke — kun en mislykket skrivning af `health.json` giver exit 1.
3. **Run-loggen** i Actions er stadig kilden til detaljer. `runUrl` i health.json peger direkte derhen.
4. `update_kpi.py` afbryder med exit 1 hvis `gh_put data.json` fejler, så en tavs "grøn men skrev ikke"-kørsel ikke kan opstå.

Begrænsninger: `workflow_run` fyrer kun når `health.yml` ligger på `main`, og GitHub throttler `schedule`-crons hårdt (`*/30` betyder i praksis 1–2 timer, nogle nætter 4+). Derfor `expectedEveryMin: 60` for dashboard-opdateringen og de to faste morgen-crons.

## Nøgler til det private repo

De tre workflows der rører `fast-as-50-private` (`send-push.yml`, `push-subscribe.yml`, `health.yml`) minter siden 9/9-2026 selv et **GitHub App-installation-token** pr. kørsel med `actions/create-github-app-token@v2` — samme app som Cloudflare Worker'en (App ID 4259031, se `workers/webhook-dispatch/README.md`). Tokenet lever en time; der er intet at forny.

Fallback: mangler `FAF_APP_ID`/`FAF_APP_PRIVATE_KEY`, springes token-steppet over (`HAS_APP` på job-niveau) og den gamle PAT `PRIVATE_REPO_TOKEN` bruges i stedet. Workflowet sætter `PRIVATE_REPO_AUTH` til `app` eller `pat`, og `health_report.secrets_for()` skriver derefter enten "GitHub App (privat repo)" uden udløb eller PAT'ens nedtælling til `health.json`. Opsætning og oprydning: `docs/PAT_RENEWAL.md`.
