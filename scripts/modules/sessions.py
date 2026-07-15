"""Sessions, aktiviteter og planlagte workouts fra Intervals.icu."""
import re
from datetime import date, timedelta
from .config import (TOTAL_WEEKS, BASE, AUTH, api_get, fix_enc, fmt, color_for, ctl_plan_for_week,
                      DAY_SHORT, BLOCK_TYPES, RUN_PACE_ZONES_SEC_PER_KM)
from .af import monday_this_week


def get_activities_since(days=10):
    """Rå Intervals-aktiviteter for de seneste `days` dage (inkl. i dag).

    Bruges af T3-adaptation, som har brug for et længere vindue end
    'denne uge'. Returnerer en liste (evt. tom) — aldrig None, så
    kalderen kan skelne 'ingen aktiviteter' fra 'ikke forsøgt'.
    """
    newest = date.today()
    oldest = newest - timedelta(days=days)
    r = api_get(f'{BASE}/activities', auth=AUTH,
                params={'oldest': str(oldest), 'newest': str(newest)})
    if r is not None and r.status_code == 200:
        try:
            return r.json()
        except Exception:
            return []
    return []


def get_activities_week():
    """TSS, løbe-km og done-sessioner fra mandag denne uge.
    Primær kilde: /activities (importerede Garmin-aktiviteter).
    Fallback: /events med paired_activity_id — fanger workouts markeret done
    i Intervals selv om Garmin-sync er forsinket."""
    monday = monday_this_week()
    today  = date.today()
    r = api_get(f'{BASE}/activities', auth=AUTH,
                     params={'oldest': str(monday), 'newest': str(today)})
    if r.status_code == 200:
        data = r.json()

        # Supplement: hent events med paired_activity_id for at fange
        # workouts der er markeret done i Intervals men endnu ikke synkroniseret
        # som aktiviteter fra Garmin
        r_ev = api_get(f'{BASE}/events', auth=AUTH,
                            params={'oldest': str(monday), 'newest': str(today)})
        if r_ev.status_code == 200:
            existing_ids = {a.get('id') for a in data}
            for ev in r_ev.json():
                paired_id = ev.get('paired_activity_id') or ev.get('activity_id')
                if not paired_id or paired_id in existing_ids:
                    continue
                # Hent den pågældende aktivitet direkte
                r_act = api_get(f'{BASE}/activities/{paired_id}', auth=AUTH)
                if r_act.status_code == 200:
                    act = r_act.json()
                    if act.get('id') not in existing_ids:
                        data.append(act)
                        existing_ids.add(act.get('id'))
                        print(f"  Fallback aktivitet hentet: {act.get('name')} ({act.get('type')})")
        print(f"  Aktiviteter denne uge: {len(data)}")
        for _a in data:
            print(f"    {_a.get('start_date_local','')[:16]} | {_a.get('type')} | {_a.get('name')} | "
                  f"moving={_a.get('moving_time')}s | icu_training_load={_a.get('icu_training_load')} | "
                  f"training_load={_a.get('training_load')}")
        total_tss = sum(a.get('icu_training_load') or a.get('training_load') or 0 for a in data)
        run_km = sum(
            (a.get('distance') or 0) / 1000
            for a in data
            if a.get('type') in ['Run', 'TrailRun', 'VirtualRun', 'IndoorRun']
        )
        bike_km = sum(
            (a.get('distance') or 0) / 1000
            for a in data
            if a.get('type') in ['Ride', 'VirtualRide', 'MountainBike', 'Cyclocross', 'Gravel', 'GravelRide']
        )
        # Træningstimer per type (i minutter)
        def mins(a): return round((a.get('moving_time') or a.get('elapsed_time') or 0) / 60, 0)
        def disc_of(a):
            t = a.get('type', '')
            if t in ['Ride','VirtualRide'] and a.get('commute'): return 'commute'
            if t in ['Run','TrailRun','VirtualRun','IndoorRun']:             return 'run'
            if t in ['Ride','VirtualRide','MountainBike','Cyclocross','Gravel','GravelRide']:       return 'bike'
            if t in ['Swim']:                                    return 'swim'
            if t in ['OpenWaterSwim']:                           return 'openwater'
            if t in ['Walk']:                                    return 'walk'
            if t in ['Hike']:                                    return 'hike'
            if t in ['WeightTraining','Workout','Strength','Yoga']: return 'strength'
            return 'free'
        train_mins = {}
        for a in data:
            d = disc_of(a)
            train_mins[d] = round(train_mins.get(d, 0) + mins(a), 0)
        # Fjern nul-værdier
        train_mins = {k: v for k, v in train_mins.items() if v > 0}
        # Byg done-map: {dag_short: [disc, ...]}
        done_map = {}
        for a in data:
            act_date = a.get('start_date_local', '')[:10]
            if not act_date:
                continue
            try:
                d = date.fromisoformat(act_date)
                day_idx = d.weekday()  # 0=Man
                day_key = DAY_SHORT[day_idx]
            except:
                continue
            atype = a.get('type', '')
            if atype in ['Ride','VirtualRide'] and a.get('commute'):
                disc = 'commute'
            elif atype in ['Run','TrailRun','VirtualRun','IndoorRun']:
                disc = 'run'
            elif atype in ['Ride','VirtualRide','MountainBike','Cyclocross','Gravel','GravelRide']:
                disc = 'bike'
            elif atype in ['Swim']:
                disc = 'swim'
            elif atype in ['OpenWaterSwim']:
                disc = 'openwater'
            elif atype in ['Walk']:
                disc = 'walk'
            elif atype in ['Hike']:
                disc = 'hike'
            elif atype in ['WeightTraining','Workout','Strength','Yoga']:
                disc = 'strength'
            else:
                disc = 'free'
            _tss      = round(a.get('icu_training_load') or a.get('training_load') or 0)
            _dur_secs = a.get('moving_time') or a.get('elapsed_time') or 0
            _dur_mins = round(_dur_secs / 60)
            # Zone-data til compliance-vurdering
            _compliance   = a.get('compliance')
            _pace_zt      = a.get('pace_zone_times')    # løb
            _power_zt     = a.get('icu_zone_times')     # cykel (list of {id, secs})
            _hr_zt        = a.get('icu_hr_zone_times')  # alle
            done_map.setdefault(day_key, []).append((
                a.get('start_date_local',''), disc, a.get('name') or atype, _tss, _dur_mins,
                _compliance, _pace_zt, _power_zt, _hr_zt, a.get('id')
            ))

        # Sortér efter tidspunkt og behold disc-navne + aktivitetsnavne
        for k in done_map:
            sorted_acts = sorted(done_map[k], key=lambda x: x[0])
            done_map[k] = [(disc, name, tss, dur_mins, compliance, pace_zt, power_zt, hr_zt, act_id)
                           for _, disc, name, tss, dur_mins, compliance, pace_zt, power_zt, hr_zt, act_id in sorted_acts]

        swim_m = sum(
            (a.get('distance') or 0)
            for a in data
            if a.get('type') in ['Swim', 'OpenWaterSwim']
        )
        return {
            'tss_week': round(total_tss, 0),
            'run_km':   round(run_km, 1),
            'bike_km':  round(bike_km, 1),
            'swim_m':   round(swim_m, 0),
            'train_mins': train_mins,
            'done_map': done_map,
        }
    return None

