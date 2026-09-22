import os, re, json, time
from concurrent.futures import ThreadPoolExecutor, as_completed
import numpy as np
import pandas as pd
import requests

ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT=os.path.join(ROOT,'outputs'); CACHE=os.path.join(ROOT,'work','cache')
RAW=os.path.join(ROOT,'work','all_bottom_divergence_raw___TARGET_ND__.csv')
DETAIL=os.path.join(OUT,'A股底背离筛选明细_数据至__TARGET_DATE__.csv')
GRADE=os.path.join(OUT,'A股底背离推荐等级排序_数据至__TARGET_DATE__.csv')
MOUT=os.path.join(OUT,'A股底背离推荐等级排序_多因子_数据至__TARGET_DATE__.csv')
TRADE_DATE='__TARGET_DATE__'
H={'User-Agent':'Mozilla/5.0','Referer':'https://data.eastmoney.com/'}
S=requests.Session(); S.headers.update(H); S.trust_env=False

# 1. Technical screen and grade
raw=pd.read_csv(RAW,dtype={'code':str})
raw['is_st']=raw.name.astype(str).str.contains('ST|退',na=False)
f=raw[(raw.strong)&(~raw.is_st)&(raw.close>=2)&(raw.amount>=50000000)&(raw.days_ago<=15)&(raw.dist_low_pct<=8)].copy()
f=f.sort_values(['score','amount'],ascending=[False,False]).reset_index(drop=True)
f.to_csv(DETAIL,index=False,encoding='utf-8-sig')
x=f.copy()
x['score_pct']=x.score.rank(pct=True,method='average')
x['confirm_score']=(2*x.above_ma20.astype(int)+x.above_ma60.astype(int)+x.hist_rising.astype(int)+x.dif_rising.astype(int)+((x['hist']>0)&(x.dif>x.dea)).astype(int)+(x.dist_low_pct<=3).astype(int))
x['recommend_score']=(70*x.score_pct.clip(0,1)+30*(x.confirm_score/x.confirm_score.max()).clip(0,1)).round(2)
ta=x.recommend_score.quantile(.85); tb=x.recommend_score.quantile(.50)
a=(x.recommend_score>=ta)&(x.confirm_score>=4)
b=(~a)&(((x.recommend_score>=tb)&(x.confirm_score>=3))|(x.confirm_score>=5))
x['推荐等级']=np.select([a,b],['A','B'],default='C')
x.to_csv(GRADE,index=False,encoding='utf-8-sig')
print('filtered',len(x),'technical grade',x['推荐等级'].value_counts().to_dict(),flush=True)

# 2. Approximate chip distribution from 250 days of qfq volume-price data.
market_map=raw.drop_duplicates('code').set_index('code')['market'].to_dict()
def cache_path(code):
    prefix='sh' if int(market_map.get(code,0))==1 else 'sz'
    return os.path.join(CACHE,f'{prefix}{code}.json')
def chip_metrics(code):
    obj=json.load(open(cache_path(code),encoding='utf-8'))
    df=pd.DataFrame(obj['k'],columns=['date','open','close','high','low','volume','amount','amplitude','pct','chg','turnover'])
    for c in ['open','close','high','low','volume']: df[c]=pd.to_numeric(df[c],errors='coerce')
    d=df.dropna(subset=['close','high','low','volume']).tail(250).reset_index(drop=True)
    lo=float(d.low.min())*.98; hi=float(d.high.max())*1.02
    grid=np.linspace(lo,hi,700); chip=np.zeros_like(grid); n=len(d)
    decay=.5**((n-1-np.arange(n))/120.0)
    for row,wt in zip(d.itertuples(index=False),decay):
        if not np.isfinite(row.volume) or row.volume<=0: continue
        typical=(row.low+row.high+2*row.close)/4.0
        if row.high<=row.low:
            chip[int(np.argmin(np.abs(grid-typical)))] += float(row.volume)*wt
        else:
            mask=(grid>=row.low)&(grid<=row.high); xx=grid[mask]
            w=np.maximum(1-np.abs(xx-typical)/(row.high-row.low),.01)
            chip[mask]+=w/w.sum()*float(row.volume)*wt
    total=chip.sum()
    if total<=0:return np.nan,np.nan,np.nan,np.nan,float(d.close.iloc[-1]),float(d.volume.iloc[-1])
    avg=float(np.sum(grid*chip)/total); conc=float(chip[(grid>=avg*.9)&(grid<=avg*1.1)].sum()/total*100)
    cdf=np.cumsum(chip)/total; p5=float(np.interp(.05,cdf,grid)); p95=float(np.interp(.95,cdf,grid))
    return avg,conc,float((p95-p5)/avg*100),float((float(d.close.iloc[-1])/avg-1)*100),float(d.close.iloc[-1]),float(d.volume.iloc[-1])

