from typing import Dict, List, Optional
from datetime import datetime, timedelta, time as dtime
from zoneinfo import ZoneInfo
import time
import requests
import pandas as pd
import yfinance as yf


_CACHE_TTL_SEC = 60
_QUOTE_CACHE: Dict[str, Dict] = {}
_OC_INIT = False
_OC_NSE = None  # type: ignore
_OHLC_CACHE: Dict[str, Dict] = {}


def _ensure_openchart():
    global _OC_INIT, _OC_NSE
    if _OC_INIT:
        return _OC_NSE
    try:
        from openchart import NSEData  # type: ignore
        nse = NSEData()
        # Download master once
        try:
            nse.download()
        except Exception:
            pass
        _OC_NSE = nse
    except Exception:
        _OC_NSE = None
    _OC_INIT = True
    return _OC_NSE


def _yf_symbol(symbol: str) -> str:
    s = (symbol or "").strip()
    if not s:
        return s
    if "." in s or ":" in s or s.startswith("^"):
        return s
    return f"{s}.NS"


def _yf_candidates(symbol: str) -> List[str]:
    s = (symbol or "").strip()
    if not s:
        return []
    if "." in s or ":" in s or s.startswith("^"):
        return [s]
    # Prefer NSE, then BSE
    return [f"{s}.NS", f"{s}.BO"]


def _merged_candidates(symbol: str) -> List[str]:
    base = _yf_candidates(symbol)
    extra = _yahoo_search_candidates(symbol)
    seen = set()
    merged: List[str] = []
    for x in base + extra:
        if not x or x in seen:
            continue
        seen.add(x)
        merged.append(x)
    return merged


def _yahoo_search_candidates(symbol: str) -> List[str]:
    s = (symbol or '').strip()
    if not s:
        return []
    try:
        url = "https://query2.finance.yahoo.com/v1/finance/search"
        params = {"q": s, "quotesCount": 6, "newsCount": 0, "lang": "en-IN", "region": "IN"}
        headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
        r = requests.get(url, params=params, headers=headers, timeout=6)
        r.raise_for_status()
        js = r.json() or {}
        quotes = js.get("quotes", []) or []
        out: List[str] = []
        for q in quotes:
            sym = q.get("symbol")
            exch = (q.get("exchDisp") or q.get("exchange" ) or '').upper()
            if not sym:
                continue
            # Prefer NSE/BSE listings
            if exch in ("NSE", "NSI", "BSE"):
                out.append(sym)
        # de-dup and keep at most 4
        seen = set()
        uniq = []
        for x in out:
            if x in seen:
                continue
            seen.add(x)
            uniq.append(x)
        return uniq[:4]
    except Exception:
        return []


def _cache_get(key: str) -> Optional[Dict]:
    item = _QUOTE_CACHE.get(key)
    if not item:
        return None
    ts = item.get("_ts")
    if ts and (time.time() - ts) < _CACHE_TTL_SEC:
        return item
    return None


def _ist_now() -> datetime:
    return datetime.now(ZoneInfo("Asia/Kolkata"))


def _is_market_open(now: Optional[datetime] = None) -> bool:
    now = now or _ist_now()
    if now.weekday() >= 5:
        return False
    t = now.time()
    return dtime(9, 15) <= t < dtime(16, 0)


def _next_market_open(now: Optional[datetime] = None) -> datetime:
    now = now or _ist_now()
    d = now.date()
    if now.weekday() < 5 and now.time() < dtime(9, 15):
        pass
    else:
        # move to next weekday
        while True:
            d = d + timedelta(days=1)
            if datetime.combine(d, dtime(9, 15)).weekday() < 5:
                break
    return datetime.combine(d, dtime(9, 15), tzinfo=ZoneInfo("Asia/Kolkata"))


def _openchart_eod_series(symbol: str, days: int = 60) -> Optional[pd.Series]:
    nse = _ensure_openchart()
    if not nse:
        return None
    try:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=max(days, 2))
        df = nse.historical(symbol=symbol, exchange='NSE', start=start_date, end=end_date, interval='1d')
        if df is None or df.empty:
            return None
        # Identify close column robustly
        close_col = None
        for c in df.columns:
            if str(c).lower() == 'close':
                close_col = c
                break
        if close_col is None:
            return None
        # Identify datetime index/column
        if isinstance(df.index, pd.DatetimeIndex):
            s = df[close_col].copy()
            s.index = pd.to_datetime(s.index)
        else:
            # Try common columns
            dt_col = None
            for c in df.columns:
                if str(c).lower() in ('date', 'datetime', 'timestamp'):
                    dt_col = c
                    break
            if dt_col is None:
                return None
            s = pd.Series(df[close_col].values, index=pd.to_datetime(df[dt_col]))
        s = s.dropna()
        return s
    except Exception:
        return None


