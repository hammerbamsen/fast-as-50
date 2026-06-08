import os, json, requests
from datetime import date, timedelta
API_KEY=os.environ.get('INTERVALS_API_KEY','')
ATHLETE_ID=os.environ.get('INTERVALS_ATHLETE_ID','i0')
BASE=f'https://intervals.icu/api/v1/athlete/{ATHLETE_ID}'
AUTH=('API_KEY',API_KEY)
today=date.today()
monday=today-timedelta(days=today.weekday())
sunday=monday+timedelta(days=6)
r=requests.get(f'{BASE}/events',auth=AUTH,params={'oldest':str(monday),'newest':str(sunday)})
out={'status':r.status_code,'range':f'{monday}..{sunday}','events':[]}
total_load=0; total_mins=0
if r.status_code==200:
    for e in r.json():
        if e.get('category') not in ('WORKOUT',None): continue
        load=e.get('load') or 0
        secs=e.get('moving_time') or e.get('elapsed_time') or e.get('planned_duration') or 0
        mins=secs/60 if secs>60 else secs
        total_load+=load; total_mins+=mins
        out['events'].append({'name':e.get('name',''),'type':e.get('type'),'load':load,'mins':round(mins)})
out['total_load_tss']=round(total_load)
out['total_mins']=round(total_mins)
with open('debug_planned.json','w') as f: json.dump(out,f,ensure_ascii=False,indent=2)
print('done')
