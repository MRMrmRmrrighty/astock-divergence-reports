import os, json
from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd
import numpy as np
from market_data import calc_indicators, bottom_divergence, score_row, CACHE

ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIST=os.path.join(ROOT,'work','stock_list.csv')

def one(row):
    code=str(row.code)
    if code.startswith(('4','8','92')): return None
    prefix='sh' if int(row.market)==1 else 'sz'; fn=os.path.join(CACHE,f'{prefix}{code}.json')
    if not os.path.exists(fn): return None
    obj=json.load(open(fn,encoding='utf-8'))
    if len(obj.get('k',[]))<90: return None
    df=pd.DataFrame(obj['k'],columns=['date','open','close','high','low','volume','amount','amplitude','pct','chg','turnover'])
    for c in ['open','close','high','low','volume','amount']:
        df[c]=pd.to_numeric(df[c],errors='coerce')
    df=calc_indicators(df); ms=bottom_divergence(df)
    if not ms: return None
    m=ms[-1]; last=df.iloc[-1]; prev=df.iloc[-2]
    v5=df.volume.tail(5).mean(); v20=df.volume.tail(20).mean()
    metrics={
      'latest_date':last.date,'latest_close':float(last.close),'latest_pct':float(last.pct),
      'volume_ratio':float(last.volume/v5) if v5>0 else np.nan,
      'vol_trend_5_20':float(v5/v20) if v20>0 else np.nan,
      'turnover':float(last.turnover),'dif':float(last.dif),'dea':float(last.dea),'hist':float(last['hist']),
      'dif_rising':bool(last.dif>prev.dif),'hist_rising':bool(last['hist']>prev['hist']),
      'above_ma20':bool(last.close>last.ma20),'above_ma60':bool(last.close>last.ma60),
      'dist_low_pct':float((last.close-m['low_j'])/m['low_j']*100),
      'macd_cross_recent':int(((df.dif>df.dea)&(df.dif.shift()>df.dea.shift())).iloc[-10:].sum())
    }
    base={'code':code,'market':int(row.market),'name':row['name'],'close':float(last.close),'amount':float(last.amount),'total_mv':np.nan,'float_mv':np.nan,'list_date':''}
    return {**base,**metrics,**m,'score':score_row(SimpleNamespace(**base),m,df)}

if __name__=='__main__':
    stocks=pd.read_csv(LIST,dtype={'code':str}); results=[]; errors=[]; done=0
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs={ex.submit(one,row):row for _,row in stocks.iterrows()}
        for fut in as_completed(futs):
            row=futs[fut]
            try:
                r=fut.result()
                if r: results.append(r)
            except Exception as e: errors.append({'code':str(row.code),'name':row['name'],'error':repr(e)})
            done+=1
            if done%1000==0: print('done',done,'matches',len(results),'errors',len(errors),flush=True)
    res=pd.DataFrame(results); res.to_csv(os.path.join(ROOT,'work','all_bottom_divergence_raw___TARGET_ND__.csv'),index=False)
    pd.DataFrame(errors).to_csv(os.path.join(ROOT,'work','errors_screen___TARGET_ND__.csv'),index=False)
    print('FINISHED caches',done,'matches',len(res),'errors',len(errors),'strong',int(res.strong.sum()) if len(res) else 0,flush=True)
