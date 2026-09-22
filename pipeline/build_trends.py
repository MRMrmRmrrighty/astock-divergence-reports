#!/usr/bin/env python3
"""聚合量化分析：支持前端日期区间筛选的跨日趋势与持续性分析。"""
import os
import glob
import re
import json
import html
import pandas as pd
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'outputs')
SITE = ROOT

TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>A股底背离聚合量化分析</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
:root {
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
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #000;
    --card: rgba(28,28,30,.72);
    --card-solid: #1c1c1e;
    --text: #f5f5f7;
    --muted: #a1a1a6;
    --hairline: rgba(255,255,255,.12);
    --blue: #0a84ff;
    --red: #ff453a;
    --shadow: 0 18px 45px rgba(0,0,0,.48);
  }
}
* { box-sizing: border-box; }
html { scroll-behavior: smooth; }
body {
  margin: 0; min-height: 100vh; color: var(--text);
  background:
    radial-gradient(circle at 5% 0%, rgba(0,113,227,.13), transparent 34rem),
    radial-gradient(circle at 100% 8%, rgba(255,59,48,.09), transparent 30rem),
    var(--bg);
  font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "SF Pro Display", "PingFang SC", "Hiragino Sans GB", "Helvetica Neue", sans-serif;
  letter-spacing: -.011em; line-height: 1.47; -webkit-font-smoothing: antialiased;
}
.topbar {
  position: sticky; top: 0; z-index: 10; display: flex; align-items: center; justify-content: space-between;
  gap: 16px; padding: 16px min(4vw, 38px);
  background: color-mix(in srgb, var(--bg) 72%, transparent);
  border-bottom: 1px solid var(--hairline);
  backdrop-filter: saturate(180%) blur(24px); -webkit-backdrop-filter: saturate(180%) blur(24px);
}
.brand { display: flex; align-items: center; gap: 10px; font-size: 16px; font-weight: 700; letter-spacing: -.02em; }
.brand-dot { width: 9px; height: 9px; border-radius: 50%; background: var(--red); box-shadow: 0 0 0 4px rgba(255,59,48,.12); }
.back {
  display: inline-flex; align-items: center; gap: 7px; color: var(--blue); text-decoration: none;
  font-size: 14px; font-weight: 600; padding: 8px 13px; border-radius: 999px;
  border: 1px solid color-mix(in srgb, var(--blue) 24%, transparent);
}
.back:hover { background: color-mix(in srgb, var(--blue) 8%, transparent); }
main { width: min(1180px, calc(100% - 44px)); margin: 0 auto; padding: 38px 0 72px; }
.eyebrow { color: var(--muted); font-size: 12.5px; font-weight: 650; text-transform: uppercase; letter-spacing: .1em; }
h1 { font-size: clamp(30px, 5vw, 42px); line-height: 1.08; letter-spacing: -.025em; font-weight: 700; margin: 9px 0 13px; }
.hero-copy { color: var(--muted); font-size: 16px; max-width: 780px; margin: 0; }
.controls {
  margin-top: 26px; padding: 20px; border: 1px solid var(--hairline); border-radius: 22px;
  background: var(--card); box-shadow: var(--shadow);
  backdrop-filter: saturate(180%) blur(24px); -webkit-backdrop-filter: saturate(180%) blur(24px);
}
.control-row { display: flex; align-items: center; justify-content: space-between; gap: 20px; }
.field { display: flex; align-items: center; gap: 10px; }
label { color: var(--muted); font-size: 13px; font-weight: 600; }
input[type=date] {
  color: var(--text); font: inherit; font-size: 14px; font-weight: 600;
  border: 1px solid var(--hairline); background: color-mix(in srgb, var(--card-solid) 78%, transparent);
  border-radius: 12px; padding: 9px 11px; outline: none;
}
input[type=date]:focus { box-shadow: 0 0 0 3px color-mix(in srgb, var(--blue) 24%, transparent); border-color: var(--blue); }
.chips { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.chip {
  appearance: none; border: 1px solid var(--hairline); background: transparent; color: var(--muted);
  font: inherit; font-size: 13px; font-weight: 600; padding: 8px 14px; border-radius: 999px; cursor: pointer;
  transition: all .18s ease;
}
.chip:hover { color: var(--text); transform: translateY(-1px); }
.chip.active { background: var(--text); color: var(--bg); border-color: transparent; }
.reset { color: var(--blue); background: transparent; border: 0; font: inherit; font-size: 13px; font-weight: 600; cursor: pointer; padding: 8px 4px; }
.range-summary { margin-top: 14px; color: var(--muted); font-size: 13px; transition: color .2s ease; }
.range-summary.notice { color: var(--red); font-weight: 600; }
.metrics { display: grid; grid-template-columns: repeat(4, minmax(0,1fr)); gap: 13px; margin: 22px 0 16px; }
.metric, .chart-panel, .table-panel {
  border: 1px solid var(--hairline); border-radius: 22px; background: var(--card); box-shadow: var(--shadow);
  backdrop-filter: saturate(180%) blur(24px); -webkit-backdrop-filter: saturate(180%) blur(24px);
}
.metric { padding: 20px; }
.metric b { display: block; font-size: clamp(24px,3vw,31px); font-weight: 700; letter-spacing: -.03em; }
.metric span { display: block; color: var(--muted); font-size: 12.5px; margin-top: 6px; }
.metric.red b { color: var(--red); }
.metric.green b { color: #30d158; }
.section { margin-top: 30px; }
.section-head { margin: 0 4px 14px; }
.section-head.chart-head {
  display: flex; align-items: flex-start; justify-content: space-between;
  gap: 16px;
}
.select-all {
  display: inline-flex; align-items: center; gap: 8px;
  border: 1px solid var(--hairline); border-radius: 999px;
  background: var(--card-solid); color: var(--text);
  font-size: 13px; font-weight: 600; padding: 7px 12px;
  cursor: pointer; user-select: none; white-space: nowrap;
  transition: transform .18s ease, border-color .18s ease, background .18s ease;
}
.select-all:hover { transform: translateY(-1px); border-color: color-mix(in srgb, var(--blue) 35%, transparent); }
.select-all input {
  appearance: none; -webkit-appearance: none; position: relative;
  width: 34px; height: 21px; margin: 0; border: 0; border-radius: 999px;
  background: color-mix(in srgb, var(--muted) 28%, transparent);
  transition: background .2s ease; cursor: pointer; flex: 0 0 auto;
}
.select-all input::before {
  content: ""; position: absolute; top: 2px; left: 2px;
  width: 17px; height: 17px; border-radius: 50%; background: #fff;
  box-shadow: 0 1px 3px rgba(0,0,0,.18);
  transition: transform .2s ease;
}
.select-all input:checked { background: var(--blue); }
.select-all input:checked::before { transform: translateX(13px); }
.section-head h2 { font-size: 21px; font-weight: 700; letter-spacing: -.022em; margin: 0 0 4px; }
.section-head p { color: var(--muted); font-size: 14px; margin: 0; }
.chart-panel { padding: 22px; }
.chart-stage { position: relative; height: 310px; }
.chart-stage.compact { height: 260px; }
.chart-stage.tall { height: 540px; }
.grid-2 { display: grid; grid-template-columns: repeat(2, minmax(0,1fr)); gap: 18px; }
.table-panel { padding: 8px 0 4px; overflow: hidden; }
.table-scroll { overflow-x: auto; max-height: 660px; overflow-y: auto; }
table { width: 100%; border-collapse: collapse; }
th {
  position: sticky; top: 0; z-index: 2; text-align: left; color: var(--muted); font-size: 12px; font-weight: 650;
  padding: 14px 20px; border-bottom: 1px solid var(--hairline); background: var(--card-solid); white-space: nowrap;
}
td { padding: 15px 20px; border-bottom: 1px solid var(--hairline); font-size: 14px; white-space: nowrap; }
tr:last-child td { border-bottom: 0; }
tbody tr { transition: background .18s ease; }
tbody tr:hover { background: color-mix(in srgb, var(--blue) 5%, transparent); }
.empty { color: var(--muted); text-align: center; padding: 34px 20px; }
code.code { font-family: ui-monospace, SF Mono, Menlo, monospace; font-size: 12.8px; color: var(--muted); }
.disclaimer { color: var(--muted); font-size: 12.5px; text-align: center; margin-top: 42px; }
@media (max-width: 900px) {
  main { width: min(1180px, calc(100% - 30px)); padding-top: 28px; }
  .metrics { grid-template-columns: repeat(2, minmax(0,1fr)); }
  .grid-2 { grid-template-columns: 1fr; }
  .chart-stage.tall { height: 470px; }
  .topbar { padding: 13px 18px; }
  .control-row { align-items: stretch; flex-direction: column; gap: 14px; }
  .field { justify-content: space-between; }
}
</style>
</head>
<body>
<nav class="topbar">
  <div class="brand"><span class="brand-dot"></span>A股底背离监测</div>
  <a class="back" href="index.html">返回报告中心</a>
</nav>
<main>
  <header>
    <div class="eyebrow">Aggregate Quantitative Analysis</div>
    <h1>聚合量化分析</h1>
    <p class="hero-copy">选择日期区间后，等级分布、多因子均值、信号持续性、连续 A 级股票与 Top 30 评分走势会同步重新计算。</p>
  </header>

  <section class="controls" aria-label="日期区间筛选">
    <div class="control-row">
      <div class="field">
        <label for="startDate">开始日期</label>
        <input type="date" id="startDate">
        <label for="endDate">结束日期</label>
        <input type="date" id="endDate">
      </div>
      <div class="chips" id="rangeChips"></div>
    </div>
    <div class="range-summary" id="rangeSummary"></div>
  </section>

  <section class="metrics" aria-live="polite">
    <div class="metric"><b id="metricTotal">—</b><span>区间末信号总数</span></div>
    <div class="metric red"><b id="metricA">—</b><span>区间末 A 级推荐</span></div>
    <div class="metric"><b id="metricScore">—</b><span>区间平均多因子评分</span></div>
    <div class="metric green"><b id="metricPersist">—</b><span>连续 A 级 ≥2天</span></div>
  </section>

  <section class="section">
    <div class="section-head"><h2>信号总量与等级分布</h2><p>分组展示 A / B / C 级数量，并叠加总信号趋势。</p></div>
    <div class="chart-panel"><div class="chart-stage compact"><canvas id="chart1"></canvas></div></div>
  </section>

  <section class="section">
    <div class="section-head"><h2>多因子核心均值</h2><p>平均评分、PE(TTM)、换手率与筹码集中度变化。</p></div>
    <div class="chart-panel"><div class="chart-stage"><canvas id="chart2"></canvas></div></div>
  </section>

  <section class="section">
    <div class="section-head"><h2>连续A级推荐股</h2><p>当前区间内至少 2 个交易日保持 A 级的候选。</p></div>
    <div class="table-panel"><div class="table-scroll">
      <table><thead><tr><th>代码</th><th>名称</th><th>等级变化</th><th>评分变化</th><th>A级天数</th><th>出现天数</th></tr></thead>
      <tbody id="persistentTable"></tbody></table>
    </div></div>
  </section>

  <div class="grid-2">
    <section class="section">
      <div class="section-head"><h2>信号持续性分布</h2><p>当前区间内每只候选股出现的天数分布。</p></div>
      <div class="chart-panel"><div class="chart-stage compact"><canvas id="chart3"></canvas></div></div>
    </section>
    <section class="section">
      <div class="section-head chart-head">
        <div>
          <h2>Top 30 评分走势</h2>
          <p>按当前区间的出现天数和最高评分排序，底部图例显示股票名。</p>
        </div>
        <label class="select-all" for="topSelectAll">
          <input type="checkbox" id="topSelectAll" checked>
          全选
        </label>
      </div>
      <div class="chart-panel"><div class="chart-stage tall"><canvas id="chart4"></canvas></div></div>
    </section>
  </div>

  <p class="disclaimer">本报告为量化筛选聚合分析，仅供参考，不构成投资建议。</p>
</main>
<script>
const allDates = __DATES__;
const totals = __TOTALS__;
const aData = __ADATA__;
const bData = __BDATA__;
const cData = __CDATA__;
const avgData = __AVGDATA__;
const peData = __PEDATA__;
const trData = __TRDATA__;
const concData = __CONCDATA__;
const stocks = __STOCKS__;
const startDateInput = document.getElementById('startDate');
const endDateInput = document.getElementById('endDate');
const rangeChips = document.getElementById('rangeChips');
const rangeSummary = document.getElementById('rangeSummary');
const persistentTable = document.getElementById('persistentTable');
const metricTotal = document.getElementById('metricTotal');
const metricA = document.getElementById('metricA');
const metricScore = document.getElementById('metricScore');
const metricPersist = document.getElementById('metricPersist');
const topSelectAll = document.getElementById('topSelectAll');
const dark = window.matchMedia('(prefers-color-scheme: dark)').matches;
const gridColor = dark ? 'rgba(255,255,255,.08)' : 'rgba(0,0,0,.055)';
Chart.defaults.color = dark ? '#a1a1a6' : '#6e6e73';
Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;
const baseOptions = {
  responsive: true,
  maintainAspectRatio: false,
  animation: { duration: 450 },
  interaction: { mode: 'index', intersect: false },
  plugins: { legend: { position: 'bottom', labels: { usePointStyle: true, boxWidth: 7, padding: 16 } } }
};
function sliceSeries(values, indexes) { return indexes.map(i => values[i]); }
function fmt(n, digits=1) { return Number(n).toFixed(digits); }
function hueForCode(code) {
  let h = 0;
  for (const ch of String(code)) h = (h * 31 + ch.charCodeAt(0)) % 360;
  return h;
}
function arrow(first, last) {
  if (last > first) return '📈';
  if (last < first) return '📉';
  return '—';
}
const chart1 = new Chart(document.getElementById('chart1'), {
  type: 'bar',
  data: { labels: allDates, datasets: [
    { label: 'A级', data: aData, backgroundColor: dark ? 'rgba(255,69,58,.82)' : 'rgba(255,59,48,.86)', borderRadius: 8, maxBarThickness: 24 },
    { label: 'B级', data: bData, backgroundColor: dark ? 'rgba(255,159,10,.82)' : 'rgba(255,149,0,.86)', borderRadius: 8, maxBarThickness: 24 },
    { label: 'C级', data: cData, backgroundColor: dark ? 'rgba(142,142,147,.34)' : 'rgba(142,142,147,.30)', borderRadius: 8, maxBarThickness: 24 },
    { label: '总信号', data: totals, type: 'line', borderColor: dark ? '#0a84ff' : '#0071e3', borderWidth: 3, pointRadius: 4, tension: .35, order: 1 }
  ]},
  options: { ...baseOptions, scales: { x: { grid: { display: false } }, y: { beginAtZero: true, grid: { color: gridColor } } } }
});
const chart2 = new Chart(document.getElementById('chart2'), {
  type: 'line',
  data: { labels: allDates, datasets: [
    { label: '平均评分', data: avgData, borderColor: dark ? '#0a84ff' : '#0071e3', backgroundColor: 'rgba(0,113,227,.10)', fill: true, tension: .35, pointRadius: 4, yAxisID: 'y' },
    { label: '平均PE(TTM)', data: peData, borderColor: '#ff3b30', tension: .35, pointRadius: 3, yAxisID: 'y1' },
    { label: '平均换手率%', data: trData, borderColor: '#30d158', tension: .35, pointRadius: 3, yAxisID: 'y1' },
    { label: '平均筹码集中度%', data: concData, borderColor: '#ff9500', tension: .35, pointRadius: 3, yAxisID: 'y1' }
  ]},
  options: { ...baseOptions, scales: {
    x: { grid: { display: false } },
    y: { position: 'left', beginAtZero: true, grid: { color: gridColor } },
    y1: { position: 'right', grid: { drawOnChartArea: false } }
  }}
});
const chart3 = new Chart(document.getElementById('chart3'), {
  type: 'bar',
  data: { labels: [], datasets: [{ label: '股票数量', data: [], backgroundColor: dark ? 'rgba(10,132,255,.72)' : 'rgba(0,113,227,.78)', borderRadius: 10, maxBarThickness: 36 }]},
  options: { ...baseOptions, scales: { x: { grid: { display: false } }, y: { beginAtZero: true, grid: { color: gridColor } } } }
});
const chart4 = new Chart(document.getElementById('chart4'), {
  type: 'line',
  data: { labels: [], datasets: [] },
  options: { ...baseOptions,
    plugins: {
      legend: {
        position: 'bottom',
        labels: { usePointStyle: true, boxWidth: 6, padding: 9, font: { size: 11 } },
        onClick(event, legendItem, legend) {
          const index = legendItem.datasetIndex;
          chart4.setDatasetVisibility(index, !chart4.isDatasetVisible(index));
          chart4.update();
          topSelectAll.checked = chart4.data.datasets.every((_, i) => chart4.isDatasetVisible(i));
        }
      },
      tooltip: { mode: 'index', intersect: false }
    },
    scales: { x: { grid: { display: false } }, y: { beginAtZero: false, grid: { color: gridColor } } }
  }
});
topSelectAll.addEventListener('change', () => {
  chart4.data.datasets.forEach((dataset, index) => {
    chart4.setDatasetVisibility(index, topSelectAll.checked);
  });
  chart4.update();
});
// 快捷区间是单选状态；手动修改日期后退出所有预设。
let activeRangePreset = 'all';
function setRangeFromLatest(days) {
  const end = allDates.length - 1;
  const start = Math.max(0, end - days + 1);
  startDateInput.value = allDates[start];
  endDateInput.value = allDates[end];
  activeRangePreset = days;
  refresh();
  updateChipActive();
}
function updateChipActive() {
  document.querySelectorAll('.chip').forEach(btn => {
    btn.classList.toggle('active', String(activeRangePreset) === btn.dataset.days);
  });
}
function buildPersistentStocks(indexes) {
  const selectedDates = indexes.map(i => allDates[i]);
  const rows = [];
  for (const stock of stocks) {
    const present = selectedDates.filter(d => stock.grades[d] !== undefined);
    const grades = present.map(d => stock.grades[d]);
    const scores = present.map(d => stock.scores[d]);
    const aCount = grades.filter(g => g === 'A').length;
    if (aCount < 2) continue;
    rows.push({
      code: stock.code,
      name: stock.name,
      grades,
      scores,
      aCount,
      days: present.length,
      latestScore: scores[scores.length - 1]
    });
  }
  rows.sort((a, b) => b.aCount - a.aCount || b.days - a.days || b.latestScore - a.latestScore);
  return rows;
}
function buildPersistentRows(indexes) {
  return buildPersistentStocks(indexes).slice(0, 20);
}
function getRangeIndexes(start, end) {
  const indexes = allDates.map((d, i) => i).filter(i => allDates[i] >= start && allDates[i] <= end);
  if (indexes.length) return { indexes, expanded: false };

  // 用户可能选择周末或节假日。这里自动匹配区间前后的最近报告，
  // 例如 09-19 ~ 09-20 会展示 09-18 和 09-21，并明确提示。
  const before = allDates.map((d, i) => d <= start ? i : -1).filter(i => i >= 0).at(-1);
  const after = allDates.map((d, i) => d >= end ? i : -1).filter(i => i >= 0)[0];
  const candidates = [...new Set([before, after].filter(i => i !== undefined && i >= 0))].sort((a, b) => a - b);
  return { indexes: candidates, expanded: true };
}
function refresh() {
  const start = startDateInput.value || allDates[0];
  const end = endDateInput.value || allDates.at(-1);
  const { indexes, expanded } = getRangeIndexes(start, end);
  if (!indexes.length) {
    rangeSummary.classList.add('notice');
    rangeSummary.textContent = '当前区间没有可用数据，请调整日期。';
    return;
  }
  const selectedDates = indexes.map(i => allDates[i]);
  const last = indexes.at(-1);
  metricTotal.textContent = totals[last];
  metricA.textContent = aData[last];
  const scoreValues = indexes.map(i => avgData[i]);
  metricScore.textContent = fmt(scoreValues.reduce((a, b) => a + b, 0) / scoreValues.length);
  chart1.data.labels = selectedDates;
  chart1.data.datasets[0].data = sliceSeries(aData, indexes);
  chart1.data.datasets[1].data = sliceSeries(bData, indexes);
  chart1.data.datasets[2].data = sliceSeries(cData, indexes);
  chart1.data.datasets[3].data = sliceSeries(totals, indexes);
  chart2.data.labels = selectedDates;
  chart2.data.datasets.forEach((ds, i) => {
    const source = [avgData, peData, trData, concData][i];
    ds.data = sliceSeries(source, indexes);
  });
  const persistence = stocks.map(stock => selectedDates.filter(d => stock.grades[d] !== undefined).length);
  const buckets = {};
  for (const n of persistence) if (n > 0) buckets[n] = (buckets[n] || 0) + 1;
  const maxDays = Math.max(...Object.keys(buckets).map(Number));
  const bucketLabels = Array.from({length: maxDays}, (_, i) => (i + 1) + '天');
  const bucketValues = Array.from({length: maxDays}, (_, i) => buckets[i + 1] || 0);
  chart3.data.labels = bucketLabels;
  chart3.data.datasets[0].data = bucketValues;
  const persistentStocks = buildPersistentStocks(indexes);
  const persistentRows = persistentStocks.slice(0, 20);
  metricPersist.textContent = persistentStocks.length;
  if (!persistentRows.length) {
    persistentTable.innerHTML = '<tr><td colspan="6" class="empty">当前区间没有连续 2 天以上 A 级的股票。</td></tr>';
  } else {
    persistentTable.innerHTML = persistentRows.map(row => {
      const grades = row.grades.join(' → ');
      const scores = row.scores.map(v => fmt(v)).join(' → ');
      const trend = row.scores.length > 1 ? arrow(row.scores[0], row.scores.at(-1)) : '—';
      return `<tr><td><strong>${row.code}</strong></td><td>${row.name}</td><td>${grades}</td><td>${scores} ${trend}</td><td>${row.aCount}天</td><td>${row.days}天</td></tr>`;
    }).join('');
  }
  const ranked = stocks.map(stock => {
    const present = selectedDates.filter(d => stock.scores[d] !== undefined);
    return { stock, present, days: present.length, max: present.length ? Math.max(...present.map(d => stock.scores[d])) : 0 };
  }).filter(x => x.days > 0).sort((a, b) => b.days - a.days || b.max - a.max).slice(0, 30);
  chart4.data.labels = selectedDates;
  chart4.data.datasets = ranked.map(item => ({
    label: item.stock.name || item.stock.code,
    data: allDates.map(d => item.stock.scores[d] ?? null),
    borderColor: 'hsl(' + hueForCode(item.stock.code) + ',68%,' + (dark ? '64%' : '45%') + ')',
    backgroundColor: 'transparent', tension: .32, pointRadius: 3, pointHoverRadius: 5, spanGaps: true,
    hidden: false
  }));
  topSelectAll.checked = true;
  rangeSummary.classList.toggle('notice', expanded);
  rangeSummary.textContent = expanded
    ? `${start} ~ ${end} 无交易日；已自动匹配最近数据：${selectedDates[0]} ~ ${selectedDates.at(-1)} · ${selectedDates.length} 个交易日`
    : `当前区间：${selectedDates[0]} ~ ${selectedDates.at(-1)} · ${selectedDates.length} 个交易日`;
  chart1.update();
  chart2.update();
  chart3.update();
  chart4.update();
}
startDateInput.min = allDates[0];
startDateInput.max = allDates.at(-1);
endDateInput.min = allDates[0];
endDateInput.max = allDates.at(-1);
startDateInput.value = allDates[0];
endDateInput.value = allDates.at(-1);
[['all', '全部'], [3, '近3日'], [5, '近5日'], [10, '近10日'], [20, '近20日']].forEach(([days, label]) => {
  const btn = document.createElement('button');
  btn.className = 'chip';
  btn.textContent = label;
  btn.dataset.days = days;
  btn.addEventListener('click', () => {
    if (days === 'all') {
      startDateInput.value = allDates[0];
      endDateInput.value = allDates.at(-1);
      activeRangePreset = 'all';
      refresh();
    } else {
      setRangeFromLatest(days);
    }
    updateChipActive();
  });
  rangeChips.appendChild(btn);
});
startDateInput.addEventListener('change', () => {
  if (startDateInput.value > endDateInput.value) endDateInput.value = startDateInput.value;
  activeRangePreset = null;
  refresh();
  updateChipActive();
});
endDateInput.addEventListener('change', () => {
  if (endDateInput.value < startDateInput.value) startDateInput.value = endDateInput.value;
  activeRangePreset = null;
  refresh();
  updateChipActive();
});
refresh();
updateChipActive();
</script>
</body>
</html>"""


def load_all():
    patterns = [
        os.path.join(ROOT, 'pipeline', 'history', 'A股底背离推荐等级排序_多因子_数据至*.csv'),
        os.path.join(OUT, 'A股底背离推荐等级排序_多因子_数据至*.csv'),
    ]
    csvs = []
    for pattern in patterns:
        csvs.extend(glob.glob(pattern))
    frames = {}
    for f in csvs:
        m = re.search(r'数据至(\d{4}-\d{2}-\d{2})\.csv', os.path.basename(f))
        if m:
            # outputs override the seed copy for the same date.
            frames[m.group(1)] = pd.read_csv(f, dtype={'代码': str})
    return frames


def build_data(frames):
    dates = sorted(frames.keys())
    daily = []
    for d in dates:
        df = frames[d]
        vc = df['多因子等级'].value_counts()
        pe = pd.to_numeric(df['PE(TTM)'], errors='coerce').replace([np.inf, -np.inf], np.nan)
        daily.append({
            'date': d,
            'total': len(df),
            'a': int(vc.get('A', 0)),
            'b': int(vc.get('B', 0)),
            'c': int(vc.get('C', 0)),
            'avg_score': round(df['多因子评分'].mean(), 1),
            'avg_pe': round(pe.dropna().clip(upper=500).mean(), 1),
            'avg_turnover': round(df['换手率%'].mean(), 2),
            'avg_chip_conc': round(df['筹码集中度%'].mean(), 1),
        })

    all_codes = set().union(*(set(frames[d]['代码']) for d in dates))
    stocks = []
    for code in all_codes:
        info = {'code': code, 'name': '', 'grades': {}, 'scores': {}}
        for d in dates:
            matched = frames[d][frames[d]['代码'] == code]
            if matched.empty:
                continue
            row = matched.iloc[0]
            info['name'] = html.escape(str(row['名称']))
            info['grades'][d] = str(row['多因子等级'])
            info['scores'][d] = float(row['多因子评分'])
        stocks.append(info)
    stocks.sort(key=lambda x: x['code'])
    return dates, daily, stocks


def gen():
    frames = load_all()
    dates, daily, stocks = build_data(frames)
    if not dates:
        raise RuntimeError('no report CSV found')
    h = TEMPLATE
    h = h.replace('__DATES__', json.dumps(dates, ensure_ascii=False))
    h = h.replace('__TOTALS__', json.dumps([d['total'] for d in daily]))
    h = h.replace('__ADATA__', json.dumps([d['a'] for d in daily]))
    h = h.replace('__BDATA__', json.dumps([d['b'] for d in daily]))
    h = h.replace('__CDATA__', json.dumps([d['c'] for d in daily]))
    h = h.replace('__AVGDATA__', json.dumps([d['avg_score'] for d in daily]))
    h = h.replace('__PEDATA__', json.dumps([d['avg_pe'] for d in daily]))
    h = h.replace('__TRDATA__', json.dumps([d['avg_turnover'] for d in daily]))
    h = h.replace('__CONCDATA__', json.dumps([d['avg_chip_conc'] for d in daily]))
    h = h.replace('__STOCKS__', json.dumps(stocks, ensure_ascii=False))
    PathOutSite = os.path.join(SITE, 'trends.html')
    PathOutOut = os.path.join(OUT, 'A股底背离聚合量化分析.html')
    for path in (PathOutSite, PathOutOut):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(h)
    print(f'[trends] OK interactive range, {len(stocks)} stocks, {len(dates)} days')


if __name__ == '__main__':
    gen()
