"""
每日增量更新脚本 - 本地运行+自动推送版
"""
import warnings
warnings.filterwarnings('ignore')

import os
import sqlite3
import logging
from datetime import datetime, timedelta
import subprocess
import time

import pandas as pd
import tushare as ts

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "data", "ath_monitor.db")

# Tushare Token
TUSHARE_TOKEN = "148de68923b3d98355af96c5dc907e82f690d37762876f9df5dd1446"

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
    try:
        df = ts.pro_bar(ts_code=ts_code, start_date=trade_date, end_date=trade_date, adj='qfq')
        return df.iloc[0] if df is not None and not df.empty else None
    except:
        return None


def git_push():
    log.info("开始推送到 GitHub...")
    try:
        subprocess.run(['git', 'add', 'data/ath_monitor.db', 'docs/index.html'], cwd=BASE_DIR, check=True)
        subprocess.run(['git', 'commit', '-m', f'更新数据 - {datetime.now().strftime("%Y%m%d")}'], cwd=BASE_DIR, check=True)
        subprocess.run(['git', 'push'], cwd=BASE_DIR, check=True)
        log.info("推送成功!")
    except subprocess.CalledProcessError as e:
        log.warning(f"推送失败: {e}")


def update_daily():
    log.info("=" * 50)
    log.info("开始每日增量更新")
    
    conn = sqlite3.connect(DB_PATH)
    trade_date = get_latest_trade_date()
    log.info(f"更新日期: {trade_date}")
    
    stocks = pd.read_sql("SELECT ts_code, name, industry, latest_ath_high FROM ath_latest", conn)
    log.info(f"共 {len(stocks)} 只股票需要检查")
    
    new_breakouts = []
    checked = 0
    
    for _, row in stocks.iterrows():
        ts_code = row['ts_code']
        log.info(f'开始检查{ts_code}')
        latest_ath_high = row['latest_ath_high']
        if latest_ath_high is None or pd.isna(latest_ath_high):
            continue
        
        daily = fetch_qfq_data(ts_code, trade_date)
        if daily is None:
            continue
        
        checked += 1
        if checked % 200 == 0:
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
    
    log.info("生成仪表板...")
    os.system(f'python "{os.path.join(BASE_DIR, "scripts", "generate_dashboard.py")}"')
    
    git_push()
    log.info("更新完成!")
    log.info("=" * 50)


if __name__ == "__main__":
    update_daily()
