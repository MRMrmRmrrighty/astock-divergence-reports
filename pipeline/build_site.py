#!/usr/bin/env python3
"""部署报告到 GitHub Pages 站点：生成苹果风格首页、复制文件并推送到 main。"""
import os
import shutil
import glob
import subprocess
import datetime
import re
import sys
import json
from pathlib import Path
from urllib.parse import quote

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'outputs')
SITE = ROOT


def run(cmd, cwd=None):
    r = subprocess.run(cmd, cwd=cwd or ROOT, capture_output=True, text=True)
    if r.returncode != 0:
        print(f'[deploy] cmd={cmd} rc={r.returncode}\nstderr: {r.stderr[-2000:]}')
        return False
    if r.stdout.strip():
        print(r.stdout.strip()[-1000:])
    return True


def find_reports():
    """按日期倒序返回 (date_str, html_path, csv_path)。"""
    htmls = glob.glob(os.path.join(OUT, 'A股底背离多因子推荐等级排序报告_数据至*.html'))
    htmls += glob.glob(os.path.join(SITE, 'A股底背离多因子推荐等级排序报告_数据至*.html'))
    reports = {}
    for h in htmls:
        m = re.search(r'数据至(\d{4}-\d{2}-\d{2})\.html', os.path.basename(h))
        if m:
            # Newly generated files in outputs override the published root copy.
            reports[m.group(1)] = h
    result = []
    for d in sorted(reports.keys(), reverse=True):
        csv_candidates = [
            os.path.join(OUT, f'A股底背离多因子重点20只_数据至{d}.csv'),
            os.path.join(SITE, f'A股底背离多因子重点20只_数据至{d}.csv'),
        ]
        csv = next((p for p in csv_candidates if os.path.exists(p)), None)
        result.append((d, reports[d], csv))
    return result


def build_trends():
    r = subprocess.run(
        [sys.executable, os.path.join(ROOT, 'pipeline', 'build_trends.py')],
        capture_output=True, text=True,
        env={**os.environ}
    )
    if r.returncode != 0:
        raise RuntimeError('[trends] ' + r.stderr[-2000:])
    print(r.stdout.strip())


def trend_summary():
    """从聚合页读取核心序列，用于首页摘要图表。"""
    path = Path(SITE, 'trends.html')
    text = path.read_text(encoding='utf-8')

    def series(name):
        m = re.search(rf'const {name} = (\[.*?\]);', text)
        return m.group(1) if m else '[]'

    persistent = 0
    stocks_match = re.search(r'const stocks = (\[.*?\]);', text)
    if stocks_match:
        try:
            stocks = json.loads(stocks_match.group(1))
            persistent = sum(
                1 for stock in stocks
                if sum(1 for grade in stock.get('grades', {}).values() if grade == 'A') >= 2
            )
        except (TypeError, ValueError, json.JSONDecodeError):
            persistent = 0

    return {
        'dates': series('dates'),
        'totals': series('totals'),
        'a': series('aData'),
        'avg': series('avgData'),
        'persistent': str(persistent),
    }


def generate_index(reports):
    latest = reports[0]
    summary = trend_summary()
    items = []
    for d, h, c in reports:
        report_href = quote(os.path.basename(h))
        csv_html = ''
        if c:
            csv_href = quote(os.path.basename(c))
            csv_html = f'<a class="csv-link" href="{csv_href}">CSV</a>'
        latest_pill = '<span class="pill">最新</span>' if d == latest[0] else ''
        items.append(f'''
          <article class="report-item">
            <a class="report-main" href="{report_href}">
              <span class="date">{d}{latest_pill}</span>
              <span class="meta">完整多因子榜单 · 底背离候选 · 等级排序</span>
            </a>
            {csv_html}
          </article>''')

    return f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>A股底背离报告中心</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
