import requests, json, math, os, sys, time, warnings, subprocess
from urllib.parse import urlencode
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd
import numpy as np

ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE=os.path.join(ROOT,'work','cache')
os.makedirs(CACHE, exist_ok=True)
HEADERS={'User-Agent':'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127 Safari/537.36','Referer':'https://quote.eastmoney.com/'}
S=requests.Session(); S.trust_env=False
PROXIES=None
BEG=os.environ.get('BEG','20250601')
END=os.environ.get('END','20500101')

def get_stock_list():
    # Sina A-share list; Eastmoney's clist endpoint is unstable from this host.
    total=int(requests.get('https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeStockCount?node=hs_a',headers=HEADERS,timeout=12,proxies={'http':None,'https':None}).text.strip('"'))
    rows=[]; page=1; num=100
    while len(rows)<total:
        url='https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData'
        params={'page':page,'num':num,'sort':'symbol','asc':1,'node':'hs_a','symbol':'','_s_r_a':'page'}
        r=requests.get(url,params=params,headers=HEADERS,timeout=15,proxies={'http':None,'https':None})
        r.raise_for_status(); arr=r.json()
        if not arr: break
        for d in arr:
            sym=d.get('symbol',''); code=d.get('code','')
            market=1 if sym.startswith('sh') else 0
            rows.append({'code':code,'market':market,'name':d.get('name',''),'close':float(d.get('trade') or 0),
                         'volume':float(d.get('volume') or 0),'amount':float(d.get('amount') or 0),
                         'total_mv':float(d.get('mktcap') or 0)*10000,'float_mv':float(d.get('nmc') or 0)*10000,
                         'list_date':''})
        print('sina list page',page,'rows',len(rows),'total',total,flush=True)
        page+=1; time.sleep(0.12)
    return pd.DataFrame(rows).drop_duplicates('code')


def fetch_hist(row):
    code=str(row.code)
    if code.startswith(('4', '8', '92')):
        # Tencent fqkline provides insufficient history for many BSE tickers.
        raise ValueError('skip BSE insufficient history')
    prefix='sh' if int(row.market)==1 else 'sz'
    symbol=prefix+code
    fn=os.path.join(CACHE,f"{symbol}.json")
    if os.path.exists(fn):
        with open(fn,encoding='utf-8') as f: obj=json.load(f)
        if len(obj['k'])>=90: return code,len(obj['k'])
    params={'param':f'{symbol},day,2025-01-01,2026-12-31,640,qfq'}
    last=''
    for attempt in range(3):
        try:
            r=S.get('https://web.ifzq.gtimg.cn/appstock/app/fqkline/get',params=params,headers=HEADERS,timeout=12)
            r.raise_for_status(); data=r.json().get('data',{}).get(symbol,{})
            lines=data.get('qfqday') or data.get('day') or []
            rec=[]
            for a in lines:
                if len(a)<6: continue
                date=a[0]; o,c,h,l,v=map(float,a[1:6])
                # Tencent stock volume is in lots; estimate turnover for relative checks.
                rec.append([date,o,c,h,l,v,c*v*100,abs(c-o)/o*100 if o else 0,(c-o)/o*100 if o else 0,c-o,0])
            if len(rec)<90: raise ValueError(f'insufficient history {len(rec)}')
            with open(fn,'w',encoding='utf-8') as f:
                json.dump({'code':code,'market':int(row.market),'name':row.name,'k':rec},f,ensure_ascii=False)
            return code,len(rec)
        except Exception as e:
            last=e; time.sleep(0.3*(attempt+1))
    raise last


def ema(s, span):
    return s.ewm(span=span, adjust=False).mean()

def calc_indicators(df):
    df=df.copy()
    df['ema12']=ema(df.close,12); df['ema26']=ema(df.close,26)
    df['dif']=df.ema12-df.ema26; df['dea']=ema(df.dif,9); df['hist']=(df.dif-df.dea)*2
    # volume MA and ratio
    for w in [5,10,20,60]:
        df[f'ma{w}']=df.close.rolling(w).mean(); df[f'vma{w}']=df.volume.rolling(w).mean()
    df['vol_ratio']=df.volume/df.vma5
    return df

def local_minima(a,w=5):
    idx=[]
    for i in range(w,len(a)-w):
        seg=a[i-w:i+w+1]
        if a[i] <= seg.min() and a[i] < a[i-1] and a[i] < a[i+1]:
            # avoid plateaus repeated: nearest local low only
            idx.append(i)
    # filter nearby pivots
    out=[]
    for i in idx:
        if not out or i-out[-1]>=w:
            out.append(i)
        elif a[i]<a[out[-1]]:
            out[-1]=i
    return out

