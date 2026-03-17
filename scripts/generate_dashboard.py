"""
生成 ATH Monitor 可视化 HTML 页面 v2
包含：
1. 今日历史新高股票模块（行业分组、行业得分、近5日突破次数）
2. 每日突破历史新高股票数量折线图
3. 行业热力图（优化色阶 + 近5/10/20日短周期）
"""
import sqlite3
import pandas as pd
import json
import os
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "data", "ath_monitor.db")
OUTPUT_PATH = os.path.join(BASE_DIR, "docs", "index.html")

conn = sqlite3.connect(DB_PATH)

# ============ 数据准备 ============

# 1. 行业总股票数
df_latest = pd.read_sql('SELECT ts_code, name, industry FROM ath_latest', conn)
ind_total = df_latest.groupby('industry')['ts_code'].count().reset_index()
ind_total.columns = ['industry', 'total_stocks']
ind_total_dict = dict(zip(ind_total['industry'], ind_total['total_stocks']))

# 2. 每日突破记录（含股票名称）
df_all = pd.read_sql('''
    SELECT s.trade_date, s.ts_code, s.industry, s.close, s.pct_chg,
           l.name
    FROM daily_ath_summary s
    LEFT JOIN ath_latest l ON s.ts_code = l.ts_code
    WHERE s.trade_date >= '20150101'
    ORDER BY s.trade_date
''', conn)
conn.close()

df_all['industry'] = df_all['industry'].fillna('未知')
df_all['name'] = df_all['name'].fillna(df_all['ts_code'])

# 3. 每日突破总数（折线图数据）
daily_count = df_all.groupby('trade_date')['ts_code'].count().reset_index()
daily_count.columns = ['trade_date', 'count']
daily_count['date_fmt'] = pd.to_datetime(daily_count['trade_date'], format='%Y%m%d').dt.strftime('%Y-%m-%d')

line_dates = daily_count['date_fmt'].tolist()
line_counts = daily_count['count'].tolist()
line_raw_dates = daily_count['trade_date'].tolist()

# 4. 行业热力图数据
daily_ind = df_all.groupby(['trade_date', 'industry'])['ts_code'].count().reset_index()
daily_ind.columns = ['trade_date', 'industry', 'breakout_count']
daily_ind['total_stocks'] = daily_ind['industry'].map(ind_total_dict).fillna(1).astype(int)
daily_ind['score'] = (daily_ind['breakout_count'] ** 2) / daily_ind['total_stocks']
daily_ind['score'] = daily_ind['score'].round(4)

all_industries = ind_total.sort_values('total_stocks', ascending=False)['industry'].tolist()

# 取最近 500 个交易日用于热力图
recent_dates = sorted(df_all['trade_date'].unique())[-500:]
daily_ind_recent = daily_ind[daily_ind['trade_date'].isin(recent_dates)].copy()

pivot = daily_ind_recent.pivot(index='industry', columns='trade_date', values='score').fillna(0)
pivot = pivot.reindex([i for i in all_industries if i in pivot.index])

heatmap_dates = sorted(recent_dates)
heatmap_dates_fmt = [pd.Timestamp(d).strftime('%Y-%m-%d') for d in heatmap_dates]
heatmap_industries = pivot.index.tolist()
heatmap_matrix = pivot.values.tolist()

# 5. 点击详情数据
detail_map = {}
for (date, ind), grp in df_all[df_all['trade_date'].isin(recent_dates)].groupby(['trade_date', 'industry']):
    key = f"{date}|{ind}"
    stocks = []
    for _, row in grp.iterrows():
        stocks.append({
            'ts_code': row['ts_code'],
            'name': str(row['name']),
            'close': round(float(row['close']), 2) if pd.notna(row['close']) else 0,
            'pct_chg': round(float(row['pct_chg']), 2) if pd.notna(row['pct_chg']) else 0,
        })
    detail_map[key] = stocks