:root {{
  color-scheme: light dark;
  --bg: #f5f5f7;
  --card: rgba(255,255,255,.76);
  --card-solid: #fff;
  --text: #1d1d1f;
  --muted: #6e6e73;
  --hairline: rgba(0,0,0,.08);
  --blue: #0071e3;
  --red: #ff3b30;
  --shadow: 0 18px 45px rgba(0,0,0,.08);
}}
@media (prefers-color-scheme: dark) {{
  :root {{
    --bg: #000;
    --card: rgba(28,28,30,.72);
    --card-solid: #1c1c1e;
    --text: #f5f5f7;
    --muted: #a1a1a6;
    --hairline: rgba(255,255,255,.12);
    --blue: #0a84ff;
    --red: #ff453a;
    --shadow: 0 18px 45px rgba(0,0,0,.48);
  }}
}}
* {{ box-sizing: border-box; }}
html {{ scroll-behavior: smooth; }}
body {{
  margin: 0;
  min-height: 100vh;
  color: var(--text);
  background:
    radial-gradient(circle at 8% 0%, rgba(0,113,227,.13), transparent 32rem),
    radial-gradient(circle at 100% 10%, rgba(255,59,48,.09), transparent 30rem),
    var(--bg);
  font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "SF Pro Display", "PingFang SC", "Hiragino Sans GB", "Helvetica Neue", sans-serif;
  font-feature-settings: "kern";
  letter-spacing: -.011em;
  line-height: 1.47;
  -webkit-font-smoothing: antialiased;
}}
.wrap {{ width: min(1180px, calc(100% - 48px)); margin: 0 auto; padding: 48px 0 64px; }}
.eyebrow {{ color: var(--muted); font-size: 13px; font-weight: 600; text-transform: uppercase; letter-spacing: .1em; }}
h1 {{ font-size: clamp(31px, 5vw, 44px); line-height: 1.08; letter-spacing: -.025em; font-weight: 700; margin: 10px 0 14px; }}
.hero-copy {{ color: var(--muted); font-size: 17px; max-width: 620px; }}
.hero-meta {{ display: flex; flex-wrap: wrap; gap: 10px; margin-top: 24px; }}
.status {{
  display: inline-flex; align-items: center; gap: 8px;
  border: 1px solid var(--hairline); background: var(--card);
  color: var(--muted); font-size: 13px; padding: 7px 14px; border-radius: 999px;
  backdrop-filter: saturate(180%) blur(20px); -webkit-backdrop-filter: saturate(180%) blur(20px);
}}
.status .dot {{ width: 7px; height: 7px; border-radius: 50%; background: var(--red); box-shadow: 0 0 0 4px rgba(255,59,48,.12); }}
.layout {{ display: grid; grid-template-columns: minmax(0, 1.22fr) minmax(0, .98fr); gap: 20px; align-items: start; margin-top: 30px; }}
.panel {{
  border: 1px solid var(--hairline); border-radius: 24px; background: var(--card);
  box-shadow: var(--shadow); overflow: hidden;
  backdrop-filter: saturate(180%) blur(24px); -webkit-backdrop-filter: saturate(180%) blur(24px);
}}
.panel-head {{ padding: 28px 28px 16px; }}
.panel-kicker {{ font-size: 12px; font-weight: 650; color: var(--muted); letter-spacing: .08em; text-transform: uppercase; }}
.panel-title {{ font-size: 22px; font-weight: 700; letter-spacing: -.02em; margin: 7px 0 5px; }}
.panel-desc {{ color: var(--muted); font-size: 14px; margin: 0; }}
.report-list {{ padding: 4px 12px 14px; }}
.report-item {{
  display: flex; align-items: center; justify-content: space-between; gap: 14px;
  border-radius: 14px; transition: background .2s ease, transform .2s ease;
}}
.report-item + .report-item {{ border-top: 1px solid var(--hairline); }}
.report-main {{ display: flex; flex: 1; min-width: 0; align-items: center; justify-content: space-between; gap: 14px; color: inherit; text-decoration: none; padding: 18px 16px; }}
.report-main:hover {{ background: rgba(0,113,227,.055); }}
.date {{ display: flex; align-items: center; gap: 8px; font-size: 17px; font-weight: 650; letter-spacing: -.01em; white-space: nowrap; }}
.meta {{ color: var(--muted); font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
.pill {{ background: var(--red); color: #fff; font-size: 11px; font-weight: 700; padding: 3px 8px; border-radius: 999px; }}
.csv-link {{
  color: var(--blue); text-decoration: none; font-size: 13px; font-weight: 600;
  border: 1px solid color-mix(in srgb, var(--blue) 28%, transparent);
  padding: 7px 12px; border-radius: 999px; margin-right: 14px; white-space: nowrap;
}}
.csv-link:hover {{ background: color-mix(in srgb, var(--blue) 8%, transparent); }}
.digest {{ padding: 0 28px 28px; }}
.stats {{ display: grid; grid-template-columns: repeat(2, minmax(0,1fr)); gap: 11px; margin-bottom: 20px; }}
.stat {{ border: 1px solid var(--hairline); border-radius: 16px; background: color-mix(in srgb, var(--card-solid) 70%, transparent); padding: 16px; min-width: 0; }}
.stat b {{ display: block; font-size: 25px; letter-spacing: -.025em; font-weight: 700; }}
.stat span {{ display: block; color: var(--muted); font-size: 12px; margin-top: 4px; }}
.stat.red b {{ color: var(--red); }}
.chart-box {{ border: 1px solid var(--hairline); border-radius: 18px; padding: 18px; background: color-mix(in srgb, var(--card-solid) 68%, transparent); }}
.cta {{
  display: flex; align-items: center; justify-content: center; gap: 8px;
  width: 100%; border: 0; border-radius: 14px; margin-top: 18px;
  background: var(--blue); color: #fff; text-decoration: none;
  font-size: 15px; font-weight: 600; padding: 14px 18px; transition: transform .18s ease, opacity .18s ease;
}}
.cta:hover {{ opacity: .9; transform: translateY(-1px); }}
footer {{ margin-top: 34px; color: var(--muted); font-size: 12.5px; text-align: center; }}
@media (max-width: 860px) {{
  .wrap {{ width: min(1180px, calc(100% - 34px)); padding-top: 34px; }}
  .layout {{ grid-template-columns: 1fr; }}
  .meta {{ display: none; }}
}}
</style>
</head>
<body>
  <main class="wrap">
    <section class="hero">
      <div class="eyebrow">A-SHARE QUANTITATIVE MONITOR</div>
      <h1>A股底背离多因子报告中心</h1>
      <p class="hero-copy">自动聚合每日底背离候选，融合推荐等级、估值、换手、筹码与持续性信号，形成可追踪的量化筛选视图。</p>
      <div class="hero-meta">
        <span class="status"><i class="dot"></i>最新数据 {latest[0]}</span>
        <span class="status">共 {len(reports)} 期</span>
        <span class="status">工作日 17:35 自动更新</span>
      </div>
    </section>

    <section class="layout">
      <div class="panel">
        <div class="panel-head">
          <div class="panel-kicker">Daily Reports</div>
          <h2 class="panel-title">报告列表</h2>
          <p class="panel-desc">按日期查看完整报告，或下载每日重点 20 只数据。</p>
        </div>
        <div class="report-list">{''.join(items)}</div>
      </div>

      <div class="panel">
        <div class="panel-head">
          <div class="panel-kicker">Quantitative Digest</div>
          <h2 class="panel-title">聚合量化分析</h2>
          <p class="panel-desc">等级趋势、持续性和多因子评分的核心摘要。</p>
        </div>
        <div class="digest">
          <div class="stats">
            <div class="stat"><b>{summary['totals'] and int(__import__('json').loads(summary['totals'])[-1])}</b><span>最新信号总数</span></div>
            <div class="stat red"><b>{summary['a'] and int(__import__('json').loads(summary['a'])[-1])}</b><span>A级推荐</span></div>
            <div class="stat"><b>{summary['avg'] and float(__import__('json').loads(summary['avg'])[-1]):.1f}</b><span>平均多因子评分</span></div>
            <div class="stat"><b>{summary['persistent']}</b><span>连续A级 ≥2天</span></div>
          </div>
          <div class="chart-box"><canvas id="digestChart" height="200"></canvas></div>
          <a class="cta" href="trends.html">打开完整聚合分析</a>
        </div>
      </div>
    </section>

    <footer>本报告为量化筛选聚合分析，仅供参考，不构成投资建议。数据来源：腾讯 K 线 / 东方财富 / 新浪财经。</footer>
  </main>
<script>
const digestDates = {summary['dates']};
const digestTotals = {summary['totals']};
const digestA = {summary['a']};
const dark = window.matchMedia('(prefers-color-scheme: dark)').matches;
Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;
Chart.defaults.color = dark ? '#a1a1a6' : '#6e6e73';
new Chart(document.getElementById('digestChart'), {{
  type: 'bar',
  data: {{ labels: digestDates, datasets: [
    {{ label: 'A级', data: digestA, backgroundColor: dark ? 'rgba(255,69,58,.82)' : 'rgba(255,59,48,.86)', borderRadius: 8, maxBarThickness: 26, yAxisID: 'y' }},
    {{ label: '总信号', data: digestTotals, type: 'line', borderColor: dark ? '#0a84ff' : '#0071e3', backgroundColor: 'transparent', borderWidth: 3, pointRadius: 4, tension: .35, yAxisID: 'y1' }}
  ]}},
  options: {{
    responsive: true, maintainAspectRatio: false,
    plugins: {{ legend: {{ position: 'bottom', labels: {{ usePointStyle: true, boxWidth: 7, padding: 16 }} }} }},
    scales: {{
      x: {{ grid: {{ display: false }} }},
      y: {{ beginAtZero: true, grid: {{ color: dark ? 'rgba(255,255,255,.08)' : 'rgba(0,0,0,.055)' }} }},
      y1: {{ position: 'right', beginAtZero: true, grid: {{ drawOnChartArea: false }} }}
    }}
  }}
}});
</script>
</body>
</html>'''


def deploy():
    build_trends()
    # GitHub Pages reports are plain static files; skip legacy Jekyll handling.
    Path(SITE, '.nojekyll').touch()
    reports = find_reports()
    if not reports:
        print('[deploy] no reports found')
        return False
    for d, h, c in reports:
        dst = Path(SITE, os.path.basename(h))
        if Path(h).resolve() != dst.resolve():
            shutil.copy2(h, dst)
        if c:
            csv_dst = Path(SITE, os.path.basename(c))
            if Path(c).resolve() != csv_dst.resolve():
                shutil.copy2(c, csv_dst)
    Path(SITE, 'index.html').write_text(generate_index(reports), encoding='utf-8')
    print(f'[deploy] apple-style dashboard generated, {len(reports)} reports listed')
    return True



if __name__ == "__main__":
    if not deploy():
        raise SystemExit(1)