# 3. Exact __TARGET_DATE__ close valuation snapshot from Eastmoney Data Center.
PREV_TRADE_DATE='__PREV_DATE__'
def valuation(code):
    for td in [TRADE_DATE, PREV_TRADE_DATE]:
        filt=f'(SECURITY_CODE="{code}")(TRADE_DATE=\'{td}\')'
        p={'reportName':'RPT_VALUEANALYSIS_DET','columns':'ALL','filter':filt,'pageNumber':1,'pageSize':1,'source':'WEB','client':'WEB'}
        for attempt in range(3):
            try:
                r=S.get('https://datacenter-web.eastmoney.com/api/data/v1/get',params=p,timeout=18); r.raise_for_status()
                js=r.json(); arr=((js.get('result') or {}).get('data') or [])
                if not arr: break
                d=arr[0]
                return code,{
                    'quote_price':d.get('CLOSE_PRICE'),'turnover_calc':np.nan,
                    'pe_ttm':d.get('PE_TTM'),'float_mv':d.get('NOTLIMITED_MARKETCAP_A'),
                    'total_mv':d.get('TOTAL_MARKET_CAP'),'pb':d.get('PB_MRQ'),
                    'valuation_date':str(d.get('TRADE_DATE',''))[:10],
                    'total_shares':d.get('TOTAL_SHARES'),'free_shares':d.get('FREE_SHARES_A')
                }
            except Exception as e:
                time.sleep(.4*(attempt+1))
    return code,{}

vals={}; errors=[]
with ThreadPoolExecutor(max_workers=4) as ex:
    futs={ex.submit(valuation,c):c for c in x.code}
    for i,fut in enumerate(as_completed(futs),1):
        code, v = fut.result()
        vals[code]=v
        if i%50==0: print('valuation',i,flush=True)
missing=[c for c in x.code if not vals.get(c)]
if missing: print('missing valuation',missing)

# Turnover for __TARGET_DATE__ is calculated from qfq daily volume and free shares.
def make_row(code):
    avg,conc,r90,pos,qclose,last_vol=chip_metrics(code)
    q=vals.get(code,{})
    free_shares=q.get('free_shares'); turnover=np.nan
    vol=last_vol
    if pd.notna(free_shares) and free_shares and pd.notna(vol): turnover=float(vol)*100/float(free_shares)*100
    return {'code':code,'筹码平均成本':avg,'筹码集中度%':conc,'90%成本区间宽度%':r90,'现价相对筹码成本%':pos,
            'quote_price':q.get('quote_price'),'turnover_rt':turnover,'pe_ttm':q.get('pe_ttm'),
            'float_mv_rt':q.get('float_mv'),'total_mv_rt':q.get('total_mv'),'pb':q.get('pb'),'valuation_date':q.get('valuation_date')}
rows=[]; cache_rows={}
for _,r in x.iterrows():
    rr=make_row(r.code); cache_rows[r.code]=rr; rows.append({'code':r.code,**rr})
mdf=pd.DataFrame(rows)
xx=x.merge(mdf,on='code',how='left',validate='one_to_one')
xx['总市值(亿)']=xx.total_mv_rt/1e8
xx['流通市值(亿)']=xx.float_mv_rt/1e8
xx['PE(TTM)']=xx.pe_ttm
xx['市净率']=xx.pb
xx['换手率%']=xx.turnover_rt
xx['筹码集中度分']=xx['筹码集中度%'].rank(pct=True,method='average').mul(100).round(1)
def cost_fit(v):
    try:
        v=float(v)
    except (ValueError,TypeError):
        return 30.0
    if not np.isfinite(v):return 30.0
    a=abs(v)
    if a<=3:return 100.0
    if a<=8:return 100-(a-3)*8
    if a<=15:return 60-(a-8)*4.29
    return max(20.,30-(a-15))
def valuation_score(pe):
    try:
        pe=float(pe)
    except (ValueError,TypeError):
        return 20.0
    if not np.isfinite(pe) or pe<=0:return 20.0
    if pe<=30:return float(np.clip(95-abs(pe-20)*.5,75,95))
    if pe<=60:return float(np.clip(75-(pe-30)*.67,55,75))
    if pe<=100:return float(np.clip(55-(pe-60)*.625,30,55))
    return 20.