# 6. 今日新高模块数据
latest_date = sorted(df_all['trade_date'].unique())[-1]
latest_date_fmt = pd.Timestamp(latest_date).strftime('%Y-%m-%d')

# 近5日日期
dates_5d = sorted(df_all['trade_date'].unique())[-5:]

df_today = df_all[df_all['trade_date'] == latest_date].copy()

# 今日每行业突破数 & 得分
today_ind_cnt = df_today.groupby('industry')['ts_code'].count().reset_index()
today_ind_cnt.columns = ['industry', 'today_breakout']
today_ind_cnt['total_stocks'] = today_ind_cnt['industry'].map(ind_total_dict).fillna(1).astype(int)
today_ind_cnt['score'] = (today_ind_cnt['today_breakout'] ** 2) / today_ind_cnt['total_stocks']
today_ind_cnt['score'] = today_ind_cnt['score'].round(4)
today_ind_score = dict(zip(today_ind_cnt['industry'], today_ind_cnt['score']))

# 每只今日股票近5日突破次数
df_5d = df_all[df_all['trade_date'].isin(dates_5d)]
cnt_5d = df_5d.groupby('ts_code')['trade_date'].count().reset_index()
cnt_5d.columns = ['ts_code', 'cnt_5d']
cnt_5d_dict = dict(zip(cnt_5d['ts_code'], cnt_5d['cnt_5d']))

# 构建今日股票列表，按行业得分 desc, 涨跌幅 desc 排序
today_stocks = []
for _, row in df_today.sort_values(['industry', 'pct_chg'], ascending=[True, False]).iterrows():
    ind = row['industry']
    today_stocks.append({
        'ts_code': row['ts_code'],
        'name': str(row['name']),
        'industry': ind,
        'ind_score': today_ind_score.get(ind, 0),
        'ind_total': ind_total_dict.get(ind, 1),
        'close': round(float(row['close']), 2) if pd.notna(row['close']) else 0,
        'pct_chg': round(float(row['pct_chg']), 2) if pd.notna(row['pct_chg']) else 0,
        'cnt_5d': int(cnt_5d_dict.get(row['ts_code'], 1)),
    })
# 按行业得分降序
today_stocks.sort(key=lambda x: (-x['ind_score'], -x['pct_chg']))

print(f"折线图数据点: {len(line_dates)}")
print(f"热力图行业数: {len(heatmap_industries)}, 日期数: {len(heatmap_dates)}")
print(f"详情条目数: {len(detail_map)}")
print(f"今日({latest_date_fmt})突破股票: {len(today_stocks)}")

# ============ 生成 HTML ============

