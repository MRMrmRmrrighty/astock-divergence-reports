import os, json, time
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd
import requests
from market_data import get_stock_list, CACHE, HEADERS, S

END='__TARGET_DATE__'
OUT_LIST=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'work','stock_list.csv')

def refresh(row):
    code=str(row.code)
    if code.startswith(('4','8','92')):
        raise ValueError('skip BSE')
    prefix='sh' if int(row.market)==1 else 'sz'
    symbol=prefix+code
    params={'param':f'{symbol},day,2025-01-01,{END},640,qfq'}
    fn=os.path.join(CACHE,f'{symbol}.json')
    last=''
    for attempt in range(4):
        try:
            r=S.get('https://web.ifzq.gtimg.cn/appstock/app/fqkline/get',params=params,headers=HEADERS,timeout=15)
            r.raise_for_status()
            data=r.json().get('data',{}).get(symbol,{})
            lines=data.get('qfqday') or data.get('day') or []
            rec=[]
            for a in lines:
                if len(a)<6: continue
                date=a[0]
                if date>END: continue
                o,c,h,l,v=map(float,a[1:6])
                rec.append([date,o,c,h,l,v,c*v*100,abs(c-o)/o*100 if o else 0,(c-o)/o*100 if o else 0,c-o,0])
            if len(rec)<90:
                raise ValueError(f'insufficient history {len(rec)}')
            tmp=fn+'.tmp'
            with open(tmp,'w',encoding='utf-8') as f:
                json.dump({'code':code,'market':int(row.market),'name':row.name,'k':rec},f,ensure_ascii=False)
            os.replace(tmp,fn)
            return code,len(rec),rec[-1][0]
        except Exception as e:
            last=e
            time.sleep(0.35*(attempt+1))
    raise last

if __name__=='__main__':
    stocks=get_stock_list()
    stocks.to_csv(OUT_LIST,index=False)
    print('stocks',len(stocks),flush=True)
    errors=[]; done=0
    with ThreadPoolExecutor(max_workers=12) as ex:
        futs={ex.submit(refresh,row):row for _,row in stocks.iterrows()}
        for fut in as_completed(futs):
            row=futs[fut]
            try:
                code,n,last_date=fut.result()
            except Exception as e:
                errors.append({'code':row.code,'name':row.name,'error':repr(e)})
            done+=1
            if done%250==0:
                print('done',done,'errors',len(errors),flush=True)
    pd.DataFrame(errors).to_csv(os.path.join(os.path.dirname(OUT_LIST),'errors_update___TARGET_ND__.csv'),index=False)
    print('FINISHED',len(stocks),'errors',len(errors),flush=True)
