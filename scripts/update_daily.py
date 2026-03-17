"""
每日增量更新脚本 - 适配 GitHub Actions
"""
import os
import sqlite3
import logging
from datetime import datetime, timedelta

import pandas as pd
import tushare as ts

# 配置 - 相对路径
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "data", "ath_monitor.db")

# 从环境变量获取 Tushare Token
TUSHARE_TOKEN = os.environ.get('TUSHARE_TOKEN')
if not TUSHARE_TOKEN:
    raise ValueError("请设置 TUSHARE_TOKEN 环境变量")

ts.set_token(TUSHARE_TOKEN)
pro = ts.pro_api()

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
log = logging.getLogger(__name__)


def get_latest_trade_date():
    """获取最新交易日"""
    today = datetime.now()
    if today.weekday() >= 5:  # 周末回退到周五
        days_back = today.weekday() - 4
        today = today - timedelta(days=days_back)
    date_str = today.strftime('%Y%m%d')
    try:
        df_cal = pro.trade_cal(exchange='SSE', start_date=date_str, end_date=date_str)
        if not df_cal.empty and df_cal.iloc[0]['is_open'] == 0:
            for i in range(1, 10):
                prev_date = today - timedelta(days=i)
                prev_str = prev_date.strftime('%Y%m%d')
                df_cal = pro.trade_cal(exchange='SSE', start_date=prev_str, end_date=prev_str)
                if not df_cal.empty and df_cal.iloc[0]['is_open'] == 1:
                    return prev_str
    except Exception as e:
        log.warning(f"获取交易日历失败: {e}")
    return date_str


def get_stock_list(conn):
    return pd.read_sql("SELECT ts_code, name, industry, latest_ath_high FROM ath_latest", conn)


def fetch_daily_price(ts_code, trade_date):
    try:
        df = pro.daily(ts_code=ts_code, start_date=trade_date, end_date=trade_date)
        return df.iloc[0] if not df.empty else None
    except:
        return None


def update_daily():
    log.info("=" * 50)
    log.info("开始每日增量更新")
    
    conn = sqlite3.connect(DB_PATH)
    trade_date = get_latest_trade_date()
    log.info(f"更新日期: {trade_date}")
    
    stocks = get_stock_list(conn)
    log.info(f"共 {len(stocks)} 只股票需要检查")
    
    new_breakouts = []
    for _, row in stocks.iterrows():
        ts_code = row['ts_code']
        latest_ath_high = row['latest_ath_high']
        if latest_ath_high is None:
            continue
        
        daily = fetch_daily_price(ts_code, trade_date)
        if daily is None:
            continue
        
        try:
            close = float(daily['close'])
            prev_high = float(latest_ath_high)
            if close > prev_high:
                log.info(f"突破: {ts_code} 收盘:{close:.2f} > 前高:{prev_high:.2f}")
                new_breakouts.append({
                    'ts_code': ts_code, 'trade_date': trade_date,
                    'open': daily['open'], 'high': daily['high'], 'low': daily['low'],
                    'close': daily['close'], 'pre_close': daily['pre_close'],
                    'change': daily['change'], 'pct_chg': daily['pct_chg'],
                    'vol': daily['vol'], 'amount': daily['amount'],
                    'industry': row['industry']
                })
                conn.execute("""UPDATE ath_latest SET latest_ath_date=?, latest_ath_close=?, latest_ath_high=? WHERE ts_code=?""",
                    (trade_date, daily['close'], daily['high'], ts_code))
        except:
            continue
    
    if new_breakouts:
        df_new = pd.DataFrame(new_breakouts)
        df_new.to_sql('ath_breakouts', conn, if_exists='append', index=False)
        df_new.to_sql('daily_ath_summary', conn, if_exists='append', index=False)
        log.info(f"新增 {len(new_breakouts)} 条突破记录")
    else:
        log.info("今日无突破股票")
    
    conn.commit()
    conn.close()
    log.info("更新完成!")
    log.info("=" * 50)


if __name__ == "__main__":
    update_daily()