HTML = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ATH Monitor — 历史新高监控仪表板</title>
<script src="echarts.min.js"></script>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  background: #0d1117;
  color: #e6edf3;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', sans-serif;
  min-height: 100vh;
}
.header {
  padding: 20px 32px 16px;
  border-bottom: 1px solid #21262d;
  display: flex;
  align-items: center;
  gap: 12px;
}
.header h1 { font-size: 20px; font-weight: 600; color: #f0f6fc; }
.header .subtitle { font-size: 13px; color: #8b949e; margin-left: auto; }
.badge {
  background: #1f6feb22; border: 1px solid #1f6feb55;
  color: #58a6ff; padding: 2px 10px; border-radius: 12px; font-size: 12px;
}
.container { padding: 20px 32px; max-width: 1800px; margin: 0 auto; }
.card {
  background: #161b22; border: 1px solid #21262d;
  border-radius: 12px; padding: 18px 22px; margin-bottom: 20px;
}
.card-title {
  font-size: 15px; font-weight: 600; color: #f0f6fc;
  margin-bottom: 4px; display: flex; align-items: center; gap: 8px;
}
.card-desc { font-size: 12px; color: #8b949e; margin-bottom: 14px; }

/* ===== 今日新高模块 ===== */
.today-summary {
  display: flex; gap: 16px; margin-bottom: 16px; flex-wrap: wrap;
}
.today-stat {
  background: #0d1117; border: 1px solid #21262d; border-radius: 8px;
  padding: 12px 18px; min-width: 120px;
}
.today-stat .val { font-size: 26px; font-weight: 700; color: #f85149; }
.today-stat .lbl { font-size: 11px; color: #8b949e; margin-top: 2px; }

/* 行业分组卡片 */
.ind-group-list { display: flex; flex-direction: column; gap: 10px; }
.ind-group {
  background: #0d1117; border: 1px solid #21262d; border-radius: 8px;
  overflow: hidden;
}
.ind-group-header {
  display: flex; align-items: center; gap: 10px;
  padding: 10px 14px; cursor: pointer;
  transition: background 0.15s;
}
.ind-group-header:hover { background: #1c2128; }
.ind-name { font-size: 14px; font-weight: 600; color: #f0f6fc; }
.ind-meta { font-size: 12px; color: #8b949e; }
.ind-score-pill {
  margin-left: auto; padding: 3px 10px; border-radius: 10px;
  font-size: 12px; font-weight: 700;
}
.ind-score-high { background:#f8514922; border:1px solid #f85149aa; color:#f85149; }
.ind-score-mid  { background:#d2992222; border:1px solid #d29922aa; color:#d29922; }
.ind-score-low  { background:#1f6feb22; border:1px solid #1f6feb55; color:#58a6ff; }
.chevron { font-size: 11px; color: #8b949e; transition: transform 0.2s; }
.chevron.open { transform: rotate(90deg); }
.ind-stocks { display: none; padding: 0 14px 10px; }
.ind-stocks.open { display: block; }
.stock-row {
  display: flex; align-items: center; gap: 8px;
  padding: 7px 0; border-top: 1px solid #21262d;
  font-size: 13px;
}
.stock-name { font-weight: 500; color: #e6edf3; min-width: 72px; }
.stock-code { font-size: 11px; color: #8b949e; min-width: 90px; }
.stock-price { color: #8b949e; min-width: 60px; }
.stock-pct { font-weight: 600; min-width: 60px; }
.stock-5d {
  margin-left: auto; font-size: 11px; color: #8b949e;
  display: flex; align-items: center; gap: 4px;
}
.dots5 { display: flex; gap: 3px; }
.dot { width: 8px; height: 8px; border-radius: 50%; }
.dot-hit { background: #f85149; }
.dot-miss { background: #30363d; }
.up { color: #f85149; }
.down { color: #3fb950; }

/* ===== 折线图 ===== */
#lineChart { width: 100%; height: 320px; }

/* ===== 热力图控制 ===== */
.heatmap-controls {
  display: flex; align-items: center; gap: 8px; margin-bottom: 12px; flex-wrap: wrap;
}
.ctrl-group { display: flex; gap: 4px; }
.range-btn {
  padding: 4px 12px; border-radius: 6px; border: 1px solid #30363d;
  background: #21262d; color: #8b949e; font-size: 12px; cursor: pointer;
  transition: all 0.15s;
}
.range-btn:hover { background: #1c2128; color: #e6edf3; }
.range-btn.active { background: #1f6feb22; border-color: #1f6feb; color: #58a6ff; }
.ctrl-divider { width: 1px; background: #30363d; margin: 0 4px; }
#heatmapChart { width: 100%; height: 700px; }
.legend-row {
  display: flex; align-items: center; gap: 16px; margin-top: 8px;
  font-size: 12px; color: #8b949e; flex-wrap: wrap;
}
.legend-item { display: flex; align-items: center; gap: 6px; }
.legend-dot { width: 12px; height: 12px; border-radius: 2px; }

/* ===== 弹窗 ===== */
.modal-overlay {
  display: none; position: fixed; inset: 0;
  background: rgba(0,0,0,0.65); z-index: 1000;
  justify-content: center; align-items: flex-start; padding-top: 80px;
}
.modal-overlay.show { display: flex; }
.modal {
  background: #161b22; border: 1px solid #30363d; border-radius: 12px;
  padding: 22px; width: 560px; max-width: 90vw; max-height: 70vh;
  overflow-y: auto; position: relative;
}
.modal-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px; }
.modal-title { font-size: 15px; font-weight: 600; color: #f0f6fc; }
.modal-close {
  background: none; border: none; color: #8b949e; font-size: 18px;
  cursor: pointer; padding: 4px 8px; border-radius: 4px;
}
.modal-close:hover { background: #21262d; color: #f0f6fc; }
.stk-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.stk-table th {
  text-align: left; padding: 7px 10px; border-bottom: 1px solid #21262d;
  color: #8b949e; font-weight: 500;
}
.stk-table td { padding: 7px 10px; border-bottom: 1px solid #0d1117; }
.stk-table tr:hover td { background: #1c2128; }
</style>
</head>
<body>

<div class="header">
  <div class="badge">ATH</div>
  <h1>历史新高监控仪表板</h1>
  <div class="subtitle">数据截至 __LATEST_DATE__ &nbsp;·&nbsp; 共 __TOTAL__ 条突破记录</div>
</div>

<div class="container">

<!-- ===== 今日新高模块 ===== -->
<div class="card">
  <div class="card-title">⚡ 今日突破历史新高</div>
  <div class="card-desc">__LATEST_DATE__ 创历史新高的股票，按行业突破强度得分降序排列，点击行业可展开股票列表</div>
  <div class="today-summary" id="todaySummary"></div>
  <div class="ind-group-list" id="indGroupList"></div>
</div>

<!-- ===== 折线图 ===== -->
<div class="card">
  <div class="card-title">📈 每日突破历史新高股票数量</div>
  <div class="card-desc">收盘价突破历史所有交易日最高价的股票数量，反映市场整体强度</div>
  <div id="lineChart"></div>
</div>

<!-- ===== 行业热力图 ===== -->
<div class="card">
  <div class="card-title">
    🔥 行业突破强度热力图
    <span style="font-size:12px;font-weight:400;color:#8b949e">（得分 = 突破数² / 行业总股数，点击格子查看突破股票）</span>
  </div>
  <div class="card-desc">得分越高说明行业内突破股票比例越集中，橙/红色边框 = 得分 > 1</div>
  <div class="heatmap-controls">
    <span style="font-size:12px;color:#8b949e">显示范围：</span>
    <div class="ctrl-group">
      <button class="range-btn" onclick="setRange(5)">近5日</button>
      <button class="range-btn" onclick="setRange(10)">近10日</button>
      <button class="range-btn" onclick="setRange(20)">近20日</button>
    </div>
    <div class="ctrl-divider"></div>
    <div class="ctrl-group">
      <button class="range-btn" onclick="setRange(60)">近60日</button>
      <button class="range-btn active" onclick="setRange(120)">近120日</button>
      <button class="range-btn" onclick="setRange(250)">近250日</button>
      <button class="range-btn" onclick="setRange(500)">近500日</button>
    </div>
    <div class="legend-row">
      <div class="legend-item"><div class="legend-dot" style="background:#f85149"></div>极强(>3)</div>
      <div class="legend-item"><div class="legend-dot" style="background:#e09921"></div>强(1~3)</div>
      <div class="legend-item"><div class="legend-dot" style="background:#3b82f6"></div>中(0.3~1)</div>
      <div class="legend-item"><div class="legend-dot" style="background:#1d4572"></div>弱(0.1~0.3)</div>
      <div class="legend-item"><div class="legend-dot" style="background:#0d1117;border:1px solid #30363d"></div>无</div>
    </div>
  </div>
  <div id="heatmapChart"></div>
</div>

</div><!-- /container -->

<!-- 弹窗 -->
<div class="modal-overlay" id="modalOverlay" onclick="closeModal(event)">
  <div class="modal" id="modal">
    <div class="modal-header">
      <div class="modal-title" id="modalTitle"></div>
      <button class="modal-close" onclick="hideModal()">✕</button>
    </div>
    <div id="modalBody"></div>
  </div>
</div>

<script>
// ===== 数据注入 =====
const LINE_DATES   = __LINE_DATES__;
const LINE_COUNTS  = __LINE_COUNTS__;
const ALL_INDUSTRIES = __ALL_INDUSTRIES__;
const HEATMAP_DATES     = __HEATMAP_DATES__;
const HEATMAP_DATES_FMT = __HEATMAP_DATES_FMT__;
const HEATMAP_MATRIX    = __HEATMAP_MATRIX__;
const DETAIL_MAP   = __DETAIL_MAP__;
const TODAY_STOCKS = __TODAY_STOCKS__;
const LATEST_DATE  = '__LATEST_DATE_RAW__';

// ===== 今日新高模块 =====
(function renderToday() {
  // 统计数据
  const total = TODAY_STOCKS.length;
  const inds = [...new Set(TODAY_STOCKS.map(s => s.industry))];
  const maxScore = TODAY_STOCKS.reduce((m, s) => Math.max(m, s.ind_score), 0);
  const hotInd = total > 0 ? inds.reduce((best, ind) => {
    const s = TODAY_STOCKS.find(x => x.industry === ind)?.ind_score || 0;
    const bs = TODAY_STOCKS.find(x => x.industry === best)?.ind_score || 0;
    return s > bs ? ind : best;
  }, inds[0]) : '-';

  document.getElementById('todaySummary').innerHTML = `
    <div class="today-stat"><div class="val">${total}</div><div class="lbl">突破股票数</div></div>
    <div class="today-stat"><div class="val">${inds.length}</div><div class="lbl">涉及行业数</div></div>
    <div class="today-stat"><div class="val" style="color:#d29922">${maxScore.toFixed(2)}</div><div class="lbl">最高行业得分</div></div>
    <div class="today-stat"><div class="val" style="font-size:18px;color:#e6edf3">${hotInd || '-'}</div><div class="lbl">最强行业</div></div>
  `;

  if (total === 0) {
    document.getElementById('indGroupList').innerHTML =
      '<div style="color:#8b949e;font-size:13px;padding:12px 0">今日无突破历史新高股票</div>';
    return;
  }

  // 按行业分组
  const groups = {};
  TODAY_STOCKS.forEach(s => {
    if (!groups[s.industry]) groups[s.industry] = { score: s.ind_score, total: s.ind_total, stocks: [] };
    groups[s.industry].stocks.push(s);
  });

  const sorted = Object.entries(groups).sort((a, b) => b[1].score - a[1].score);
  const container = document.getElementById('indGroupList');
  container.innerHTML = '';

  sorted.forEach(([ind, info], gi) => {
    const sc = info.score;
    const pillCls = sc > 3 ? 'ind-score-high' : sc > 1 ? 'ind-score-mid' : 'ind-score-low';
    const div = document.createElement('div');
    div.className = 'ind-group';
    div.innerHTML = `
      <div class="ind-group-header" onclick="toggleGroup(${gi})">
        <span class="ind-name">${ind}</span>
        <span class="ind-meta">${info.stocks.length}只 / 共${info.total}只</span>
        <span class="ind-score-pill ${pillCls}">得分 ${sc.toFixed(3)}</span>
        <span class="chevron" id="chev-${gi}">▶</span>
      </div>
      <div class="ind-stocks" id="stocks-${gi}">
        ${info.stocks.map(s => {
          const dots = Array.from({length: 5}, (_, i) =>
            `<div class="dot ${i < s.cnt_5d ? 'dot-hit' : 'dot-miss'}"></div>`
          ).join('');
          return `
          <div class="stock-row">
            <span class="stock-name">${s.name}</span>
            <span class="stock-code">${s.ts_code}</span>
            <span class="stock-price">¥${s.close}</span>
            <span class="stock-pct ${s.pct_chg >= 0 ? 'up' : 'down'}">${s.pct_chg >= 0 ? '+' : ''}${s.pct_chg}%</span>
            <div class="stock-5d">
              <span>近5日</span>
              <div class="dots5">${dots}</div>
              <span style="color:${s.cnt_5d >= 3 ? '#f85149' : '#8b949e'}">${s.cnt_5d}次</span>
            </div>
          </div>`;
        }).join('')}
      </div>
    `;
    container.appendChild(div);
    // 得分>1 默认展开
    if (sc > 1) toggleGroup(gi);
  });
})();

function toggleGroup(gi) {
  const el = document.getElementById(`stocks-${gi}`);
  const ch = document.getElementById(`chev-${gi}`);
  el.classList.toggle('open');
  ch.classList.toggle('open');
}

// ===== 折线图 =====
const lineChart = echarts.init(document.getElementById('lineChart'));
lineChart.setOption({
  backgroundColor: 'transparent',
  tooltip: {
    trigger: 'axis',
    backgroundColor: '#1c2128', borderColor: '#30363d',
    textStyle: { color: '#e6edf3', fontSize: 13 },
    formatter: p => `<b>${p[0].axisValue}</b><br/>突破数量：<span style="color:#58a6ff;font-weight:600">${p[0].value}</span> 只`
  },
  toolbox: {
    right: 16,
    feature: {
      dataZoom: { yAxisIndex: 'none', title: { zoom: '区域缩放', back: '还原' } },
      restore: { title: '还原' },
      saveAsImage: { title: '保存图片' }
    },
    iconStyle: { borderColor: '#58a6ff' }
  },
  dataZoom: [
    { type: 'inside', start: 80, end: 100 },
    {
      type: 'slider', start: 80, end: 100, height: 22, bottom: 6,
      backgroundColor: '#161b22',
      dataBackground: { lineStyle: { color: '#1f6feb55' }, areaStyle: { color: '#1f6feb22' } },
      fillerColor: '#1f6feb33', borderColor: '#30363d',
      textStyle: { color: '#8b949e', fontSize: 11 }
    }
  ],
  grid: { top: 12, left: 56, right: 32, bottom: 48 },
  xAxis: {
    type: 'category', data: LINE_DATES,
    axisLine: { lineStyle: { color: '#30363d' } },
    axisLabel: { color: '#8b949e', fontSize: 11 }, splitLine: { show: false }
  },
  yAxis: {
    type: 'value', name: '突破数量（只）',
    nameTextStyle: { color: '#8b949e', fontSize: 11 },
    axisLine: { show: false }, axisLabel: { color: '#8b949e', fontSize: 11 },
    splitLine: { lineStyle: { color: '#21262d', type: 'dashed' } }
  },
  series: [{
    type: 'line', data: LINE_COUNTS, smooth: 0.3, symbol: 'none',
    lineStyle: { color: '#58a6ff', width: 1.5 },
    areaStyle: {
      color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
        colorStops: [{ offset: 0, color: '#1f6feb44' }, { offset: 1, color: '#1f6feb05' }] }
    },
    markPoint: {
      data: [{ type: 'max', name: '最大值' }],
      label: { color: '#f0f6fc', fontSize: 11 },
      itemStyle: { color: '#f85149' }
    }
  }]
});

// ===== 热力图 =====
let currentRange = 120;
const heatChart = echarts.init(document.getElementById('heatmapChart'));

function getVisibleRange(range) {
  const total = HEATMAP_DATES.length;
  const start = Math.max(0, total - range);
  return {
    dates:    HEATMAP_DATES.slice(start),
    datesFmt: HEATMAP_DATES_FMT.slice(start),
    matrix:   HEATMAP_MATRIX.map(row => row.slice(start))
  };
}

// 对数映射：让低分段颜色差异更明显
// 原始分数 -> 颜色映射值（log scale）
function logScale(score) {
  if (score <= 0) return 0;
  // log(1 + score*5) / log(1 + 5*maxScore)  → 归一化到 [0,1]
  // 直接返回 log(1 + score) 让echarts visualMap用 log 空间
  return Math.log1p(score * 4);
}

function buildHeatmapData(dates, matrix) {
  const data = [];
  for (let r = 0; r < ALL_INDUSTRIES.length; r++) {
    for (let c = 0; c < dates.length; c++) {
      const raw = matrix[r] ? (matrix[r][c] || 0) : 0;
      const val = logScale(raw);
      if (raw > 1) {
        data.push({
          value: [c, r, val],
          _raw: raw,
          itemStyle: {
            borderColor: raw > 3 ? '#f85149cc' : '#d29922cc',
            borderWidth: 1.5
          }
        });
      } else {
        data.push({ value: [c, r, val], _raw: raw });
      }
    }
  }
  return data;
}

function renderHeatmap() {
  const { dates, datesFmt, matrix } = getVisibleRange(currentRange);
  const heatData = buildHeatmapData(dates, matrix);
  const logMax = Math.log1p(10 * 4); // 对应原始分数约10的映射上限

  // x轴标签间隔
  const labelInterval = dates.length <= 10 ? 0
    : dates.length <= 25 ? 1
    : Math.floor(dates.length / 20);

  const option = {
    backgroundColor: 'transparent',
    tooltip: {
      position: 'top',
      backgroundColor: '#1c2128', borderColor: '#30363d',
      textStyle: { color: '#e6edf3', fontSize: 12 },
      formatter: params => {
        const raw = params.data;
        const arr = Array.isArray(raw) ? raw.value : raw.value;
        const [colIdx, rowIdx] = arr;
        const score = raw._raw !== undefined ? raw._raw : 0;
        const ind = ALL_INDUSTRIES[rowIdx];
        const dateFmt = datesFmt[colIdx];
        const rawDate = dates[colIdx];
        const key = rawDate + '|' + ind;
        const stocks = DETAIL_MAP[key] || [];
        let tip = `<b>${dateFmt}</b> &nbsp; ${ind}<br/>`;
        tip += `突破股票：<b>${stocks.length}</b> 只`;
        if (score > 0) tip += `&nbsp;·&nbsp; 强度得分：<b style="color:${score>3?'#f85149':score>1?'#d29922':'#58a6ff'}">${score.toFixed(3)}</b>`;
        if (stocks.length > 0) tip += `<br/><span style="color:#8b949e;font-size:11px">点击查看详情</span>`;
        return tip;
      }
    },
    grid: { top: 8, left: 90, right: 20, bottom: 50 },
    xAxis: {
      type: 'category', data: datesFmt, splitArea: { show: false },
      axisLabel: { color: '#8b949e', fontSize: 9, rotate: 45, interval: labelInterval },
      axisLine: { lineStyle: { color: '#30363d' } }
    },
    yAxis: {
      type: 'category', data: ALL_INDUSTRIES, splitArea: { show: false },
      axisLabel: { color: '#c9d1d9', fontSize: 11 },
      axisLine: { lineStyle: { color: '#30363d' } }
    },
    visualMap: {
      min: 0, max: logMax,
      calculable: false,
      show: false,  // 隐藏默认visualMap，用自定义图例
      inRange: {
        // 5段对数色阶：黑 → 深蓝 → 蓝 → 橙 → 红
        color: [
          '#0d1117',  // 0    无
          '#0d2137',  // 极低
          '#0f3460',  // 低
          '#1a5276',  // 低中
          '#1d6fa4',  // 中低
          '#2e86c1',  // 中
          '#3b9dd2',  // 中高
          '#d4ac0d',  // 高（黄）
          '#e67e22',  // 高（橙）
          '#e74c3c',  // 极高（红橙）
          '#c0392b',  // 极强（深红）
        ]
      }
    },
    series: [{
      name: '行业突破强度',
      type: 'heatmap',
      data: heatData,
      label: { show: false },
      itemStyle: { borderColor: 'transparent', borderWidth: 0 },
      emphasis: {
        itemStyle: {
          shadowBlur: 8, shadowColor: '#58a6ff66',
          borderColor: '#58a6ff', borderWidth: 2
        }
      }
    }]
  };

  heatChart.setOption(option, true);
}

renderHeatmap();

// 热力图点击
heatChart.on('click', params => {
  if (params.componentType !== 'series') return;
  const raw = params.data;
  const arr = raw.value;
  const [colIdx, rowIdx] = arr;
  const score = raw._raw !== undefined ? raw._raw : 0;
  const { dates, datesFmt } = getVisibleRange(currentRange);
  const ind = ALL_INDUSTRIES[rowIdx];
  const dateFmt = datesFmt[colIdx];
  const rawDate = dates[colIdx];
  const key = rawDate + '|' + ind;
  const stocks = DETAIL_MAP[key] || [];
  if (stocks.length === 0) return;
  showModal(dateFmt, ind, score, stocks);
});

// ===== 弹窗 =====
function showModal(date, industry, score, stocks) {
  const pillCls = score > 3 ? 'ind-score-high' : score > 1 ? 'ind-score-mid' : 'ind-score-low';
  document.getElementById('modalTitle').innerHTML =
    `${date} &nbsp;·&nbsp; ${industry} &nbsp;<span class="ind-score-pill ${pillCls}">得分 ${score.toFixed(3)}</span>`;
  const rows = stocks.map(s => `
    <tr>
      <td>${s.name}</td>
      <td style="color:#8b949e;font-size:11px">${s.ts_code}</td>
      <td>¥${s.close}</td>
      <td class="${s.pct_chg >= 0 ? 'up' : 'down'}">${s.pct_chg >= 0 ? '+' : ''}${s.pct_chg}%</td>
    </tr>`).join('');
  document.getElementById('modalBody').innerHTML = `
    <table class="stk-table">
      <thead><tr><th>名称</th><th>代码</th><th>收盘价</th><th>涨跌幅</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>
    <div style="text-align:center;color:#8b949e;font-size:12px;margin-top:10px">共 ${stocks.length} 只股票突破历史新高</div>
  `;
  document.getElementById('modalOverlay').classList.add('show');
}
function hideModal() { document.getElementById('modalOverlay').classList.remove('show'); }
function closeModal(e) { if (e.target === document.getElementById('modalOverlay')) hideModal(); }

// ===== 范围按钮高亮修复 =====
function setRange(n) {
  currentRange = n;
  document.querySelectorAll('.range-btn').forEach(btn => {
    const txt = btn.textContent.trim();
    btn.classList.toggle('active', txt === `近${n}日` || txt === `近${n}日`);
  });
  renderHeatmap();
}

// ===== 响应式 =====
window.addEventListener('resize', () => { lineChart.resize(); heatChart.resize(); });
</script>
</body>
</html>'''

# ===== 数据注入 =====
html = HTML
html = html.replace('__LINE_DATES__',       json.dumps(line_dates,         ensure_ascii=False))
html = html.replace('__LINE_COUNTS__',      json.dumps(line_counts))
html = html.replace('__ALL_INDUSTRIES__',   json.dumps(heatmap_industries, ensure_ascii=False))
html = html.replace('__HEATMAP_DATES__',    json.dumps(heatmap_dates,      ensure_ascii=False))
html = html.replace('__HEATMAP_DATES_FMT__',json.dumps(heatmap_dates_fmt,  ensure_ascii=False))
html = html.replace('__HEATMAP_MATRIX__',   json.dumps(heatmap_matrix))
html = html.replace('__DETAIL_MAP__',       json.dumps(detail_map,         ensure_ascii=False))
html = html.replace('__TODAY_STOCKS__',     json.dumps(today_stocks,       ensure_ascii=False))
html = html.replace('__LATEST_DATE__',      latest_date_fmt)
html = html.replace('__LATEST_DATE_RAW__',  latest_date_fmt)
html = html.replace('__TOTAL__',            str(len(df_all)))

with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
    f.write(html)

print(f"\nHTML 已生成：{OUTPUT_PATH}")
print(f"文件大小：{os.path.getsize(OUTPUT_PATH) / 1024:.1f} KB")