def compute_run_pace_zone_secs(act_id):
    """Beregn sek. pr. Friel-zone (Z1-Z6, i den rækkefølge) for en løbeaktivitet
    ud fra rå pace-stream (velocity_smooth), IKKE Intervals.icu's egen
    pace_zone_times -- da ICU's generiske %-tabel ikke matcher Kennets
    Friel-grænser for Z3 og opefter (bug fundet + verificeret 2/7-26).
    Returnerer [] hvis stream ikke kan hentes (fx svøm eller manglende GPS)."""
    if not act_id:
        return []
    r = api_get(f'https://intervals.icu/api/v1/activity/{act_id}/streams',
                auth=AUTH, params={'types': 'time,velocity_smooth'})
    if not r or r.status_code != 200:
        return []
    try:
        streams = {s['type']: s.get('data', []) for s in r.json()}
    except Exception:
        return []
    vel = streams.get('velocity_smooth') or []
    if not vel:
        return []
    zone_order = ['Z1', 'Z2', 'Z3', 'Z4', 'Z5', 'Z6']
    secs = [0, 0, 0, 0, 0, 0]
    for v in vel:
        if not v or v <= 0:
            continue
        pace = 1000.0 / v  # sek/km
        for i, z in enumerate(zone_order):
            lo, hi = RUN_PACE_ZONES_SEC_PER_KM[z]
            if lo <= pace <= hi:
                secs[i] += 1
                break
    return secs


