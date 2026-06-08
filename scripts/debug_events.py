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
out={'status':r.status_code,'range':f'{monday}..{sunday}','count':0,'events':[]}
tss_sum=0
if r.status_code==200:
    evs=r.json()
    out['count']=len(evs)
    for e in evs:
        load=e.get('load')
        tss_sum += (load or 0)
        out['events'].append({
            'name':e.get('name',''),
            'category':e.get('category'),
            'type':e.get('type'),
            'load':load,
            'moving_time':e.get('moving_time'),
            'icu_training_load':e.get('icu_training_load'),
        })
out['tss_sum_from_load']=round(tss_sum)
with open('debug_events.json','w') as f: json.dump(out,f,ensure_ascii=False,indent=2)
print('done')
