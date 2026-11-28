# 28/11-2026 — En dublet-anmodning skal ikke farve systemkortet rødt

## Hvad der skete

Kl. 12:53 blev forslaget `2026-11-28-hegnet-c-loeb` anvendt: gate ok, plan.json committet
(`cabd054`). Kl. 12:58 kom endnu en `plan-edit`-dispatch med samme forslag. Det var nu
`accepted`, så `edit_apply.apply_edit` kastede
`ValueError: Forslag ... er allerede afgjort (accepted)`.

`scripts/apply_edit.py` fangede den ikke. Resultatet:

- traceback → rc=1 → rød kørsel (10 sek., run 46147229859),
- intet `edit_result`-opslag, så klienten pollede forgæves og endte i timeout,
- "⚠ SYSTEM: 1 WORKFLOW FEJLER" på dashboardets I dag-side for en anmodning, der i praksis
  bare var overflødig. Ingen data manglede.

## Rettelsen

`scripts/apply_edit.py` — kaldet til `edit_apply.apply_edit` pakkes i `try/except ValueError`.
`ValueError` er modulets måde at sige "ugyldig anmodning" på (ukendt entryId, afgjort forslag,
dårlige params), og bliver nu et almindeligt `status: "reject"` i `edit_result.json` med
undtagelsens tekst som `gate.msg`. Kørslen bliver grøn, og appen viser "Afvist: Forslag … er
allerede afgjort (accepted)" i stedet for en timeout.

Grænsen er bevidst: kun `ValueError`. `KeyError`, `TypeError` og netværksfejl fælder stadig
kørslen, så ægte kodefejl stadig bliver røde i systemkortet.

`gate.flags` sættes til en tom liste. `ptGateFlags` i `index.html` forventer objekter
`{level, rule, msg}`; en streng som `"invalid_request"` ville have renderet "undefined".

## Tests

Ny fil `scripts/test_apply_edit_entry.py` (orkestratoren havde ingen tests):

- afgjort forslag → `main()` kaster ikke, skriver `status: "reject"`, rører ikke planen
  (intet `plan_commit`), `flags == []`,
- `KeyError` fra samme kald → `main()` fælder stadig kørslen.

Alle fire CI-trin kørt lokalt: 817 passed, 1 skipped · skemaer OK · `sw.js` OK ·
index.html's tre inline-scripts OK.

## Ikke verificeret

Run-loggen for 46147229859 er ikke læst — GitHub Actions' API var lukket i sessionen.
Diagnosen bygger på `health.json`, `edit_result.json` og koden: kørslens varighed (10 sek.),
det manglende `edit_result`-opslag og den accepterede forslagsfil peger alle samme vej.
Hvem der sendte dubletten (app-genkald eller en gentaget dispatch) står stadig åbent.
Banneret forsvinder, når `plan-edit` kører grønt næste gang.

## Efterspil — rød CI på første push (da9bf3d)

Testen bestod lokalt og faldt i CI: `scripts/apply_edit.py` importerer `word_master`, som
importerer `python-docx` på modulniveau og bygger `RGBColor`-konstanter med det samme. CI
installerer kun pytest, requests, pywebpush og jsonschema. Testen stubber nu `docx` i
`sys.modules`, når pakken mangler — bedre end at skippe testen, som så aldrig ville køre i CI.

Første stub-forsøg (`5c80af8`) var også rødt, og min lokale efterligning af CI var skyld i
begge: en `meta_path`-finder der returnerer `None` blokerer ikke noget — importsystemet går
bare videre til næste finder og fandt den rigtige pakke. Den skjulte to fejl: stubbene var
`object` og kunne ikke kaldes med argumenter, og stub-modulerne manglede `__spec__`, så
`find_spec` kastede i test nummer to. Rettet med kaldbare stubs (metaclass, så
`WD_ALIGN_VERTICAL.CENTER` også virker) og rigtige `ModuleSpec`'s.

Verifikationen er nu et rent virtuelt miljø med præcis CI's fire pakker: **818 passed**, ingen
python-docx installeret.