def get_workout_compliance_this_week(events_this_week, activities_this_week):
    """Beregner zone-compliance for hvert planlagt workout denne uge.

    Matcher planlagte events med faktiske aktiviteter via paired_activity_id,
    og ekstraherer zone-fordeling (pace/power/HR) pr. disciplin.

    Returnerer liste af dicts:
      {
        'day':         str,    # 'Tir'
        'date':        str,    # '2026-06-23'
        'label':       str,    # 'Løb Z2 45 min'
        'disc':        str,    # 'run'
        'planned_zone': str,   # 'Z2'
        'intervals_compliance': float,  # 104.3 (Intervals' egen score, 0 = ikke paired)
        'zone_pct':    float,  # 14.7 (% tid i target zone)
        'hr_z1_pct':   float,  # 97.9 (% tid i HR-Z1, nyttigt for drift-vurdering)
        'hr_z2plus_pct': float, # 2.1 (% tid i HR-Z2+, viser faktisk HR-intensitet)
        'zone_flag':   str,    # 'ok' / 'under' / 'over' / 'no_data'
        'metric':      str,    # 'pace' / 'power' / 'hr'
        'moving_mins': float,  # 47
        'planned_mins': float, # 45
        'note':        str,    # Coach-fortolkning
      }
    """
    TYPE_MAP = {
        'Run': 'run', 'TrailRun': 'run', 'VirtualRun': 'run', 'IndoorRun': 'run',
        'Ride': 'bike', 'VirtualRide': 'bike', 'MountainBike': 'bike',
        'Cyclocross': 'bike', 'Gravel': 'bike', 'GravelRide': 'bike',
        'Swim': 'swim', 'OpenWaterSwim': 'swim',
        'WeightTraining': 'strength', 'Workout': 'strength', 'Strength': 'strength',
    }
    DAY_SHORT_LOCAL = ["Man", "Tir", "Ons", "Tor", "Fre", "Lør", "Søn"]

    # Byg lookup: activity_id -> aktivitet
    act_by_id = {a.get('id'): a for a in (activities_this_week or [])}
    # Byg lookup: (dato, disc) -> aktivitet (fallback)
    # Pendlingsture holdes UDE: de er ikke dagens planlagte pas. Uden det her
    # bliver en 12-min pendlertur limet på et 80-min hometrainer-pas og vist
    # som "15% gennemfoert" — passet ser brugt ud foer det er koert.
    # (Beskyttelsen i paired-grenen nedenfor rammer ikke her, fordi Intervals
    #  ikke har sat paired_event_id paa en fritstaaende pendlertur.)
    act_by_date_disc = {}
    for a in (activities_this_week or []):
        if a.get('commute') or (a.get('sub_type') or '').upper() == 'COMMUTE':
            continue
        dt = a.get('start_date_local', '')[:10]
        disc = TYPE_MAP.get(a.get('type', ''), 'free')
        key = (dt, disc)
        if key not in act_by_date_disc:
            act_by_date_disc[key] = a

    def detect_planned_zone(event_name):
        """Udtræk planlagt zone fra workout-navn."""
        name_upper = (event_name or '').upper()
        for z in ['Z5', 'Z4', 'Z3', 'Z2', 'Z1']:
            if z in name_upper:
                return z
        if any(kw in name_upper for kw in ['INTERVAL', 'BJERG', 'VO2', 'TEMPO']):
            return 'Z4'
        if any(kw in name_upper for kw in ['RECOVERY', 'LET', 'EASY']):
            return 'Z1'
        return 'Z2'  # default

    def zone_target_floor(planned_zone, disc):
        """Mindste acceptable % tid i target zone (Friel-baseret)."""
        if planned_zone in ('Z4', 'Z5'):
            return 15   # Interval-træning: lav pct er OK (restitutionstid ml. intervals)
        if disc == 'swim':
            return 30   # Svøm: zone-måling er HR, mere spredt
        if disc == 'bike':
            return 40   # Cykel: Z2+Z3 samlet, coasting+trapper giver naturligt mere Z1
        return 55       # Løb Z2: pace er præcis nok til strikt krav

    results = []
    for ev in (events_this_week or []):
        if ev.get('category') not in ('WORKOUT', None):
            continue
        ev_type = ev.get('type', '')
        disc = TYPE_MAP.get(ev_type, 'free')
        if disc in ('free', 'strength'):
            continue  # Ingen zone-vurdering for styrke/gåtur

        ev_date = ev.get('start_date_local', '')[:10]
        ev_name = fix_enc(ev.get('name', ''))
        planned_zone = detect_planned_zone(ev_name)
        planned_secs = ev.get('moving_time') or ev.get('elapsed_time') or 0
        planned_mins = round(planned_secs / 60) if planned_secs else None

        try:
            dt = date.fromisoformat(ev_date)
            day_key = DAY_SHORT_LOCAL[dt.weekday()]
        except Exception:
            day_key = '?'

        # Find matchet aktivitet
        act = None
        paired_id = ev.get('paired_activity_id') or ev.get('activity_id')
        if paired_id and paired_id in act_by_id:
            candidate = act_by_id[paired_id]
            if candidate.get('commute') or (candidate.get('sub_type') or '').upper() == 'COMMUTE':
                # Paired aktivitet er en pendlingstur — find ikke-commute alternativ samme dag+type
                non_commute = [
                    a for a in (activities_this_week or [])
                    if a.get('start_date_local', '')[:10] == ev_date
                    and TYPE_MAP.get(a.get('type', ''), 'free') == disc
                    and not a.get('commute')
                    and (a.get('sub_type') or '').upper() != 'COMMUTE'
                ]
                if non_commute:
                    # Vælg den tidsmæssigt tætteste på eventet
                    act = non_commute[0]
                    print(f"  ⚠️ Paired aktivitet for '{ev_name}' er commute — bruger ikke-commute alternativ: '{act.get('name')}'")
                else:
                    act = candidate  # ingen alternativ fundet, brug commute som fallback
                    print(f"  ⚠️ Paired aktivitet for '{ev_name}' er commute — ingen alternativ fundet")
            else:
                act = candidate
        else:
            act = act_by_date_disc.get((ev_date, disc))

        if not act:
            results.append({
                'day': day_key, 'date': ev_date, 'label': ev_name,
                'disc': disc, 'planned_zone': planned_zone,
                'intervals_compliance': None, 'zone_pct': None,
                'hr_z1_pct': None, 'hr_z2plus_pct': None,
                'zone_flag': 'no_data', 'metric': None,
                'moving_mins': None, 'planned_mins': planned_mins,
                'note': 'Ingen matchet aktivitet fundet',
            })
            continue

        moving_time = act.get('moving_time') or act.get('elapsed_time') or 0
        moving_mins = round(moving_time / 60, 0) if moving_time else 0
        intervals_compliance = act.get('compliance')
        if intervals_compliance == 0.0:
            intervals_compliance = None  # 0.0 = ikke paired, None = ukendt

        # HR-zone data (fælles for alle discipliner)
        hr_zt = act.get('icu_hr_zone_times') or []
        total_hr = sum(hr_zt) if hr_zt else 0
        hr_z1_pct = round(hr_zt[0] / total_hr * 100, 1) if total_hr and hr_zt else None
        hr_z2plus_pct = round(sum(hr_zt[1:]) / total_hr * 100, 1) if total_hr and len(hr_zt) > 1 else None

        # Zone-kilde og beregning per disciplin
        zone_pct = None
        metric = None

        if disc == 'run':
            # Primær: rå pace-stream bucketet mod Kennets egne Friel-zoner.
            # (IKKE act['pace_zone_times'] -- ICU's generiske 7-zone %-tabel
            # matcher ikke Friel-grænserne for Z3+, se compute_run_pace_zone_secs.)
            pzt = compute_run_pace_zone_secs(act.get('id'))
            if pzt and sum(pzt) > 0:
                total_p = sum(pzt)
                if planned_zone in ('Z4', 'Z5'):
                    # Interval-zone: Z4+Z5 tælles samlet (naturlig rep-til-rep
                    # variation omkring threshold-pace er ikke "for langsomt/hurtigt")
                    zone_pct = round((pzt[3] + pzt[4]) / total_p * 100, 1)
                else:
                    z_idx = int(planned_zone[1]) - 1 if planned_zone.startswith('Z') else 1
                    zone_pct = round(pzt[z_idx] / total_p * 100, 1) if z_idx < len(pzt) else 0
                metric = 'pace'
            elif hr_zt and total_hr > 0:
                z_idx = int(planned_zone[1]) - 1 if planned_zone.startswith('Z') else 1
                if planned_zone in ('Z4', 'Z5') and z_idx + 1 < len(hr_zt):
                    zone_pct = round((hr_zt[z_idx] + hr_zt[z_idx + 1]) / total_hr * 100, 1)
                else:
                    zone_pct = round(hr_zt[z_idx] / total_hr * 100, 1) if z_idx < len(hr_zt) else 0
                metric = 'hr'

        elif disc == 'bike':
            # Primær: icu_zone_times (power)
            # Trim warmup+cooldown+coasting fra Z1 så opvarmning og nedkørsler
            # (0W frihjul, typisk på kuperede/gravel-ruter) ikke forvrænger zone-billedet
            coasting_secs = act.get('coasting_time') or 0
            moving_total = act.get('moving_time') or act.get('elapsed_time') or 0
            high_coasting = bool(moving_total and coasting_secs / moving_total > 0.10)
            pzt_raw = act.get('icu_zone_times') or []
            if pzt_raw:
                pzt = [z.get('secs', 0) for z in pzt_raw if isinstance(z, dict)]
                # Træk warmup+cooldown+coasting fra Z1 (de sidder næsten altid i Z1)
                trim_secs = (act.get('icu_warmup_time') or 0) + (act.get('icu_cooldown_time') or 0) + coasting_secs
                if trim_secs > 0 and pzt:
                    pzt[0] = max(0, pzt[0] - trim_secs)
                total_p = sum(pzt)
                if total_p > 0:
                    if planned_zone == 'Z2':
                        # Z2+Z3 tælles samlet (Friel: Z3 er acceptabel overskridelse i aerob base)
                        z2_secs = pzt[1] if len(pzt) > 1 else 0
                        z3_secs = pzt[2] if len(pzt) > 2 else 0
                        zone_pct = round((z2_secs + z3_secs) / total_p * 100, 1)
                        metric = 'power (Z2+Z3)'
                    else:
                        z_idx = int(planned_zone[1]) - 1 if planned_zone.startswith('Z') else 1
                        zone_pct = round(pzt[z_idx] / total_p * 100, 1) if z_idx < len(pzt) else 0
                        metric = 'power'
            if zone_pct is None and hr_zt and total_hr > 0:
                z_idx = int(planned_zone[1]) - 1 if planned_zone.startswith('Z') else 1
                zone_pct = round(hr_zt[z_idx] / total_hr * 100, 1) if z_idx < len(hr_zt) else 0
                metric = 'hr'

        elif disc == 'swim':
            # Kun HR tilgængeligt for svøm
            if hr_zt and total_hr > 0:
                z_idx = int(planned_zone[1]) - 1 if planned_zone.startswith('Z') else 1
                zone_pct = round(hr_zt[z_idx] / total_hr * 100, 1) if z_idx < len(hr_zt) else 0
                metric = 'hr'

        # Zone-flag
        if zone_pct is None:
            zone_flag = 'no_data'
        else:
            floor = zone_target_floor(planned_zone, disc)
            zone_flag = 'ok' if zone_pct >= floor else 'under'

        # Bestem altid (uanset ok/under) hvor evt. afvigende tid faktisk landede
        # ift. target-zonen — hurtigere/højere zone vs. langsommere/lavere zone.
        # Gæt ALDRIG retning ud fra HR alene: lav HR ved en for hurtig pace/watt
        # betyder ikke lav intensitet, bare at HR ikke nåede at følge med.
        # Z4/Z5 (interval-træning) undtages: recovery mellem intervals giver
        # naturligt meget tid i lavere zoner — det er IKKE "for roligt".
        direction = None
        below_pct = above_pct = None
        is_interval_zone = planned_zone in ('Z4', 'Z5')
        if not is_interval_zone and disc == 'run' and metric == 'pace' and pzt and sum(pzt) > 0:
            total_p = sum(pzt)
            z_idx = int(planned_zone[1]) - 1 if planned_zone.startswith('Z') else 1
            below_pct = round(sum(pzt[:z_idx]) / total_p * 100, 1) if z_idx > 0 else 0.0
            above_pct = round(sum(pzt[z_idx + 1:]) / total_p * 100, 1)
            if above_pct - below_pct >= 10:
                direction = 'fast'
            elif below_pct - above_pct >= 10:
                direction = 'slow'
        elif not is_interval_zone and disc == 'bike' and metric and metric.startswith('power') and pzt and sum(pzt) > 0:
            total_p = sum(pzt)
            target_idxs = {1, 2} if planned_zone == 'Z2' else {int(planned_zone[1]) - 1}
            below_pct = round(sum(v for i, v in enumerate(pzt) if i < min(target_idxs)) / total_p * 100, 1)
            above_pct = round(sum(v for i, v in enumerate(pzt) if i > max(target_idxs)) / total_p * 100, 1)
            if above_pct - below_pct >= 10:
                direction = 'fast'
            elif below_pct - above_pct >= 10:
                direction = 'slow'

        # Coaching-note
        note = ''
        if zone_flag == 'no_data':
            note = 'Ingen zone-data'
        elif disc == 'run' and metric == 'pace':
            combined_note = ' (Z4+Z5 kombineret)' if planned_zone in ('Z4', 'Z5') else ''
            base = f'{zone_pct}% i {planned_zone} (pace-zone){combined_note}'
            tag = ' — on target' if zone_flag == 'ok' else f' — under {floor}%-målet'
            if direction == 'fast':
                note = (f'{base}{tag}, men {above_pct}% af tiden lå i en HURTIGERE pace-zone end target '
                        f'(HR-Z1 = {hr_z1_pct}% — HR nåede ikke at følge med en for høj pace). Sænk tempoet.')
            elif direction == 'slow':
                note = (f'{base}{tag}, og {below_pct}% lå i en LANGSOMMERE pace-zone — '
                        f'løbet for roligt, overvej at skrue op for tempoet')
            else:
                note = f'{base}{tag}'
        elif disc == 'bike':
            base = f'{zone_pct}% i {planned_zone} ({metric})'
            tag = ' — on target' if zone_flag == 'ok' else f' — under {floor}%-målet (Z2+Z3 kombineret)'
            np_watts = act.get('icu_weighted_avg_watts')
            coasting_note = ''
            if high_coasting and moving_total:
                coasting_pct = round(coasting_secs / moving_total * 100, 1)
                coasting_note = (f' (NB: {coasting_pct}% coasting/frihjul — sandsynligt kuperet/gravel-terræn; '
                                  f'NP={np_watts}W er et mere retvisende effekt-mål end rå tid-i-zone her)')
            if direction == 'fast':
                if zone_flag == 'ok':
                    note = (f'{base}{tag}, {above_pct}% af tiden lå i højere watt-zone end target '
                             f'(fint hvis det var bevidste stigninger/indsatser){coasting_note}')
                else:
                    note = (f'{base}{tag}, men {above_pct}% af tiden lå i en HØJERE watt-zone end target — '
                            f'kørt for hårdt. Sænk wattene.{coasting_note}')
            elif direction == 'slow':
                if zone_flag == 'ok':
                    # Zonen er allerede opfyldt (>= floor) — "slow"-signalet er kun kontekst,
                    # ALDRIG en instruktion om at "skrue op", da det modsiger on-target-vurderingen
                    note = (f'{base}{tag}, {below_pct}% af tiden lå i lavere watt-zone '
                             f'(typisk nedkørsler/frihjul på kuperet terræn, ikke lav indsats){coasting_note}')
                else:
                    note = f'{base}{tag}, og {below_pct}% lå i en LAVERE watt-zone — skru wattene op{coasting_note}'
            else:
                note = f'{base}{tag}{coasting_note}'
        elif zone_flag == 'ok':
            note = f'{zone_pct}% i {planned_zone} ({metric}) — on target'
        else:
            note = f'{zone_pct}% i {planned_zone} ({metric}) — under {floor}%-målet'

        # Tilføj Intervals compliance hvis tilgængeligt
        if intervals_compliance and intervals_compliance > 0:
            note = f'Steps: {intervals_compliance:.0f}% · {note}'

        results.append({
            'day': day_key, 'date': ev_date, 'label': ev_name,
            'disc': disc, 'planned_zone': planned_zone,
            'intervals_compliance': intervals_compliance,
            'zone_pct': zone_pct, 'hr_z1_pct': hr_z1_pct,
            'hr_z2plus_pct': hr_z2plus_pct,
            'zone_flag': zone_flag, 'metric': metric,
            'moving_mins': moving_mins, 'planned_mins': planned_mins,
            'note': note,
        })

        print(f"  Zone-compliance {day_key} {ev_name[:30]}: {note}")

    return results