def _cache_set(key: str, data: Dict) -> None:
    data = dict(data)
    data["_ts"] = time.time()
    _QUOTE_CACHE[key] = data


def _set_ohlc_cache(key: str, df: pd.DataFrame) -> None:
    now = _ist_now()
    expiry = now + timedelta(seconds=300) if _is_market_open(now) else _next_market_open(now)
    _OHLC_CACHE[key] = {"df": df.copy(), "expiry": expiry}


def _get_ohlc_cache(key: str) -> Optional[pd.DataFrame]:
    item = _OHLC_CACHE.get(key)
    if not item:
        return None
    exp = item.get("expiry")
    if isinstance(exp, datetime) and exp > _ist_now():
        return item.get("df")
    return None


def _yahoo_quote_api(symbol: str) -> Dict[str, Optional[float]]:
    # Call Yahoo quote endpoint directly; try multiple hosts
    hosts = ["query1.finance.yahoo.com", "query2.finance.yahoo.com"]
    for host in hosts:
        try:
            url = f"https://{host}/v7/finance/quote"
            params = {"symbols": symbol, "region": "IN", "lang": "en-IN"}
            headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
            r = requests.get(url, params=params, headers=headers, timeout=6)
            r.raise_for_status()
            js = r.json()
            res = (js or {}).get("quoteResponse", {}).get("result", [])
            if not res:
                continue
            q = res[0]
            last = q.get("regularMarketPrice")
            prev = q.get("regularMarketPreviousClose")
            return {"last": float(last) if last is not None else None, "prev_close": float(prev) if prev is not None else None}
        except Exception:
            continue
    return {"last": None, "prev_close": None}


def _yahoo_chart_api(symbol: str, days: int = 2) -> Dict[str, Optional[float]]:
    hosts = ["query1.finance.yahoo.com", "query2.finance.yahoo.com"]
    for host in hosts:
        try:
            rng = "5d" if days >= 5 else "2d"
            url = f"https://{host}/v8/finance/chart/{symbol}"
            params = {"range": rng, "interval": "1d", "region": "IN", "lang": "en-IN"}
            headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
            r = requests.get(url, params=params, headers=headers, timeout=6)
            r.raise_for_status()
            js = r.json()
            res = (js or {}).get("chart", {}).get("result", [])
            if not res:
                continue
            closes = res[0].get("indicators", {}).get("quote", [{}])[0].get("close", [])
            if not closes:
                continue
            cleaned: List[float] = []
            for x in closes:
                if x is None:
                    continue
                try:
                    xf = float(x)
                    if xf == xf:
                        cleaned.append(xf)
                except Exception:
                    continue
            if not cleaned:
                continue
            last = cleaned[-1]
            prev = cleaned[-2] if len(cleaned) >= 2 else None
            return {"last": float(last) if last is not None else None, "prev_close": float(prev) if prev is not None else None}
        except Exception:
            continue
    return {"last": None, "prev_close": None}


def _yahoo_chart_series(symbol: str, days: int = 60) -> Optional[pd.Series]:
    hosts = ["query1.finance.yahoo.com", "query2.finance.yahoo.com"]
    for host in hosts:
        try:
            url = f"https://{host}/v8/finance/chart/{symbol}"
            params = {"range": f"{days}d", "interval": "1d", "region": "IN", "lang": "en-IN"}
            headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
            r = requests.get(url, params=params, headers=headers, timeout=6)
            r.raise_for_status()
            js = r.json()
            res = (js or {}).get("chart", {}).get("result", [])
            if not res:
                continue
            node = res[0]
            ts = node.get("timestamp", [])
            closes = node.get("indicators", {}).get("quote", [{}])[0].get("close", [])
            if not ts or not closes:
                continue
            s = pd.Series(closes, index=pd.to_datetime(ts, unit='s'))
            s = s.dropna()
            return s
        except Exception:
            continue
    return None


