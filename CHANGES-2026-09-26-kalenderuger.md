# 26/9-2026 — kalenderuger overalt i stedet for programuger

**Ønske (Kennet):** brug kalenderugenumre generelt — programuger (1–51) er svære at læse.

## Ændringer
- `index.html`: ny `progIso(n)` (programuge → ISO-uge, regnet fra dags dato). Bruges i Mere-fanens periodeplan (tal under hver celle), "Træningsfordeling — uge", CTL-grafens x-akse og "MÅL … (uge …)", den gamle ugevisning, kvote-tekster i ⋯-arket (fra ugens startdato), svøm-søjlernes ugetal (fra `date`). Sticky-baren viser kun "UGE 39" (ikke længere "program-uge 3/51").
- `scripts/update_kpi.py`: CTL-flisens undertekst og coach-headeren bruger kalenderugen.
- `scripts/modules/coach.py`: dagstekst og trajectory-note bruger kalenderugen; "uge X af Y" er fjernet.
- `scripts/modules/friel.py`: `_iso()` — alle flag-beskeder skriver kalenderugen. Feltet `week` i flaggene er uændret (programuge, bruges i logikken).
- `scripts/modules/adaptation.py`: fase-guard-teksten bruger kalenderugen.
- `scripts/modules/coach_context.py` + `prompts/coach_system.md`: `program.isoWeek` i konteksten og regel om kun at skrive kalenderuger.

Programugen bruges stadig internt (plan.json, CTL-mål, logik). Kun tekster på skærmen er ændret.

## Test
- pytest: 660 passed, 1 skipped · schemas/validate.py OK · node --check sw.js OK · inline scripts OK.
- `progIso`: programuge 1 → uge 37, 3 → 39, 4 → 40, 51 → 34 (2027).

## Ikke verificeret
- Visuelt på iPhone. Tekster fra pipelinen (CTL-flise, coach) skifter først ved næste update-kpi-kørsel.