def format_compliance_for_prompt(compliance_list):
    """Formaterer compliance-liste til en kompakt streng til AI-prompten."""
    if not compliance_list:
        return None
    lines = []
    for c in compliance_list:
        day = c.get('day', '?')
        label = c.get('label', '')[:30]
        flag = c.get('zone_flag', 'no_data')
        note = c.get('note', '')
        moving = c.get('moving_mins')
        planned = c.get('planned_mins')

        dur_str = ''
        if moving and planned:
            dur_str = f' ({int(moving)}/{int(planned)} min)'
        elif moving:
            dur_str = f' ({int(moving)} min)'

        if flag == 'no_data':
            lines.append(f'- {day}: {label}{dur_str} → ikke gennemført')
        elif flag == 'ok':
            lines.append(f'- {day}: {label}{dur_str} → ✅ {note}')
        else:
            lines.append(f'- {day}: {label}{dur_str} → ⚠️  {note}')
    return '\n'.join(lines)


def get_planned_mins_this_week():
    """Henter planlagt træningstid i minutter fra Intervals denne uge.
    Bruger moving_time (sek), ellers estimated_moving_time, ellers 0.
    """
    today  = date.today()
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)
    r = api_get(f'{BASE}/events', auth=AUTH,
                     params={'oldest': str(monday), 'newest': str(sunday)})
    if r.status_code != 200:
        print(f"  Planned mins API fejl: {r.status_code}")
        return 0
    events = r.json()
    print(f"  Events denne uge: {len(events)}")
    # Et enkelt pas > 6t er ikke reelt — det er korrupt event-data (fx en
    # svømning med moving_time = 132240s ≈ 36t). Sådanne events afvises, så
    # de ikke oppuster ugens planlagte tid (var årsag til "48t 48m"-fejlen).
    MAX_SESSION_SECS = 6 * 3600
    total_mins = 0
    for e in events:
        if e.get('category') != 'WORKOUT':
            continue
        # Varighed i sekunder — moving_time bærer den planlagte varighed på events.
        # Intervals leverer disse felter i sekunder; ingen gætte-heuristik på enhed.
        secs = (e.get('moving_time') or
                e.get('elapsed_time') or
                e.get('indoor_time') or
                e.get('planned_duration') or 0)
        if not secs or secs <= 0:
            print(f"    Springer over (ingen varighed): {e.get('name','')}")
            continue
        if secs > MAX_SESSION_SECS:
            print(f"    ⚠️ Urealistisk varighed {secs}s ({secs/3600:.1f}t) — data-fejl, springes over: {e.get('name','')}")
            continue
        mins = secs / 60
        total_mins += mins
        print(f"    Event: {e.get('name','')} secs={secs} mins={mins:.0f}")
    result = round(total_mins, 0)
    print(f"  Planlagt total: {result} min")
    return result

