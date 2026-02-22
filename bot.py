import ccxt
import pandas as pd
import pytz
import time
import os
from datetime import datetime

# ================== CONFIG ==================
COINS = ['BTC/USDT:USDT', 'ETH/USDT:USDT', 'SOL/USDT:USDT', 'XRP/USDT:USDT', 'DOGE/USDT:USDT']
DRY_RUN = os.getenv('DRY_RUN', 'true').lower() == 'true'
RISK_PERCENT = 2.0
ATR_MULTIPLIER = 0.7
RR = 2.0
# ===========================================

exchange = ccxt.bitget({
    'apiKey': os.getenv('BITGET_API_KEY'),
    'secret': os.getenv('BITGET_API_SECRET'),
    'password': os.getenv('BITGET_PASSPHRASE'),
    'enableRateLimit': True,
    'options': {'defaultType': 'swap'}
})

ny_tz = pytz.timezone('America/New_York')

print("✅ Multi-coin Bitget Bot started - DRY_RUN =", DRY_RUN)
print(f"Scanning: {COINS}")

while True:
    now_ny = datetime.now(ny_tz)
    
    if 3 <= now_ny.hour < 7:
        best_signal = None
        best_score = -1
        
        for symbol in COINS:
            try:
                daily = exchange.fetch_ohlcv(symbol, '1d', limit=250)
                df_d = pd.DataFrame(daily, columns=['ts', 'o', 'h', 'l', 'c', 'v'])
                prev = df_d.iloc[-2]
                
                avg_vol = df_d['v'].rolling(20).mean().iloc[-2]
                rvol = prev['v'] / avg_vol if avg_vol > 0 else 0
                
                if rvol <= 1.2:
                    continue
                    
                close = prev['c']
                df_d['tp'] = (df_d['h'] + df_d['l'] + df_d['c']) / 3
                df_d['tpv'] = df_d['tp'] * df_d['v']
                vwap90 = (df_d['tpv'].rolling(90).sum() / df_d['v'].rolling(90).sum()).iloc[-2]
                
                sma200 = df_d['c'].rolling(200).mean().iloc[-2]
                ema21 = df_d['c'].ewm(span=21, adjust=False).mean().iloc[-2]
                
                is_long_bias = (close > vwap90) and (close > sma200) and (ema21 > sma200)
                is_short_bias = (close < vwap90) and (close < sma200) and (ema21 < sma200)
                
                if not (is_long_bias or is_short_bias):
                    continue
                
                # 15m check
                m15 = exchange.fetch_ohlcv(symbol, '15m', limit=100)
                df15 = pd.DataFrame(m15, columns=['ts', 'o', 'h', 'l', 'c', 'v'])
                current_price = df15['c'].iloc[-1]
                
                prev_vwap = (prev['h'] + prev['l'] + prev['c']) / 3
                
                today_start = now_ny.replace(hour=0, minute=0, second=0, microsecond=0)
                df_today = df15[pd.to_datetime(df15['ts'], unit='ms').dt.tz_localize('UTC').dt.tz_convert(ny_tz) >= today_start]
                current_vwap = (df_today['h'] + df_today['l'] + df_today['c']).mean() if len(df_today) > 0 else current_price
                
                valid = False
                direction = None
                if is_long_bias and current_price > current_vwap and current_price > prev_vwap:
                    valid = True
                    direction = "LONG"
                elif is_short_bias and current_price < current_vwap and current_price < prev_vwap:
                    valid = True
                    direction = "SHORT"
                
                if valid:
                    distance_pct = abs((current_price - vwap90) / vwap90) * 100
                    score = distance_pct * rvol
                    
                    if score > best_score:
                        best_score = score
                        best_signal = {
                            'symbol': symbol,
                            'direction': direction,
                            'price': current_price,
                            'rvol': rvol,
                            'score': score
                        }
                        
            except:
                continue  # skip coin if error
        
        if best_signal:
            print(f"🏆 BEST SIGNAL → {best_signal['direction']} {best_signal['symbol']} @ {best_signal['price']} | Score {best_signal['score']:.1f} | RVOL {best_signal['rvol']:.2f}")
        else:
            print(f"[{now_ny}] No valid setups among 5 coins")
            
    else:
        print(f"[{now_ny}] Waiting for 3-6am NY window...")
        
    time.sleep(60)
