"""
生成 ATH Monitor 可视化 HTML 页面 v3
包含：
1. 今日历史新高股票模块（行业分组、行业得分、近5日突破次数）
2. 每日突破历史新高股票数量折线图
3. 行业热力图（筛选过滤 + 优化颜色 + 同花顺链接）
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

# 【新功能1】过滤掉周期内没有1天得分>1的行业（基于120日默认范围）
def filter_industries(pivot_df, threshold=1.0):
    """过滤：在默认范围内(120日)没有任何一天得分超过threshold的行业"""
    default_range = 120
    total = pivot_df.shape[1]
    start = max(0, total - default_range)
    visible_data = pivot_df.iloc[:, start:]
    max_scores = visible_data.max(axis=1)
    return max_scores[max_scores > threshold].index.tolist()

# 获取默认120日内有得分>1的行业
active_industries = filter_industries(pivot, threshold=1.0)
print(f"过滤前行业数: {len(pivot.index)}, 过滤后(120日内有得分>1): {len(active_industries)}")

# 保留所有行业用于筛选，但默认显示活跃的
heatmap_dates = sorted(recent_dates)
heatmap_dates_fmt = [pd.Timestamp(d).strftime('%Y-%m-%d') for d in heatmap_dates]
heatmap_industries = pivot.index.tolist()  # 保留所有行业
heatmap_matrix = pivot.values.tolist()

# 同时保存活跃行业索引，用于前端筛选
active_industry_indices = [heatmap_industries.index(ind) for ind in active_industries if ind in heatmap_industries]

# 5. 点击详情数据 - 增加同花顺链接所需信息
detail_map = {}
for (date, ind), grp in df_all[df_all['trade_date'].isin(recent_dates)].groupby(['trade_date', 'industry']):
    key = f"{date}|{ind}"
    stocks = []
    for _, row in grp.iterrows():
        ts_code = str(row['ts_code'])
        # 生成同花顺链接
        if ts_code.endswith('.SZ'):
            jqka_code = ts_code.replace('.SZ', '')
        elif ts_code.endswith('.SH'):
            jqka_code = ts_code.replace('.SH', '')
        else:
            jqka_code = ts_code
        jqka_link = f"https://stockpage.10jqka.com.cn/{jqka_code}/"

        stocks.append({
            'ts_code': ts_code,
            'name': str(row['name']),
            'close': round(float(row['close']), 2) if pd.notna(row['close']) else 0,
            'pct_chg': round(float(row['pct_chg']), 2) if pd.notna(row['pct_chg']) else 0,
            'jqka_link': jqka_link
        })
    detail_map[key] = stocks

# 6. 今日新高模块数据
latest_date = sorted(df_all['trade_date'].unique())[-1]
latest_date_fmt = pd.Timestamp(latest_date).strftime('%Y-%m-%d')

dates_5d = sorted(df_all['trade_date'].unique())[-5:]

df_today = df_all[df_all['trade_date'] == latest_date].copy()

today_ind_cnt = df_today.groupby('industry')['ts_code'].count().reset_index()
today_ind_cnt.columns = ['industry', 'today_breakout']
today_ind_cnt['total_stocks'] = today_ind_cnt['industry'].map(ind_total_dict).fillna(1).astype(int)
today_ind_cnt['score'] = (today_ind_cnt['today_breakout'] ** 2) / today_ind_cnt['total_stocks']
today_ind_cnt['score'] = today_ind_cnt['score'].round(4)
today_ind_score = dict(zip(today_ind_cnt['industry'], today_ind_cnt['score']))

df_5d = df_all[df_all['trade_date'].isin(dates_5d)]
cnt_5d = df_5d.groupby('ts_code')['trade_date'].count().reset_index()
cnt_5d.columns = ['ts_code', 'cnt_5d']
cnt_5d_dict = dict(zip(cnt_5d['ts_code'], cnt_5d['cnt_5d']))

# 构建今日股票列表 - 增加同花顺链接
today_stocks = []
for _, row in df_today.sort_values(['industry', 'pct_chg'], ascending=[True, False]).iterrows():
    ind = row['industry']
    ts_code = str(row['ts_code'])
    if ts_code.endswith('.SZ'):
        jqka_code = ts_code.replace('.SZ', '')
    elif ts_code.endswith('.SH'):
        jqka_code = ts_code.replace('.SH', '')
    else:
        jqka_code = ts_code
    jqka_link = f"https://stockpage.10jqka.com.cn/{jqka_code}/"

    today_stocks.append({
        'ts_code': ts_code,
        'name': str(row['name']),
        'industry': ind,
        'ind_score': today_ind_score.get(ind, 0),
        'ind_total': ind_total_dict.get(ind, 1),
        'close': round(float(row['close']), 2) if pd.notna(row['close']) else 0,
        'pct_chg': round(float(row['pct_chg']), 2) if pd.notna(row['pct_chg']) else 0,
        'cnt_5d': int(cnt_5d_dict.get(row['ts_code'], 1)),
        'jqka_link': jqka_link
    })
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
.stock-code a { color: #58a6ff; text-decoration: none; }
.stock-code a:hover { text-decoration: underline; }
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
/* 【新功能3】热力图高度拉高 */
#heatmapChart { width: 100%; height: 1000px; }
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
.stk-table .ts-code a { color: #58a6ff; text-decoration: none; }
.stk-table .ts-code a:hover { text-decoration: underline; }
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
    <div class="ctrl-divider"></div>
    <!-- 【新功能1】添加筛选按钮 -->
    <label style="display:flex;align-items:center;gap:6px;cursor:pointer;font-size:12px;color:#8b949e;">
      <input type="checkbox" id="filterActive" checked onchange="renderHeatmap()">
      仅显示120日内有得分>1的行业
    </label>
    <div class="legend-row">
      <div class="legend-item"><div class="legend-dot" style="background:#f85149"></div>强(>2)</div>
      <div class="legend-item"><div class="legend-dot" style="background:#e67e22"></div>中强(1~2)</div>
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
const ACTIVE_INDUSTRIES = __ACTIVE_INDUSTRIES__;

// ===== 今日新高模块 =====
(function renderToday() {
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
          // 【新功能2】股票代码添加同花顺链接
          return `
          <div class="stock-row">
            <span class="stock-name">${s.name}</span>
            <span class="stock-code"><a href="${s.jqka_link}" target="_blank">${s.ts_code}</a></span>
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

// 【新功能4】优化颜色映射，让1-2分更醒目
function logScale(score) {
  if (score <= 0) return 0;
  // 使用更激进的映射，让低分更明显
  // score 0.3 -> 约1.2, score 1 -> 约2, score 2 -> 约3
  return Math.log1p(score * 3);
}

function buildHeatmapData(dates, matrix, industries, filterEnabled) {
  const data = [];
  // 如果启用筛选，只显示活跃行业
  const visibleIndustries = filterEnabled ? ACTIVE_INDUSTRIES : industries;
  
  for (let r = 0; r < industries.length; r++) {
    const indName = industries[r];
    // 如果启用筛选但该行业不活跃，跳过
    if (filterEnabled && !ACTIVE_INDUSTRIES.includes(indName)) continue;
    
    for (let c = 0; c < dates.length; c++) {
      const raw = matrix[r] ? (matrix[r][c] || 0) : 0;
      const val = logScale(raw);
      if (raw > 1) {
        data.push({
          value: [c, r, val],
          _raw: raw,
          itemStyle: {
            borderColor: raw > 2 ? '#f85149cc' : '#e67e22cc',
            borderWidth: 1.5
          }
        });
      } else if (raw > 0) {
        data.push({ value: [c, r, val], _raw: raw });
      }
    }
  }
  return data;
}

function renderHeatmap() {
  const { dates, datesFmt, matrix } = getVisibleRange(currentRange);
  const filterEnabled = document.getElementById('filterActive').checked;
  const heatData = buildHeatmapData(dates, matrix, ALL_INDUSTRIES, filterEnabled);
  const logMax = Math.log1p(8 * 3); // 调整上限

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
        if (!raw) return '';
        const arr = Array.isArray(raw.value) ? raw.value : raw.value;
        const [colIdx, rowIdx] = arr;
        const score = raw._raw !== undefined ? raw._raw : 0;
        const ind = ALL_INDUSTRIES[rowIdx];
        const dateFmt = datesFmt[colIdx];
        const rawDate = dates[colIdx];
        const key = rawDate + '|' + ind;
        const stocks = DETAIL_MAP[key] || [];
        let tip = `<b>${dateFmt}</b> &nbsp; ${ind}<br/>`;
        tip += `突破股票：<b>${stocks.length}</b> 只`;
        if (score > 0) tip += `&nbsp;·&nbsp; 强度得分：<b style="color:${score>2?'#f85149':score>1?'#e67e22':'#58a6ff'}">${score.toFixed(3)}</b>`;
        if (stocks.length > 0) tip += `<br/><span style="color:#8b949e;font-size:11px">点击查看详情</span>`;
        return tip;
      }
    },
    grid: { top: 8, left: 100, right: 20, bottom: 50 },
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
      show: false,
      inRange: {
        // 【新功能4】优化颜色：0分保持深色，0.3开始变蓝，1开始变橙，2以上变红
        color: [
          '#0d1117',  // 0 无
          '#0d2137',  // 0-0.1 极弱
          '#0f3460',  // 0.1-0.3 弱
          '#1a5276',  // 0.3-0.5 较弱
          '#2e86c1',  // 0.5-1 中
          '#e67e22',  // 1-1.5 中强 (橙色开始醒目!)
          '#f39c12',  // 1.5-2 较强
          '#e74c3c',  // 2-3 强
          '#c0392b',  // >3 极强
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
  if (!raw) return;
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
  // 【新功能2】弹窗中也添加同花顺链接
  const rows = stocks.map(s => `
    <tr>
      <td>${s.name}</td>
      <td class="ts-code"><a href="${s.jqka_link}" target="_blank">${s.ts_code}</a></td>
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
    btn.classList.toggle('active', txt === `近${n}日`);
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
html = html.replace('__ACTIVE_INDUSTRIES__', json.dumps(active_industries,   ensure_ascii=False))
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