def get_latest_and_prev_close(symbol: str) -> Dict[str, Optional[float]]:
    cache_key = f"q:{symbol}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return {"last": cached.get("last"), "prev_close": cached.get("prev_close")}

    # Try candidates in order: NSE then BSE (merge with Yahoo search)
    for cand in _merged_candidates(symbol):
        # 1) Direct quote API (accept if last is present; fill prev via chart if needed)
        q = _yahoo_quote_api(cand)
        if q.get("last") is not None:
            if q.get("prev_close") is None:
                q_chart = _yahoo_chart_api(cand, days=5)
                if q_chart.get("prev_close") is not None:
                    q["prev_close"] = q_chart.get("prev_close")
                elif q_chart.get("last") is not None:
                    q["prev_close"] = q_chart.get("last")
            q["prev_close"] = q.get("prev_close") or q.get("last")
            _cache_set(cache_key, q)
            return q

        # 2) Chart API alone
        q_chart = _yahoo_chart_api(cand, days=5)
        if q_chart.get("last") is not None:
            q_chart["prev_close"] = q_chart.get("prev_close") or q_chart.get("last")
            _cache_set(cache_key, q_chart)
            return q_chart

        # 3) yfinance last/prev as additional fallback (helps *.BO only listings)
        if str(cand).upper().endswith('.BO'):
            try:
                hist = yf.download(cand, period="5d", interval="1d", auto_adjust=False, progress=False, threads=False)
                if hist is not None and not hist.empty:
                    close = hist['Close'].dropna()
                    if not close.empty:
                        last = float(close.iloc[-1])
                        prev = float(close.iloc[-2]) if len(close) >= 2 else last
                        qyf = {"last": last, "prev_close": prev}
                        _cache_set(cache_key, qyf)
                        return qyf
            except Exception:
                pass

    # 4) OpenChart EOD fallback (NSE only)
    try:
        s = _openchart_eod_series(symbol, days=10)
        if s is not None and not s.empty:
            last = float(s.iloc[-1])
            prev = float(s.iloc[-2]) if len(s) >= 2 else last
            q3 = {"last": last, "prev_close": prev}
            _cache_set(cache_key, q3)
            return q3
    except Exception:
        pass

    # Total failure
    qf = {"last": None, "prev_close": None}
    _cache_set(cache_key, qf)
    return qf


def get_history(symbols: List[str], days: int = 60) -> pd.DataFrame:
    if not symbols:
        return pd.DataFrame()
    # Pick best working ticker per symbol by probing quote API (falls back to BSE via yfinance)
    chosen: Dict[str, str] = {}
    for s in symbols:
        picked = None
        for cand in _merged_candidates(s):
            q = _yahoo_quote_api(cand)
            if q.get("last") is not None:
                picked = cand
                break
        if not picked:
            picked = _yf_symbol(s)
        chosen[s] = picked

    # Fetch each symbol using Yahoo chart API first; then yfinance; fallback to OpenChart (NSE only)
    series_map: Dict[tuple, pd.Series] = {}
    for sym, yf_sym in chosen.items():
        s = _yahoo_chart_series(yf_sym, days=days)
        if s is None or s.empty:
            try:
                if str(yf_sym).upper().endswith('.BO'):
                    hist = yf.download(yf_sym, period=f"{days}d", interval="1d", auto_adjust=False, progress=False, threads=False)
                    if hist is not None and not hist.empty:
                        s = hist['Close']
                        s.index = pd.to_datetime(s.index)
            except Exception:
                s = None
        if s is None or s.empty:
            s = _openchart_eod_series(sym, days=days)
        if s is None or s.empty:
            continue
        s.name = (sym, "Close")
        series_map[(sym, "Close")] = s

    if not series_map:
        return pd.DataFrame()

    # Align on the union of indices and build a MultiIndex column DataFrame
    all_idx = None
    for s in series_map.values():
        all_idx = s.index if all_idx is None else all_idx.union(s.index)
    data = {}
    for key, s in series_map.items():
        data[key] = s.reindex(all_idx)
    df = pd.DataFrame(data)
    df.columns = pd.MultiIndex.from_tuples(df.columns)
    return df


# ---------- OHLC utilities for charts ----------
def _yahoo_chart_ohlc(symbol: str, days: int = 90) -> Optional[pd.DataFrame]:
    hosts = ["query1.finance.yahoo.com", "query2.finance.yahoo.com"]
    for host in hosts:
        try:
            url = f"https://{host}/v8/finance/chart/{symbol}"
            params = {"range": f"{days}d", "interval": "1d", "region": "IN", "lang": "en-IN"}
            headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
            r = requests.get(url, params=params, headers=headers, timeout=6)
            r.raise_for_status()
            js = r.json()
            res = (js or {}).get("chart", {}).get("result", [])
            if not res:
                continue
            node = res[0]
            ts = node.get("timestamp", [])
            q = node.get("indicators", {}).get("quote", [{}])[0]
            opens = q.get("open", [])
            highs = q.get("high", [])
            lows = q.get("low", [])
            closes = q.get("close", [])
            volumes = q.get("volume", [])
            if not ts or not closes:
                continue
            idx = pd.to_datetime(ts, unit='s')
            df = pd.DataFrame({
                'open': pd.Series(opens, index=idx, dtype='float64'),
                'high': pd.Series(highs, index=idx, dtype='float64'),
                'low': pd.Series(lows, index=idx, dtype='float64'),
                'close': pd.Series(closes, index=idx, dtype='float64'),
                'volume': pd.Series(volumes, index=idx, dtype='float64') if volumes else pd.Series(index=idx, dtype='float64'),
            }).dropna()
            return df
        except Exception:
            continue
    return None