def planned_tss_this_week():
    """Estimerer planlagt TSS live fra Intervals events denne uge.
    Intervals giver ikke altid 'load' på planlagte workouts, så vi estimerer
    fra varighed (moving_time) + zone via IF-model: TSS/time = IF^2 * 100.
    Falder tilbage til hardcodet tabel hvis API fejler eller ingen events.
    """
    today  = date.today()
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)

    # Fallback-tabel (bruges kun hvis live-data ikke kan hentes)
    week1 = date(2026, 6, 1)
    diff  = (today - week1).days
    week_num = min(max(diff // 7 + 1, 1), TOTAL_WEEKS)
    fallback = {1:383,2:460,3:466,4:167,5:511,6:490,7:546,8:186,
                9:596,10:598,11:638,12:194,13:345,14:245}.get(week_num, 400)

    r = api_get(f'{BASE}/events', auth=AUTH,
                     params={'oldest': str(monday), 'newest': str(sunday)})
    if r.status_code != 200:
        print(f"  Planned TSS API fejl: {r.status_code} — bruger fallback {fallback}")
        return fallback

    events = r.json()
    IF = {'Z1':0.55,'Z2':0.70,'Z3':0.80,'Z4':0.90,'Z5':1.0}
    total_tss = 0
    used_live = False

    for e in events:
        if e.get('category') not in ('WORKOUT', None):
            continue
        name = (e.get('name') or '')
        # 1) Hvis Intervals selv har en load/TSS, brug den
        load = e.get('load') or e.get('icu_training_load')
        if load:
            total_tss += load
            used_live = True
            continue
        # 2) Ellers estimer fra varighed + zone
        secs = (e.get('moving_time') or e.get('elapsed_time') or
                e.get('indoor_time') or e.get('planned_duration') or 0)
        if not secs:
            continue
        if secs > 6 * 3600:   # korrupt varighed (samme guard som planlagt tid) — udelad af TSS-estimat
            print(f"    ⚠️ Urealistisk varighed på '{name}' ({secs/3600:.1f}t) — udelades af TSS-estimat")
            continue
        hrs = secs / 3600
        nl = name.lower()
        # Bestem zone fra navnet
        zone = 'Z2'
        for z in ['Z5','Z4','Z3','Z2','Z1']:
            if z.lower() in nl:
                zone = z; break
        if 'interval' in nl or 'bjerg' in nl:
            zone = 'Z4'
        # Disciplinspecifik justering
        if 'styrke' in nl or e.get('type') in ('WeightTraining','Workout'):
            tss = hrs * 40            # styrke ~40 TSS/time
        elif 'svøm' in nl or e.get('type') == 'Swim':
            tss = hrs * 55            # svøm lidt højere intensitet
        else:
            tss = hrs * (IF[zone]**2 * 100)
        total_tss += tss
        used_live = True

    result = round(total_tss)
    if result == 0:
        print(f"  Ingen brugbare events med TSS/varighed — bruger fallback {fallback}")
        return fallback
    print(f"  Planlagt TSS (live estimat): {result}")
    return result

def parse_planned_mins(label):
    """Parser planlagt varighed fra label. Fx 'Lang løb Z2 90 min' → 90."""
    m = re.search(r'(\d+)\s*min', label or '', re.IGNORECASE)
    return int(m.group(1)) if m else None

def calc_completion(actual_tss, planned_tss, actual_mins, planned_mins, threshold=0.80):
    """
    Returnerer (status, pct):
      'done'    ≥80% af planlagt TSS (primær) eller tid (fallback)
      'partial' 20-79%
      'minimal' <20% — nærmest ikke gennemført
    """
    if planned_tss and planned_tss > 0 and actual_tss and actual_tss > 0:
        pct = actual_tss / planned_tss
        if pct >= threshold:      return 'done',    round(pct * 100)
        elif pct >= 0.20:         return 'partial', round(pct * 100)
        else:                     return 'minimal', round(pct * 100)
    if planned_mins and planned_mins > 0 and actual_mins and actual_mins > 0:
        pct = actual_mins / planned_mins
        if pct >= threshold:      return 'done',    round(pct * 100)
        elif pct >= 0.20:         return 'partial', round(pct * 100)
        else:                     return 'minimal', round(pct * 100)
    return 'done', None  # matchet men ingen data — antag done

def build_week_sessions(done_map, planned_sessions):
    """Opdater done-status på ugessessioner baseret på Intervals-aktiviteter.
    done_map: {dag_short: [(disc, navn), ...]} sorteret efter tidspunkt.
    Planlagte sessioner matches mod aktiviteter af samme disc; resterende
    aktiviteter tilføjes som separate ekstra-rækker (walk, hike, commute osv.)."""
    today     = date.today()
    today_idx = today.weekday()  # 0=Man, 6=Søn

    disc_labels = {
        'run': 'Løb', 'bike': 'Cykel', 'swim': 'Svøm', 'strength': 'Styrke',
        'free': 'Aktiv restitution', 'walk': 'Gåtur', 'hike': 'Vandring',
        'commute': 'Pendling', 'openwater': 'Open water',
    }

    # Spor hvilke aktiviteter pr. dag der er brugt til at matche planlagte sessioner
    used = {day: set() for day in done_map}

    result = []
    planned_days = set()
    for s in planned_sessions:
        day_key = s['day']
        try:
            day_idx = DAY_SHORT.index(day_key)
        except:
            day_idx = -1

        planned_days.add(day_key)
        new_s = dict(s)
        new_s.pop('today', None)
        # Ekstra aktiviteter får egne rækker nu — planlagte sessioner skal ikke
        # bære en forældet disc2 (fx "free"), som gav et overflødigt FRI-tag.
        new_s.pop('disc2', None)

        if day_idx == today_idx:
            new_s['today'] = True

        if day_idx <= today_idx and day_key in done_map:
            acts = done_map[day_key]
            planned_disc = s.get('disc')
            # Kun match på korrekt disc — ingen fallback
            # Kommute/cykel må ikke forbruge et planlagt løb
            match_idx = None
            for i, act_entry in enumerate(acts):
                disc = act_entry[0]
                # Pendlingsture matcher ALDRIG et planlagt pas. En 12-min tur paa
                # 3 TSS er ikke 15% af et 80-min hometrainer-pas — den er en
                # selvstaendig ekstra-aktivitet. Den gamle regel lod commute
                # forbruge et cykel-pas hvis ingen rigtig cykeltur fandtes, og
                # gjorde dagens pas "brugt" foer det var koert.
                if i not in used[day_key] and (
                    disc == planned_disc
                    or (disc in ("swim", "openwater") and planned_disc in ("swim", "openwater"))
                ):
                    match_idx = i
                    break
            if match_idx is not None:
                act_entry = acts[match_idx]
                act_disc, act_name, act_tss, act_dur_mins = act_entry[0], act_entry[1], act_entry[2], act_entry[3]
                act_compliance = act_entry[4] if len(act_entry) > 4 else None
                act_pace_zt    = act_entry[5] if len(act_entry) > 5 else None
                act_power_zt   = act_entry[6] if len(act_entry) > 6 else None
                act_hr_zt      = act_entry[7] if len(act_entry) > 7 else None
                planned_mins_val = parse_planned_mins(s.get('label', ''))
                planned_tss_val  = s.get('planned_tss') or None

                status, pct = calc_completion(
                    act_tss, planned_tss_val,
                    act_dur_mins, planned_mins_val
                )
                new_s['completion']     = status
                new_s['completion_pct'] = pct
                new_s['actual_tss']     = act_tss
                new_s['actual_mins']    = act_dur_mins
                new_s['planned_mins']   = planned_mins_val
                new_s['done'] = (status in ('done', 'partial'))
                # Zone-compliance data (til dashboard og AI-coaching)
                if act_compliance and act_compliance > 0:
                    new_s['intervals_compliance'] = round(act_compliance, 1)
                used[day_key].add(match_idx)

        result.append(new_s)

    # Ekstra-pas: alle ubrugte aktiviteter tilføjes som separate rækker
    for day_key, acts in done_map.items():
        try:
            day_idx = DAY_SHORT.index(day_key)
        except:
            continue
        if day_idx > today_idx:
            continue
        for i, act_entry in enumerate(acts):
            if i in used.get(day_key, set()):
                continue
            disc, name = act_entry[0], act_entry[1]
            tss, dur_mins = act_entry[2], act_entry[3]
            label = name if name else disc_labels.get(disc, disc)
            extra = {
                'day': day_key,
                'disc': disc,
                'label': label,
                'done': True,
                'extra': True,
            }
            if day_idx == today_idx:
                extra['today'] = True
            result.append(extra)

    result.sort(key=lambda s: DAY_SHORT.index(s['day']) if s['day'] in DAY_SHORT else 99)
    return result


def get_planned_weeks():
    """Hent planned workouts fra Intervals for forrige, denne og næste uge.
    Returnerer all_weeks dict: {week_num: {sessions: [...], focus: str, blockType: str}}
    """
    week1     = date(2026, 6, 1)
    today     = date.today()
    week_num  = min(max((today - week1).days // 7 + 1, 1), TOTAL_WEEKS)

    BLOCK_TYPES = {1:'BUILD',2:'BUILD+',3:'BUILD+',4:'RECOVERY',5:'BUILD',6:'BUILD',
                   7:'RECOVERY',8:'BUILD',9:'BUILD',10:'BUILD+',11:'BUILD+',12:'TAPER',
                   13:'TAPER',14:'RACE'}

    TYPE_MAP = {
        'Run':'run','TrailRun':'run','VirtualRun':'run','IndoorRun':'run',
        'Ride':'bike','VirtualRide':'bike','MountainBike':'bike',
        'Cyclocross':'bike','Gravel':'bike','GravelRide':'bike',
        'Swim':'swim','OpenWaterSwim':'openwater',
        'WeightTraining':'strength','Workout':'strength','Strength':'strength',
        'Walk':'walk','Hike':'hike',
    }
    DAY_SHORT = ["Man","Tir","Ons","Tor","Fre","Lør","Søn"]

    all_weeks = {}

    # Ét samlet API-kald for hele planperioden (uge 1-14) i stedet for 14 individuelle kald
    plan_start = week1
    plan_end   = week1 + timedelta(weeks=14) - timedelta(days=1)
    r = api_get(f'{BASE}/events', auth=AUTH,
                params={'oldest': str(plan_start), 'newest': str(plan_end)})
    if not r or r.status_code != 200:
        print(f"  ⚠️  get_planned_weeks: events API fejlede ({r.status_code if r else 'ingen svar'})")
        return all_weeks

    all_events = r.json()

    # Initialiser alle 14 uger
    for w in range(1, 15):
        all_weeks[w] = {'sessions': [], 'blockType': BLOCK_TYPES.get(w, 'BUILD'), 'focus': ''}

    day_order = {d:i for i,d in enumerate(DAY_SHORT)}

    for wo in all_events:
        if wo.get('category') not in ('WORKOUT', None):
            continue
        dt_str = wo.get('start_date_local', '')[:10]
        if not dt_str:
            continue
        try:
            dt = date.fromisoformat(dt_str)
        except:
            continue
        # Beregn hvilken planuge dette event tilhører
        delta_days = (dt - week1).days
        if delta_days < 0 or delta_days >= 14 * 7:
            continue
        w = delta_days // 7 + 1
        day_idx = dt.weekday()
        disc = TYPE_MAP.get(wo.get('type',''), 'free')
        name = fix_enc(wo.get('name', 'Træning'))
        all_weeks[w]['sessions'].append({
            'day':   DAY_SHORT[day_idx],
            'disc':  disc,
            'label': name,
            'done':  False,
            'today': (dt == today),
        })

    # Sorter sessions i alle uger
    for w in all_weeks:
        all_weeks[w]['sessions'].sort(key=lambda s: day_order.get(s['day'], 7))

    return all_weeks



def generate_week_focus(week_num, sessions, block_type):
    """Genererer weekFocus dynamisk fra ugens planlagte sessions i Intervals."""
    BLOCK_LABELS = {
        'BUILD': 'Build-uge', 'BUILD+': 'Intensiv build-uge',
        'RECOVERY': 'Restituitionsuge', 'TAPER': 'Taper-uge', 'RACE': 'Race-uge'
    }
    block_label = BLOCK_LABELS.get(block_type, 'Træningsuge')

    # Tæl discipliner
    discs = [s.get('disc') for s in sessions]
    runs   = discs.count('run')
    bikes  = discs.count('bike')
    swims  = discs.count('swim')
    strengths = discs.count('strength')

    parts = []
    if runs:    parts.append(f"{runs} løb")
    if bikes:   parts.append(f"{bikes} cykel")
    if swims:   parts.append(f"{swims} svøm")
    if strengths: parts.append(f"{strengths} styrke")

    discipline_str = " · ".join(parts) if parts else "aktiv hvile"

    # VO2-stimulus?
    has_vo2 = any('VO2' in (s.get('label') or '') or 'Z4' in (s.get('label') or '') or 'Z5' in (s.get('label') or '') for s in sessions)
    vo2_str = " · én VO2-stimulus" if has_vo2 else ""

    return f"{block_label} {week_num} — {discipline_str}{vo2_str}. Fokus: konsistens over intensitet."

QUOTES_TRAINING = [
    "\"Det er ikke om at have tid. Det er om at tage den.\"",
    "\"Sæt farten ned, så du kan gå langt.\"",
    "\"Konsistens slår intensitet, hver gang.\"",
    "\"Hvil er ikke det modsatte af fremskridt — det er en del af det.\"",
    "\"Formen bygges i kedsomheden — ikke i begejstringen.\"",
    "\"14 uger er lang tid. Men hver dag er kort.\"",
    "\"Den bedste træning er den, du faktisk gennemfører.\"",
    "\"Recovery er ikke pause — det er produktion.\"",
    "\"Du har gjort det 16 gange før. Kroppen kender vejen.\"",
]

QUOTES_DIET = [
    "\"Et godt måltid og en god nats søvn slår en ekstra hård træning.\"",
    "\"AF-dage er ikke et offer — de er en investering i morgendagens energi.\"",
    "\"Mindre alkohol, mere søvn — den billigste performance-boost der findes.\"",
    "\"Protein ved hvert måltid. Ingen undtagelser, ingen drama.\"",
    "\"Kroppen tror, hvad sindet siger.\"",
    "\"Vægten flytter sig ikke i dag. Men vanen gør.\"",
]

QUOTES_PHILOSOPHY = [
    "\"Disciplin er at vælge mellem hvad du vil nu, og hvad du vil mest.\"",
    "\"Det er de små valg hver dag, der bygger den store form.\"",
    "\"Keep moving forward.\"",
    "\"Du konkurrerer ikke mod andre i dag. Kun mod gårsdagens dig.\"",
    "\"Smertegrænsen flytter sig — men kun hvis du respekterer den først.\"",
    "\"Sæt målet højt, men sæt i dag realistisk.\"",
    "\"Form kommer og går. Vaner bliver.\"",
    "\"Hold roen. Hold rytmen. Hold farten.\"",
    "\"Du har magt over dit sind — ikke over yderomstændigheder. Indse det, og du finder styrke.\" — Marcus Aurelius",
    "\"Begynd ikke at handle som om du har ti tusind år at leve i.\" — Marcus Aurelius",
    "\"Hindringen for handling fremmer handlingen. Det, der står i vejen, bliver vejen.\" — Marcus Aurelius",
    "\"Det er ikke at have for lidt, der gør et menneske fattigt, men at ville have mere.\" — Seneca",
    "\"Hver morgen: jeg vågner for at gøre menneskets arbejde.\" — Marcus Aurelius",
    "\"Udholdenhed er bitter, men dens frugt er sød.\"",
    "\"Du bliver til det, du gør ofte.\"",
]


def get_swim_history():
    """Hent ugentlig svømdistance (meter) siden projektstart uge 1.
    Bruges til svøm-progression mod Christiansborg Rundt 2000m (29/8-2026).
    Returnerer liste: [{week, date_str, meters, cumulative}]
    """
    from datetime import date, timedelta
    week1 = date(2026, 6, 1)
    today = date.today()
    oldest = str(week1)
    newest = str(today)

    r = api_get(f'{BASE}/activities', auth=AUTH,
                params={'oldest': oldest, 'newest': newest,
                        'types': 'Swim,OpenWaterSwim', 'limit': 200})
    if not r or r.status_code != 200:
        return []

    acts = r.json()
    # Gruppér pr. uge
    by_week = {}
    for a in acts:
        # Intervals.icu ignorerer 'types'-parameteren, saa filtrer selv
        if a.get('type') not in ('Swim', 'OpenWaterSwim'):
            continue
        dt_str = (a.get('start_date_local') or '')[:10]
        if not dt_str:
            continue
        try:
            dt = date.fromisoformat(dt_str)
        except:
            continue
        delta = (dt - week1).days
        if delta < 0:
            continue
        w = delta // 7 + 1
        dist_m = a.get('distance') or 0
        by_week[w] = round(by_week.get(w, 0) + dist_m, 0)

    # Byg kronologisk liste uge 1 → nu
    current_week = min(max((today - week1).days // 7 + 1, 1), TOTAL_WEEKS)
    result = []
    cumulative = 0
    for w in range(1, current_week + 1):
        m = by_week.get(w, 0)
        cumulative += m
        mon = week1 + timedelta(weeks=w - 1)
        result.append({
            'week':       w,
            'date':       str(mon),
            'meters':     m,
            'cumulative': round(cumulative, 0),
        })
    return result


def generate_week_focus_ai(week_num, sessions, block_type, ctl=None, tsb=None, week_note=None, anthropic_key=None):
    """Genererer weekFocus via Anthropic API — caches per uge i update_kpi.
    Fallback til generate_week_focus() hvis API fejler eller key mangler."""
    if not anthropic_key:
        return generate_week_focus(week_num, sessions, block_type)

    import json
    try:
        import urllib.request as _req
    except ImportError:
        return generate_week_focus(week_num, sessions, block_type)

    BLOCK_LABELS = {
        'BUILD': 'Build-uge', 'BUILD+': 'Intensiv build-uge',
        'RECOVERY': 'Restituitionsuge', 'TAPER': 'Taper-uge', 'RACE': 'Race-uge'
    }
    block_label = BLOCK_LABELS.get(block_type, 'Træningsuge')

    discs = [s.get('disc') for s in sessions]
    session_lines = [f"- {s.get('day','?')}: {s.get('label','?')}" for s in sessions]
    has_vo2 = any('VO2' in (s.get('label') or '') or 'Z4' in (s.get('label') or '') or 'Z5' in (s.get('label') or '') for s in sessions)

    fitness_str = ""
    if ctl is not None:
        fitness_str += f"CTL: {ctl}"
    if tsb is not None:
        fitness_str += f", TSB: {tsb}"

    note_str = f"\nMaster Plan-note for ugen: \"{week_note}\"" if week_note else ""

    prompt = (
        f"Du er træningscoach for Kennet Hammerby, 51 år, erfaren Ironman-atlet.\n"
        f"Han er i uge {week_num} af 14 i sit 'Fast as Fifty' program.\n"
        f"Ugetype: {block_label}.\n"
        f"Fitness: {fitness_str}.\n"
        f"{'VO2-stimulus planlagt denne uge.' if has_vo2 else 'Ingen VO2-stimulus denne uge.'}"
        f"{note_str}\n"
        f"Planlagte sessioner:\n" + "\n".join(session_lines) + "\n\n"
        f"Skriv ÉT ugefokus på dansk. ALDRIG linjeskift, ALDRIG punktopstilling — kun én enkelt sætning.\n"
        f"Max 12 ord. Ingen overskrift, ingen emoji, ingen punktum til sidst.\n"
        f"Det skal være præcist og motiverende — ikke generisk.\n"
        f"Eksempel: 'Genopbyg intensitet og rytme efter recovery — første VO2-stimulus'\n"
        f"Svar KUN med selve fokus-teksten — intet andet. Ingen forklaring, ingen citationstegn."
    )

    try:
        payload = json.dumps({
            "model": "claude-sonnet-4-6",
            "max_tokens": 60,
            "messages": [{"role": "user", "content": prompt}]
        }).encode()

        req = _req.Request(
            "https://api.anthropic.com/v1/messages",
            data=payload,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "x-api-key": anthropic_key,
                "anthropic-version": "2023-06-01"
            }
        )
        with _req.urlopen(req, timeout=15) as r:
            result = json.loads(r.read())
            text = fix_enc(result["content"][0]["text"]).strip().split("\n")[0].strip().strip('"').strip("'")[:120]
            print(f"  ✅ weekFocus AI genereret: {text}")
            return text
    except Exception as e:
        print(f"  ⚠️  weekFocus AI fejlede: {e} — bruger fallback")
        return generate_week_focus(week_num, sessions, block_type)