def bottom_divergence(df):
    # Need enough data
    if len(df)<90: return None
    lows=df.low.values; dif=df.dif.values; hist=df["hist"].values
    piv=local_minima(lows,w=5)
    if len(piv)<2: return None
    n=len(df); matches=[]
    for jj in range(len(piv)-1,0,-1):
        j=piv[jj]
        # near term only
        if n-1-j>15: break
        for ii in range(jj-1,-1,-1):
            i=piv[ii]
            gap=j-i
            if gap<8: continue
            if gap>65: break
            # lower price low
            if not (lows[j] < lows[i]*0.995): continue
            # windows around pivots, bounded to not overlap strongly
            iw=slice(max(0,i-5),min(n,i+6)); jw=slice(max(0,j-5),min(n,j+6))
            dif_i=np.nanmin(dif[iw]); dif_j=np.nanmin(dif[jw])
            h_i=np.nanmin(hist[iw]); h_j=np.nanmin(hist[jw])
            # oscillator higher by small tolerance, avoid pure noise
            dif_ok=dif_j > dif_i + 1e-6
            hist_ok=h_j > h_i + 1e-6
            if dif_ok or hist_ok:
                typ=[]
                if dif_ok: typ.append('DIF')
                if hist_ok: typ.append('柱体')
                matches.append({
                    'pivot_i':int(i),'pivot_j':int(j),'date_i':df.date.iloc[i],'date_j':df.date.iloc[j],
                    'low_i':float(lows[i]),'low_j':float(lows[j]),'gap':int(gap),
                    'dif_i':float(dif_i),'dif_j':float(dif_j),'dif_gain':float(dif_j-dif_i),
                    'hist_i':float(h_i),'hist_j':float(h_j),'hist_gain':float(h_j-h_i),
                    'type':'+'.join(typ),'days_ago':n-1-j,'strong':bool(dif_ok and hist_ok)
                })
                # take the earliest valid prior pivot for the latest low
                break
        # If latest pivot has any match, stop searching for other later pivots
        if matches: break
    return matches

def score_row(row, m, df):
    last=df.iloc[-1]
    strength=(m['dif_gain']/max(abs(m['dif_i']),0.01)*0.65 + m['hist_gain']/max(abs(m['hist_i']),0.01)*0.35)
    liquidity=math.log10(max(float(row.amount or 0),1))/8
    return float(100*max(0,strength) + 20*liquidity + 8*(m['strong']) + max(0,3-m['days_ago']/5))

def analyze_all():
    stocks=get_stock_list(); print('stocks',len(stocks),flush=True)
    stocks.to_csv(os.path.join(ROOT,'work','stock_list.csv'),index=False)
    results=[]; errors=[]; done=0
    def one(row):
        prefix='sh' if int(row.market)==1 else 'sz'
        fn=os.path.join(CACHE,f"{prefix}{row.code}.json")
        if os.path.exists(fn):
            with open(fn,encoding='utf-8') as f: obj=json.load(f)
            if len(obj['k'])<90: return None
            df=pd.DataFrame(obj['k'],columns=['date','open','close','high','low','volume','amount','amplitude','pct','chg','turnover'])
        else:
            return None
        df=calc_indicators(df); ms=bottom_divergence(df)
        if not ms: return None
        m=ms[-1]
        last=df.iloc[-1]; prev=df.iloc[-2] if len(df)>1 else last
        # price/volume action
        v5=df.volume.tail(5).mean(); v20=df.volume.tail(20).mean()
        metrics={
          'latest_date':last.date,'latest_close':float(last.close),'latest_pct':float(last.pct),
          'volume_ratio':float(last.volume/df.volume.tail(5).mean()) if df.volume.tail(5).mean()>0 else np.nan,
          'vol_trend_5_20':float(v5/v20) if v20>0 else np.nan,
          'turnover':float(last.turnover),'dif':float(last.dif),'dea':float(last.dea),'hist':float(last['hist']),
          'dif_rising':bool(last.dif>prev.dif),'hist_rising':bool(last['hist']>prev['hist']),
          'above_ma20':bool(last.close>last.ma20),'above_ma60':bool(last.close>last.ma60),
          'dist_low_pct':float((last.close-m['low_j'])/m['low_j']*100),
          'macd_cross_recent':int(((df.dif>df.dea)&(df.dif.shift()>df.dea.shift())).iloc[-10:].sum())
        }
        base={k:row[k] for k in ['code','market','name','close','amount','total_mv','float_mv','list_date']}
        return {**base,**metrics,**m,'score':score_row(row,m,df)}
    with ThreadPoolExecutor(max_workers=16) as ex:
        futs={ex.submit(fetch_hist,row):row for _,row in stocks.iterrows()}
        for fut in as_completed(futs):
            row=futs[fut]
            try:
                fut.result()
                r=one(row)
                if r: results.append(r)
            except Exception as e:
                errors.append({'code':row.code,'error':repr(e)})
            done+=1
            if done%500==0: print('done',done,'matches',len(results),'errors',len(errors),flush=True)
    res=pd.DataFrame(results)
    res.to_csv(os.path.join(ROOT,'work','all_bottom_divergence_raw.csv'),index=False)
    err=pd.DataFrame(errors); err.to_csv(os.path.join(ROOT,'work','errors.csv'),index=False)
    print('FINISHED',len(stocks),len(res),len(err))
    print('strong', int(res.strong.sum()) if len(res) else 0)
    return res

if __name__=='__main__':
    analyze_all()