def _openchart_ohlc(symbol: str, days: int = 90) -> Optional[pd.DataFrame]:
    nse = _ensure_openchart()
    if not nse:
        return None
    try:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=max(days, 2))
        df = nse.historical(symbol=symbol, exchange='NSE', start=start_date, end=end_date, interval='1d')
        if df is None or df.empty:
            return None
        cols = {c.lower(): c for c in df.columns}
        req = ['open', 'high', 'low', 'close']
        if not all(k in cols for k in req):
            return None
        out = pd.DataFrame({
            'open': df[cols['open']].astype(float),
            'high': df[cols['high']].astype(float),
            'low': df[cols['low']].astype(float),
            'close': df[cols['close']].astype(float),
            'volume': df[cols['volume']].astype(float) if 'volume' in cols else pd.Series(index=df.index, dtype='float64'),
        })
        if not isinstance(df.index, pd.DatetimeIndex):
            dt_col = None
            for c in df.columns:
                if str(c).lower() in ('date', 'datetime', 'timestamp'):
                    dt_col = c
                    break
            if dt_col is None:
                return None
            out.index = pd.to_datetime(df[dt_col])
        else:
            out.index = pd.to_datetime(df.index)
        out = out.dropna()
        return out
    except Exception:
        return None


def heikin_ashi(df: pd.DataFrame) -> pd.DataFrame:
    o = df['open'].copy()
    h = df['high'].copy()
    l = df['low'].copy()
    c = df['close'].copy()
    ha_close = (o + h + l + c) / 4.0
    ha_open = ha_close.copy()
    if len(df) > 0:
        ha_open.iloc[0] = (o.iloc[0] + c.iloc[0]) / 2.0
        for i in range(1, len(df)):
            ha_open.iloc[i] = (ha_open.iloc[i-1] + ha_close.iloc[i-1]) / 2.0
    ha_high = pd.concat([h, ha_open, ha_close], axis=1).max(axis=1)
    ha_low = pd.concat([l, ha_open, ha_close], axis=1).min(axis=1)
    return pd.DataFrame({'open': ha_open, 'high': ha_high, 'low': ha_low, 'close': ha_close}, index=df.index)


def bollinger_bands(close: pd.Series, window: int = 20, num_std: float = 2.0) -> pd.DataFrame:
    ma = close.rolling(window).mean()
    std = close.rolling(window).std()
    upper = ma + num_std * std
    lower = ma - num_std * std
    return pd.DataFrame({'upper': upper, 'middle': ma, 'lower': lower}, index=close.index)


def get_ohlc(symbol: str, days: int = 90, append_live: bool = True) -> Optional[pd.DataFrame]:
    key = f"ohlc:{symbol}:{days}"
    cached = _get_ohlc_cache(key)
    if cached is not None and not cached.empty:
        df = cached.copy()
    else:
        df = None
        for cand in _merged_candidates(symbol):
            # 1) Yahoo chart API
            df = _yahoo_chart_ohlc(cand, days=days)
            if df is not None and not df.empty:
                break
            # 2) yfinance as fallback (works for many BSE tickers like *.BO)
            if str(cand).upper().endswith('.BO'):
                try:
                    yf_df = yf.download(cand, period=f"{days}d", interval="1d", auto_adjust=False, progress=False, threads=False)
                    if yf_df is not None and not yf_df.empty:
                        cols = {c.lower(): c for c in yf_df.columns}
                        if all(k in cols for k in ['open','high','low','close']):
                            df = pd.DataFrame({
                                'open': yf_df[cols['open']].astype(float),
                                'high': yf_df[cols['high']].astype(float),
                                'low': yf_df[cols['low']].astype(float),
                                'close': yf_df[cols['close']].astype(float),
                                'volume': yf_df[cols.get('volume','Volume')].astype(float) if (cols.get('volume') or cols.get('volume'.lower()) or cols.get('Volume'.lower())) else pd.Series(index=yf_df.index, dtype='float64'),
                            })
                            df.index = pd.to_datetime(yf_df.index)
                            break
                except Exception:
                    pass
        if df is None or df.empty:
            df = _openchart_ohlc(symbol, days=days)
        if df is None or df.empty:
            return None
        df.index = pd.to_datetime(df.index).tz_localize(None)
        df = df[~df.index.duplicated(keep='last')]
        _set_ohlc_cache(key, df)

    if append_live and _is_market_open():
        q = get_latest_and_prev_close(symbol)
        last = q.get('last')
        if last is not None:
            today = pd.Timestamp(_ist_now().date())
            if today in df.index:
                df.loc[today, ['open', 'high', 'low', 'close']] = [last, last, last, last]
            else:
                # Volume intraday unknown here; keep NaN
                df.loc[today] = [last, last, last, last, float('nan') if 'volume' in df.columns else None]
            df = df.sort_index()
    return df