def turnover_score(t):
    if not np.isfinite(t):return 30.
    if t<.3:return 30+t/.3*30
    if t<1:return 60+(t-.3)/.7*25
    if t<=7:return float(np.clip(100-abs(t-3.5)*3.5,80,100))
    if t<=12:return float(np.clip(90-(t-7)*4,70,90))
    return float(np.clip(70-(t-12)*2,20,70))
def cap_score(v):
    if not np.isfinite(v) or v<=0:return 30.
    lv=np.log10(v)
    if 50<=v<=300:return 100.
    if 20<=v<50:return 70+(lv-np.log10(20))/(np.log10(50)-np.log10(20))*30
    if 300<v<=800:return 100-(lv-np.log10(300))/(np.log10(800)-np.log10(300))*20
    if 800<v<=1500:return 80-(lv-np.log10(800))/(np.log10(1500)-np.log10(800))*20
    if v<20:return max(30.,30+(lv-np.log10(5))/(np.log10(20)-np.log10(5))*40)
    return max(35.,60-(lv-np.log10(1500))*40)
xx['成本贴合分']=xx['现价相对筹码成本%'].apply(cost_fit).round(1)
xx['估值分']=xx['PE(TTM)'].apply(valuation_score).round(1)
xx['换手率分']=xx['换手率%'].apply(turnover_score).round(1)
xx['市值分']=xx['总市值(亿)'].apply(cap_score).round(1)
xx['多因子评分']=(.45*xx.recommend_score+.15*xx['筹码集中度分']+.10*xx['成本贴合分']+.10*xx['估值分']+.10*xx['换手率分']+.10*xx['市值分']).round(2)
ta=xx['多因子评分'].quantile(.85); tb=xx['多因子评分'].quantile(.50)
a=(xx['多因子评分']>=ta)&(xx.confirm_score>=4)
b=(~a)&(((xx['多因子评分']>=tb)&(xx.confirm_score>=3))|(xx.confirm_score>=5))
xx['多因子等级']=np.select([a,b],['A','B'],default='C')
order={'A':0,'B':1,'C':2}; xx['_ord']=xx['多因子等级'].map(order)
xx=xx.sort_values(['_ord','多因子评分','总市值(亿)'],ascending=[True,False,False]).drop(columns='_ord').reset_index(drop=True)
outcols=['代码' if False else 'code','name']
# Standard Chinese output columns, matching the prior report.
ren={'code':'代码','name':'名称','推荐等级':'推荐等级','recommend_score':'推荐评分','confirm_score':'信号确认分','latest_date':'数据截至','latest_close':'最新收盘','date_i':'前低日期','low_i':'前低价','date_j':'本次低日期','low_j':'本次低价','dif_gain':'DIF抬高','hist_gain':'MACD柱抬高','dif':'当前DIF','dea':'当前DEA','hist':'当前MACD柱','above_ma20':'站上MA20','above_ma60':'站上MA60','dist_low_pct':'距背离低点%','vol_trend_5_20':'近5日/20日均量','score_pct':'强度分位','score':'原综合分'}
out=xx.rename(columns=ren).copy()
out['总市值(亿)']=out['总市值(亿)'].round(2); out['流通市值(亿)']=out['流通市值(亿)'].round(2)
out['估值日期']=out.valuation_date
out['最新成交额(亿)']=(out.amount/1e8).round(2)
out['强度分位']=out['强度分位'].round(3)
cols=['代码','名称','多因子等级','多因子评分','推荐等级','推荐评分','信号确认分','总市值(亿)','流通市值(亿)','PE(TTM)','市净率','换手率%','筹码平均成本','筹码集中度%','90%成本区间宽度%','现价相对筹码成本%','筹码集中度分','成本贴合分','估值分','换手率分','市值分','估值日期','数据截至','最新收盘','前低日期','前低价','本次低日期','本次低价','DIF抬高','MACD柱抬高','当前DIF','当前DEA','当前MACD柱','站上MA20','站上MA60','距背离低点%','近5日/20日均量','最新成交额(亿)','强度分位','原综合分']
out[cols].to_csv(MOUT,index=False,encoding='utf-8-sig')
print('valuation date',out['估值日期'].value_counts().to_dict())
print('multifactor grade',out['多因子等级'].value_counts().to_dict(),'A_min',ta,'B_min',tb)
print('missing valuation',out['PE(TTM)'].isna().sum(),'missing chips',out['筹码平均成本'].isna().sum())
print(out.groupby('多因子等级').agg(count=('代码','size'),min_score=('多因子评分','min'),max_score=('多因子评分','max')).to_string())
print(out.head(30)[['代码','名称','多因子等级','多因子评分','PE(TTM)','换手率%','筹码平均成本']].to_string(index=False))
