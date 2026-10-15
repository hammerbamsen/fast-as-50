# Ændring 15/10-2026 — dagens vejning på Krop

- `index.html`: ny `lastWeighLine()`. Krop-heroen viser nu "vejet i dag 74,0 kg · fedt 21,5 %" under 7d-snittet (eller "seneste vejning d/m" hvis der ikke er vejet i dag). Gælder cut-, hold- og pre-fasen. Kilde: `weightHistory`/`fatHistory` i data.json — ingen pipeline-ændring.
- Baggrund: Krop viste kun 7d-snit, så dagens vejning så ud til at mangle.
- Test: de fire CI-trin kørt lokalt (se commit). Ikke verificeret visuelt på telefon.