def rsi_series(close: pd.Series, period: int = 14) -> pd.Series:
    close = close.astype(float)
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


def ema_series(close: pd.Series, span: int) -> pd.Series:
    close = close.astype(float)
    return close.ewm(span=span, min_periods=span, adjust=False).mean()


def atr_series(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high = df['high'].astype(float)
    low = df['low'].astype(float)
    close = df['close'].astype(float)
    prev_close = close.shift(1)
    tr = pd.concat([
        (high - low).abs(),
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1/period, min_periods=period, adjust=False).mean()


def supertrend_direction(df: pd.DataFrame, period: int = 10, multiplier: float = 3.0) -> Optional[bool]:
    if df is None or df.empty:
        return None
    if not all(c in df.columns for c in ('high', 'low', 'close')):
        return None

    df2 = df[['high', 'low', 'close']].dropna().copy()
    if df2.empty or len(df2) < (period + 2):
        return None

    atr = atr_series(df2, period=period)
    atr_valid = atr.dropna()
    if atr_valid.empty:
        return None

    # Start from the first bar where ATR is available to avoid NaN-band issues
    start_idx = atr_valid.index[0]
    df3 = df2.loc[start_idx:].copy()
    atr3 = atr.loc[df3.index]

    if df3.empty or len(df3) < 3:
        return None

    high = df3['high'].astype(float)
    low = df3['low'].astype(float)
    close = df3['close'].astype(float)

    hl2 = (high + low) / 2.0
    upper = hl2 + (multiplier * atr3)
    lower = hl2 - (multiplier * atr3)

    final_upper = upper.copy()
    final_lower = lower.copy()

    for i in range(1, len(df3)):
        prev_fu = float(final_upper.iloc[i - 1])
        prev_fl = float(final_lower.iloc[i - 1])
        prev_close = float(close.iloc[i - 1])

        cur_u = float(upper.iloc[i])
        cur_l = float(lower.iloc[i])

        if cur_u < prev_fu or prev_close > prev_fu:
            final_upper.iloc[i] = cur_u
        else:
            final_upper.iloc[i] = prev_fu

        if cur_l > prev_fl or prev_close < prev_fl:
            final_lower.iloc[i] = cur_l
        else:
            final_lower.iloc[i] = prev_fl

    st = pd.Series(index=df3.index, dtype='float64')
    direction = pd.Series(index=df3.index, dtype='int64')

    # Initialize using first computed bands
    if float(close.iloc[0]) <= float(final_upper.iloc[0]):
        st.iloc[0] = float(final_upper.iloc[0])
        direction.iloc[0] = -1
    else:
        st.iloc[0] = float(final_lower.iloc[0])
        direction.iloc[0] = 1

    for i in range(1, len(df3)):
        prev_st = float(st.iloc[i - 1])
        prev_fu = float(final_upper.iloc[i - 1])
        prev_fl = float(final_lower.iloc[i - 1])
        c = float(close.iloc[i])
        fu = float(final_upper.iloc[i])
        fl = float(final_lower.iloc[i])

        if prev_st == prev_fu:
            if c <= fu:
                st.iloc[i] = fu
                direction.iloc[i] = -1
            else:
                st.iloc[i] = fl
                direction.iloc[i] = 1
        else:
            if c >= fl:
                st.iloc[i] = fl
                direction.iloc[i] = 1
            else:
                st.iloc[i] = fu
                direction.iloc[i] = -1

    return bool(int(direction.iloc[-1]) == 1)
