# 24/9-2026 — styrke lør 45 min, svøm fre, FTP-test 8/10 + QA

## Plan (via plan-edit, forslag `2026-09-24-styrke-lor-svom-fre-ftp`, accepted)
- Uge 39: tor 24/9 løb let 20 min, fre 25/9 fri, lør 26/9 gravel Z2 90 min ude. FTP-test flyttet til tor 8/10 (uge 41).
- Uge 41-53: styrke B fra tor til lør. Build-uger 45 min (10 min opvarmning + 3 runder, `styrke-fs4-*-3r`); recovery-uger 2 runder. Svøm fre, løb ons (undtagen 25/12 og 1/1: svøm ons).
- Gate: ok, ingen flag. Synk: ingen fejl.

## QA-rettelser (denne commit)
- `data/plan.json`: `programs.tds-2027.weeks` og `season2027.weeks` — uge 3 quota 0/0 + ny purpose/note; uge 5 quota 1/0 + purpose/note med FTP-test; purpose uge 6-17 "Løb ons, svøm fre, styrke man+lør 45 min".
- Tests der læser den rigtige plan: `test_ftp_track.test_real_plan_has_history_and_test` (test i uge 41), `test_plan_tab.test_build_plan_tab_window_spans_program_switch` (FTP-nøglepas i uge 5), `test_proposals` blok 11 (3r-skabeloner tilladt, kvoter uge 39/41).
- Første dispatch fejlede: inline-forslag på 55 KB gav "Argument list too long" i plan-edit.yml (GH_EVENT_PAYLOAD). Løst ved at committe forslagsfilen først og sende dispatch uden inline-forslag.

## Tests
660 passed, 1 skipped. Skemaer grønne. `node --check sw.js` ok.
