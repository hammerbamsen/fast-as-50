#!/usr/bin/env python3
"""
Debug: printer alle felter i Intervals.icu wellness-respons for de seneste 30 dage.
Kør via: python3 scripts/debug_wellness_fields.py
Formål: identificere det korrekte API-feltnavn for kropsfedt/bodyFat.
"""
import os, json, requests
from datetime import date, timedelta

API_KEY    = os.environ.get('INTERVALS_API_KEY', '')
ATHLETE_ID = os.environ.get('INTERVALS_ATHLETE_ID', 'i0')
BASE       = f'https://intervals.icu/api/v1/athlete/{ATHLETE_ID}'
AUTH       = ('API_KEY', API_KEY)

oldest = str(date.today() - timedelta(days=30))
newest = str(date.today())
r = requests.get(f'{BASE}/wellness', auth=AUTH, params={'oldest': oldest, 'newest': newest})

print(f"Status: {r.status_code}")
if r.status_code != 200:
    print("Fejl:", r.text[:200])
    exit(1)

rows = r.json()
print(f"Rækker: {len(rows)}")
print()

# Print alle unikke felter på tværs af alle rækker
all_keys = set()
for row in rows:
    all_keys.update(row.keys())

print("=== ALLE FELTER I WELLNESS-RESPONSE ===")
for k in sorted(all_keys):
    print(f"  {k}")

print()
print("=== RÆKKER MED VÆGT ELLER FEDT (alle felter) ===")
for row in rows:
    has_weight = row.get('weight') is not None
    # Tjek alle felter for noget der ligner fedt
    fat_fields = {k: v for k, v in row.items() 
                  if v is not None and any(word in k.lower() for word in 
                     ['fat', 'fedt', 'krop', 'body', 'percent', 'pct', 'bf'])}
    if has_weight or fat_fields:
        dt = row.get('id') or row.get('date', '?')
        print(f"  {dt}  weight={row.get('weight')}  fat-felter={fat_fields}")
