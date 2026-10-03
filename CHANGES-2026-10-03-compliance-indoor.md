# Compliance: TSS farves på indendørs cykelpas (3/10-2026)

Lørdagens pas hedder "Cykel Z2 90 min Mallorca", men Kennet kørte det indendørs (Zwift, aktivitet "75m Z2"). Reglen fra 30/9 læste "Mallorca" i pasnavnet og gjorde TSS-procenten grå. Indendørs skal TSS bedømmes.

## Ændringer
- `index.html` (`complianceHtml`): findes aktivitetens navn (`actual_name`), afgør det alene — "Fornalutx" = udendørs, TSS-procent uden farve. "Mallorca" i pasnavnet bruges kun, før en aktivitet findes (planlagte pas).
- Ingen ændring i pipeline, plan.json eller skemaer.

## Effekt på ugen (data.json 3/10 08:26)
- Man, Ons, Tor (Fornalutx Cykling på vej): TSS uden farve som før.
- Lør (75m Z2): TSS 63/63 = 100 % farves grøn.

## Test
- pytest 675 bestået, 1 sprunget over; `schemas/validate.py` OK; `node --check sw.js` OK; index.html inline-scripts OK.
- Reglen kørt i node mod live data.json.

## Ikke verificeret
- Ikke set gengivet på telefon. `pywebpush` kunne ikke bygges i sandkassen; testene kørte uden.
