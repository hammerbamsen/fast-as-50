# 26/9-2026 — styrkekortet flyttet fra Plan til Mere

**Ønske (Kennet):** kortet "Styrke · Næste" fyldte nederst i Plan-fanen. Det skal ligge i Mere.

## Ændringer
- `index.html`: `renderPlan()` viser ikke længere `strengthCardHtml()` (hverken i planTab- eller fallback-visningen). `renderMore()` viser kortet under "Træning", efter oversigten. Kortet er uændret; check-in-kortet og "Dagens styrke" i I dag er uændrede.

## Test
- pytest: 660 passed, 1 skipped · schemas/validate.py OK · node --check sw.js OK · inline scripts i index.html OK.

## Ikke verificeret
- Visuelt på iPhone (ingen browser i sandkassen).
