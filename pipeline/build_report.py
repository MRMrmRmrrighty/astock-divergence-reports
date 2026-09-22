import os, json, base64, html, re
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'outputs')
CH = os.path.join(OUT, 'charts___TARGET_ND__')
os.makedirs(CH, exist_ok=True)
plt.rcParams['font.sans-serif'] = ['PingFang SC', 'Hiragino Sans GB', 'Noto Sans CJK SC', 'WenQuanYi Zen Hei', 'Songti SC', 'Arial Unicode MS', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False
plt.rcParams['figure.facecolor'] = 'white'

mdf = pd.read_csv(os.path.join(OUT, 'A股底背离推荐等级排序_多因子_数据至__TARGET_DATE__.csv'), dtype={'代码': str})
raw = pd.read_csv(os.path.join(ROOT, 'work', 'all_bottom_divergence_raw___TARGET_ND__.csv'), dtype={'code': str})
raw['name'] = raw['name'].astype(str)
filtered = raw[(raw.strong) & (~raw.name.str.contains('ST|退', na=False)) & (raw.close >= 2) & (raw.amount >= 50000000) & (raw.days_ago <= 15) & (raw.dist_low_pct <= 8)].copy()

# 将原始信号中的前后低点、DIF低点合并回多因子结果，专供图表标注。
signal_cols = ['code','date_i','low_i','date_j','low_j','dif_i','dif_j','hist_i','hist_j','type','gap']
raw_for_merge = raw[signal_cols].drop_duplicates(['code','date_i','date_j']).rename(columns={'code':'代码'})
mdf = mdf.merge(raw_for_merge, left_on=['代码','前低日期','本次低日期'], right_on=['代码','date_i','date_j'], how='left')

def load_df(code):
    rr = filtered.loc[filtered.code == code]
    if rr.empty:
        raise ValueError(f'no raw row for {code}')
    market = int(rr.iloc[0].market)
    prefix = 'sh' if market == 1 else 'sz'
    obj = json.load(open(os.path.join(ROOT, 'work', 'cache', f'{prefix}{code}.json'), encoding='utf-8'))
    df = pd.DataFrame(obj['k'], columns=['date','open','close','high','low','volume','amount','amplitude','pct','chg','turnover'])
    df['ema12'] = df.close.ewm(span=12, adjust=False).mean()
    df['ema26'] = df.close.ewm(span=26, adjust=False).mean()
    df['dif'] = df.ema12 - df.ema26
    df['dea'] = df.dif.ewm(span=9, adjust=False).mean()
    df['macd'] = (df.dif - df.dea) * 2
    for w in [5, 10, 20, 60]:
        df[f'ma{w}'] = df.close.rolling(w).mean()
        df[f'vma{w}'] = df.volume.rolling(w).mean()
    df['date'] = pd.to_datetime(df.date)
    return df

def local_extreme_point(d, anchor, value_col, radius=5):
    """返回锚点日期附近 radius 个交易日内的极值坐标。"""
    d2 = d.reset_index(drop=True)
    pos_map = {dt: k for k, dt in enumerate(d2.date)}
    ai = pos_map.get(pd.to_datetime(anchor))
    if ai is None:
        return None, None
    lo, hi = max(0, ai-radius), min(len(d2), ai+radius+1)
    seg = d2.iloc[lo:hi].copy()
    idx = seg[value_col].idxmin()
    return d2.loc[idx, 'date'], d2.loc[idx, value_col]

def make_chart(r):
    df = load_df(r['代码'])
    d = df.tail(180).reset_index(drop=True)
    pos_map = {dt: k for k, dt in enumerate(d.date)}
    di = pd.to_datetime(r['date_i'])
    dj = pd.to_datetime(r['date_j'])
    xi = pos_map.get(di)
    xj = pos_map.get(dj)

    fig, axes = plt.subplots(3, 1, figsize=(12, 9.8), sharex=True, gridspec_kw={'height_ratios':[3,1,1.45], 'hspace':0.08})
    ax = axes[0]
    up = d.close >= d.open
    ax.vlines(d.date, d.low, d.high, color=np.where(up, '#d94f43', '#26a269'), lw=.65, alpha=.45)
    ax.plot(d.date, d.close, color='#1f4e79', lw=1.7, label='收盘(前复权)')
    ax.plot(d.date, d.ma20, color='#e08214', lw=1, label='MA20')
    ax.plot(d.date, d.ma60, color='#7b52ab', lw=1, label='MA60')

    # 价格背离低点：绿色▼=前低；红色★=本次底背离低点。
    if xi is not None and xj is not None:
        ax.plot([di, dj], [r['low_i'], r['low_j']], color='#d94f43', lw=1.7, ls='--', alpha=.95, zorder=6, label='价格低点降低')
    if xi is not None:
        ax.scatter(di, r['low_i'], marker='v', s=125, color='#26a269', edgecolors='white', linewidths=1.2, zorder=8, label='前低')
        ax.annotate(f'前低 {di:%Y-%m-%d}\n价格 {r["low_i"]:.2f}', (di, r['low_i']), xytext=(0,-38), textcoords='offset points', ha='center', fontsize=9, color='#1b6b47', weight='bold', bbox=dict(boxstyle='round,pad=0.25', fc='white', ec='#26a269', alpha=.92), arrowprops=dict(arrowstyle='-', color='#26a269', lw=.8))
    if xj is not None:
        ax.scatter(dj, r['low_j'], marker='*', s=210, color='#d94f43', edgecolors='white', linewidths=1.0, zorder=8, label='本次底背离低点')
        ax.annotate(f'背离低点 {dj:%Y-%m-%d}\n价格 {r["low_j"]:.2f}', (dj, r['low_j']), xytext=(0,36), textcoords='offset points', ha='center', fontsize=10, color='#a02a20', weight='bold', bbox=dict(boxstyle='round,pad=0.28', fc='#fff5f4', ec='#d94f43', alpha=.95), arrowprops=dict(arrowstyle='-', color='#d94f43', lw=.9))

    ax.set_title(f"{r['代码']} {r['名称']}｜多因子等级 {r['多因子等级']}｜评分 {r['多因子评分']:.2f}｜K线截至 {r['数据截至']} 收盘 {r['最新收盘']:.2f}", fontsize=15, weight='bold', loc='left')
    ax.legend(loc='best', ncol=3, fontsize=9)
    ax.grid(True, alpha=.18)
    ax.margins(y=.13)

    axv = axes[1]
    colors = np.where(up, '#d94f43', '#26a269')
    axv.bar(d.date, d.volume, color=colors, width=1, alpha=.75)
    axv.plot(d.date, d.vma5, color='#1f4e79', lw=1, label='VMA5')
    axv.plot(d.date, d.vma20, color='#e08214', lw=1, label='VMA20')
    axv.set_ylabel('成交量(手)')
    axv.legend(loc='best', ncol=2, fontsize=9)
    axv.grid(True, alpha=.18)

    axm = axes[2]
    axm.bar(d.date, d['macd'], color=np.where(d['macd'] >= 0, '#d94f43', '#26a269'), width=1, alpha=.62, label='MACD柱')
    axm.plot(d.date, d.dif, color='#1f4e79', lw=1.3, label='DIF')
    axm.plot(d.date, d.dea, color='#e08214', lw=1.3, label='DEA')
    axm.axhline(0, color='#555', lw=.7)

    # MACD DIF 低点：取前后低点日期附近5个交易日的实际DIF最低点。
    di_dif, y_dif_i = local_extreme_point(d, di, 'dif')
    dj_dif, y_dif_j = local_extreme_point(d, dj, 'dif')
    if di_dif is not None and dj_dif is not None:
        axm.plot([di_dif, dj_dif], [y_dif_i, y_dif_j], color='#1b6b47', lw=1.8, ls='--', alpha=.95, zorder=6, label='DIF低点抬高')
        axm.scatter([di_dif], [y_dif_i], marker='o', s=65, color='#26a269', edgecolors='white', linewidths=.9, zorder=8)
        axm.scatter([dj_dif], [y_dif_j], marker='o', s=85, color='#d94f43', edgecolors='white', linewidths=.9, zorder=8)
        axm.annotate(f'DIF低点 {y_dif_j:.3f}', (dj_dif, y_dif_j), xytext=(0,18), textcoords='offset points', ha='center', fontsize=9, color='#1b6b47', weight='bold', bbox=dict(boxstyle='round,pad=0.22', fc='white', ec='#26a269', alpha=.92), arrowprops=dict(arrowstyle='-', color='#26a269', lw=.7))

    # 用贯通竖线清楚对应价格低点与MACD低点。
    if xi is not None:
        for a in [ax, axm]: a.axvline(di, color='#26a269', lw=.9, ls=':', alpha=.65, zorder=2)
    if xj is not None:
        for a in [ax, axm]: a.axvline(dj, color='#d94f43', lw=1.0, ls=':', alpha=.75, zorder=2)

    axm.set_ylabel('MACD')
    axm.legend(loc='best', ncol=3, fontsize=9)
    axm.grid(True, alpha=.18)
    axm.margins(y=.18)
    fig.autofmt_xdate(rotation=0)
    fn = os.path.join(CH, f"{r['代码']}_{r['名称']}.png")
    fig.savefig(fn, dpi=160, bbox_inches='tight')
    plt.close(fig)
    return os.path.basename(fn)

# 生成排序后的前20张图。
chart_df = mdf.head(20).copy()
chart_rows = []
for rank, r in chart_df.iterrows():
    fn = make_chart(r)
    chart_rows.append({'排名': rank + 1, '图': fn, **r.to_dict()})
chart_rep = pd.DataFrame(chart_rows)
chart_rep.to_csv(os.path.join(OUT, 'A股底背离多因子重点20只_数据至__TARGET_DATE__.csv'), index=False, encoding='utf-8-sig')

parts = []
parts.append('''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>A股底背离多因子推荐等级排序报告</title>
<style>
body{font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;margin:32px auto;max-width:1360px;color:#17233d;line-height:1.55}
h1{font-size:30px;margin-bottom:8px} h2{margin-top:36px;font-size:22px;border-left:5px solid #1f4e79;padding-left:10px}
.meta{background:#f5f8fb;border:1px solid #dbe6ef;padding:14px 18px;border-radius:10px}
.badges{display:flex;gap:12px;flex-wrap:wrap;margin:14px 0}
.badge{padding:10px 14px;border-radius:10px;border:1px solid #dbe6ef;background:#fff;min-width:155px}
.badge b{display:block;font-size:22px}
.badge.A{border-left:6px solid #c0392b}.badge.B{border-left:6px solid #e08214}.badge.C{border-left:6px solid #7b52ab}
.card{border:1px solid #dbe6ef;border-radius:12px;padding:18px;margin-top:18px;box-shadow:0 2px 8px rgba(20,40,80,.05)}
table{border-collapse:collapse;width:100%;font-size:12px;margin-top:14px}
th,td{border-bottom:1px solid #e5eaf0;padding:7px;text-align:left;white-space:nowrap}
th{position:sticky;top:0;background:#eef4f9;z-index:2}
img{max-width:100%;height:auto;border:1px solid #dbe6ef;border-radius:8px;margin-top:12px}
.small{color:#64748b;font-size:13px}
.gA,.gB,.gC{display:inline-block;min-width:24px;text-align:center;border-radius:6px;color:#fff;font-weight:700}
.gA{background:#c0392b}.gB{background:#e08214}.gC{background:#7b52ab}
.note{background:#fff8e6;border:1px solid #f0dbab;padding:12px 14px;border-radius:10px;margin-top:12px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:10px;margin-top:10px}
.kv{background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:8px 10px;font-size:13px}
</style></head><body>''')
snapshot_raw = str(mdf.attrs.get('quote_snapshot', ''))
if len(snapshot_raw) >= 14:
    snapshot = f"{snapshot_raw[:4]}-{snapshot_raw[4:6]}-{snapshot_raw[6:8]} {snapshot_raw[8:10]}:{snapshot_raw[10:12]}:{snapshot_raw[12:14]}"
else:
    snapshot = '__TARGET_DATE__ 收盘'
parts.append('<h1>A股底背离多因子推荐等级排序报告</h1>')
parts.append(f'''<div class="meta"><b>K线/MACD信号：</b>__TARGET_DATE__ 前复权日K（个别停牌/延迟股票为其最新可得交易日）<br>
<b>估值/换手快照：</b>{snapshot}，来源为东方财富数据中心收盘估值；换手率按当日成交量/自由流通A股回算<br>
<b>筹码指标：</b>近250个交易日量价分布近似；价格区间做三角形分布，使用120日半衰期衰减；筹码平均成本、±10%成本集中度、90%成本区间宽度均由该分布估算，非券商精确筹码数据<br>
<b>范围：</b>沪深 A 股，剔除 ST/退市标的和北交所<br>
<b>多因子评分：</b>技术信号 45% + 筹码集中度 15% + 成本贴合度 10% + 估值 10% + 换手率 10% + 市值 10%<br>
<b>等级规则：</b>A=多因子评分前15%且信号确认分≥4；B=评分前50%且确认分≥3，或确认分≥5；C=其余观察</div>''')
counts = mdf['多因子等级'].value_counts().reindex(['A','B','C']).fillna(0).astype(int)
parts.append('<div class="badges">')
for g, desc in [('A','多因子强 + 技术确认'), ('B','中等强度 / 待确认'), ('C','仅信号观察')]:
    parts.append(f"<div class='badge {g}'><span>{g}级</span><b>{counts[g]}</b><small>{desc}</small></div>")
parts.append('</div>')
parts.append('<div class="note">以下图表为多因子等级排序后的<b>前 20 只</b>；完整 175 只排序见 <code>A股底背离推荐等级排序_多因子_数据至__TARGET_DATE__.csv</code>。<br><b>图例：</b>绿色▼=前低，红色★=本次底背离低点；红色虚线=价格低点降低，绿色虚线=对应区间DIF低点抬高，竖虚线用于对齐价格低点和MACD低点。</div>')

def fmt_pe(v):
    try:
        v = float(v)
        return f"{v:.2f}" if v > 0 else '亏损'
    except Exception:
        return '—'

def table(df, full=True):
    x = df.copy()
    if not full:
        x = x[['代码','名称','多因子等级','多因子评分','推荐评分','信号确认分','总市值(亿)','PE(TTM)','换手率%','筹码平均成本','现价相对筹码成本%','筹码集中度%']]
    tbl = ['<table><thead><tr><th>排名</th><th>等级</th><th>代码</th><th>名称</th><th>多因子</th><th>技术</th><th>确认</th><th>总市值(亿)</th><th>PE(TTM)</th><th>PB</th><th>换手</th><th>筹码成本</th><th>现价/成本</th><th>±10%集中</th><th>90%区间宽</th><th>估值分</th><th>换手分</th><th>市值分</th></tr></thead><tbody>']
    for rank, (_, r) in enumerate(x.iterrows(), 1):
        tbl.append(
            f"<tr><td>{rank}</td><td><span class='g{r['多因子等级']}'>{r['多因子等级']}</span></td><td>{r['代码']}</td><td>{html.escape(str(r['名称']))}</td>"
            f"<td>{r['多因子评分']:.2f}</td><td>{r['推荐评分']:.2f}</td><td>{int(r['信号确认分'])}</td><td>{r['总市值(亿)']:.1f}</td><td>{fmt_pe(r['PE(TTM)'])}</td><td>{r['市净率']:.2f}</td>"
            f"<td>{r['换手率%']:.2f}%</td><td>{r['筹码平均成本']:.2f}</td><td>{r['现价相对筹码成本%']:+.1f}%</td><td>{r['筹码集中度%']:.1f}%</td><td>{r['90%成本区间宽度%']:.1f}%</td>"
            f"<td>{r['估值分']:.0f}</td><td>{r['换手率分']:.0f}</td><td>{r['市值分']:.0f}</td></tr>"
        )
    tbl.append('</tbody></table>')
    return ''.join(tbl)

parts.append('<h2>A级明细</h2>' + table(mdf[mdf['多因子等级']=='A'], full=True))
parts.append('<h2>B级明细</h2>' + table(mdf[mdf['多因子等级']=='B'], full=True))
parts.append('<h2>C级明细</h2>' + table(mdf[mdf['多因子等级']=='C'], full=True))

for _, r in chart_rep.iterrows():
    p = os.path.join(CH, r['图'])
    with open(p, 'rb') as f:
        b = base64.b64encode(f.read()).decode()
    parts.append(f"<div class='card'><h2>{int(r['排名'])}. {r['代码']} {html.escape(str(r['名称']))}｜<span class='g{r['多因子等级']}'>{r['多因子等级']}</span> 多因子 {r['多因子评分']:.2f}</h2>")
    parts.append('<div class="grid">')
    parts.append(f"<div class='kv'><b>估值：</b>总市值 {r['总市值(亿)']:.1f}亿｜PE(TTM) {fmt_pe(r['PE(TTM)'])}｜PB {r['市净率']:.2f}｜换手 {r['换手率%']:.2f}%</div>")
    parts.append(f"<div class='kv'><b>筹码：</b>平均成本 {r['筹码平均成本']:.2f}｜现价/成本 {r['现价相对筹码成本%']:+.1f}%｜±10%集中 {r['筹码集中度%']:.1f}%｜90%区间宽 {r['90%成本区间宽度%']:.1f}%</div>")
    parts.append(f"<div class='kv'><b>MACD：</b>DIF {r['当前DIF']:.3f}｜DEA {r['当前DEA']:.3f}｜柱 {r['当前MACD柱']:.3f}｜距背离低点 {r['距背离低点%']:.1f}%</div>")
    parts.append(f"<div class='kv'><b>均线/流动性：</b>MA20 {r['站上MA20']}｜MA60 {r['站上MA60']}｜最新成交额 {r['最新成交额(亿)']:.2f}亿</div>")
    parts.append('</div>')
    parts.append(f"<img src='data:image/png;base64,{b}' alt='{r['代码']}'>")
    parts.append('</div>')

parts.append('<p class="small">本结果为量化筛选与多因子横向比较，不构成投资建议；筹码分布为量价近似而非精确股东成本，估值/换手为 __TARGET_DATE__ 收盘口径，行业与盈利质量未单独建模。底背离可能钝化或失败，需结合基本面、风险事件、流动性和止损纪律。</p>')
parts.append('</body></html>')
out_html = os.path.join(OUT, 'A股底背离多因子推荐等级排序报告_数据至__TARGET_DATE__.html')
with open(out_html, 'w', encoding='utf-8') as f:
    f.write('\n'.join(parts))
print('charts', len(chart_rep))
print('html', out_html, os.path.getsize(out_html))
