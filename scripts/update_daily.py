"""
每日增量更新脚本 - 前复权版本
"""
import os
import sqlite3
import logging
from datetime import datetime, timedelta
import time

import pandas as pd
import tushare as ts
from tushare.pro.client import DataApi

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "data", "ath_monitor.db")

TUSHARE_TOKEN = os.environ.get('TUSHARE_TOKEN')
if not TUSHARE_TOKEN:
    raise ValueError("请设置 TUSHARE_TOKEN 环境变量")

ts.set_token(TUSHARE_TOKEN)
pro = ts.pro_api()

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
log = logging.getLogger(__name__)


def get_latest_trade_date():
    today = datetime.now()
    if today.weekday() >= 5:
        days_back = today.weekday() - 4
        today = today - timedelta(days=days_back)
    return today.strftime('%Y%m%d')


def fetch_qfq_data(ts_code, trade_date):
    """获取单只股票前复权数据"""
    try:
        df = ts.pro_bar(
            ts_code=ts_code, 
            start_date=trade_date, 
            end_date=trade_date, 
            adj='qfq'
        )
        if df is None or df.empty:
            return None
        return df.iloc[0]
    except Exception as e:
        return None


def update_daily():
    log.info("=" * 50)
    log.info("开始每日增量更新（前复权版本）")
    
    conn = sqlite3.connect(DB_PATH)
    trade_date = get_latest_trade_date()
    log.info(f"更新日期: {trade_date}")
    
    # 获取股票列表
    stocks = pd.read_sql("SELECT ts_code, name, industry, latest_ath_high FROM ath_latest", conn)
    log.info(f"共 {len(stocks)} 只股票需要检查")
    
    new_breakouts = []
    checked = 0
    
    for idx, row in stocks.iterrows():
        ts_code = row['ts_code']
        latest_ath_high = row['latest_ath_high']
        
        if latest_ath_high is None or pd.isna(latest_ath_high):
            continue
        
        # 获取前复权数据
        daily = fetch_qfq_data(ts_code, trade_date)
        if daily is None:
            continue
        
        checked += 1
        if checked % 100 == 0:
            log.info(f"已检查 {checked}/{len(stocks)} 只股票")
        
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
