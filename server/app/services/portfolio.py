from typing import Dict, List, Any
from datetime import date, datetime, time as dtime, timedelta
from zoneinfo import ZoneInfo
import pandas as pd
from sqlmodel import Session, select
from ..models import Account, Holding, Transaction, TransactionType, HoldingMeta, Strategy
from .prices import get_latest_and_prev_close, get_history, get_ohlc, heikin_ashi, bollinger_bands, rsi_series


_AGG_CACHE: Dict[str, Dict[str, Any]] = {}


def _ist_now() -> datetime:
    return datetime.now(ZoneInfo("Asia/Kolkata"))


def _is_market_open(now: datetime | None = None) -> bool:
    now = now or _ist_now()
    if now.weekday() >= 5:  # Sat/Sun
        return False
    t = now.time()
    return (t >= dtime(9, 15)) and (t < dtime(16, 0))


def _next_market_open(now: datetime | None = None) -> datetime:
    now = now or _ist_now()
    target_date = now.date()
    if now.weekday() < 5 and now.time() < dtime(9, 15):
        # before open today
        pass
    else:
        # after close or weekend -> move to next weekday
        while True:
            target_date = target_date + timedelta(days=1)
            if datetime.combine(target_date, dtime(9, 15)).weekday() < 5:
                break
    return datetime.combine(target_date, dtime(9, 15), tzinfo=ZoneInfo("Asia/Kolkata"))


def _agg_cache_get(key: str) -> Any | None:
    item = _AGG_CACHE.get(key)
    if not item:
        return None
    exp: datetime = item.get("expiry")  # type: ignore
    if exp and exp > _ist_now():
        return item.get("value")
    return None


def _agg_cache_set(key: str, value: Any) -> None:
    now = _ist_now()
    expiry = now + timedelta(seconds=60) if _is_market_open(now) else _next_market_open(now)
    _AGG_CACHE[key] = {"value": value, "expiry": expiry, "updated_at": now}


def invalidate_user_cache(user_id: int, holding_id: int | None = None) -> None:
    # Remove cached entries for this user (summary, breakdown, holdings_pl, charts)
    prefixes = [
        f"summary:{user_id}",
        f"account_breakdown:{user_id}",
        f"equity_curve:{user_id}:",
        f"holdings_pl:{user_id}",
        f"active_charts:{user_id}:",
    ]
    if holding_id is not None:
        prefixes.append(f"holding_chart:{user_id}:{holding_id}:")
    to_del = [k for k in list(_AGG_CACHE.keys()) if any(k.startswith(p) for p in prefixes)]
    for k in to_del:
        try:
            del _AGG_CACHE[k]
        except KeyError:
            pass


def portfolio_summary(session: Session, user_id: int) -> Dict:
    cache_key = f"summary:{user_id}"
    cached = _agg_cache_get(cache_key)
    if cached is not None:
        return cached
    accounts = session.exec(select(Account).where(Account.user_id == user_id)).all()
    account_ids = [a.id for a in accounts]
    holdings = session.exec(select(Holding).where(Holding.account_id.in_(account_ids))).all() if account_ids else []
    total_value = 0.0
    unrealized = 0.0
    daily_change = 0.0
    invested_total = 0.0
    for h in holdings:
        if h.quantity <= 0:
            continue
        p = get_latest_and_prev_close(h.symbol)
        last = p.get("last") or 0.0
        prev = p.get("prev_close") or last
        value = last * h.quantity
        total_value += value
        unrealized += (last - h.average_price) * h.quantity
        daily_change += (last - prev) * h.quantity
        invested_total += float(h.total_cost or 0.0)
    realized = 0.0
    txns = session.exec(select(Transaction).where(Transaction.holding_id.in_([h.id for h in holdings]))).all() if holdings else []
    txns_by_h: Dict[int, float] = {}
    for t in txns:
        realized += t.realized_profit
        txns_by_h[t.holding_id] = txns_by_h.get(t.holding_id, 0.0) + float(t.realized_profit)

    active_trades = sum(1 for h in holdings if h.quantity > 0)
    closed_trades = sum(1 for h in holdings if h.quantity <= 0 and any(t.holding_id == h.id for t in txns))
    profitable_closed = sum(1 for h in holdings if h.quantity <= 0 and txns_by_h.get(h.id, 0.0) > 0)
    total_trades = active_trades + closed_trades
    profitable_pct = (profitable_closed / closed_trades * 100.0) if closed_trades > 0 else 0.0
    total_profit = unrealized + realized
    total_return_pct = (total_profit / invested_total * 100.0) if invested_total > 0 else 0.0
    result = {
        "portfolio_value": round(total_value, 2),
        "total_profit": round(total_profit, 2),
        "daily_change": round(daily_change, 2),
        "unrealized": round(unrealized, 2),
        "realized": round(realized, 2),
        "invested_value": round(invested_total, 2),
        "total_return_pct": round(total_return_pct, 2),
        "total_trades": int(total_trades),
        "active_trades": int(active_trades),
        "closed_trades": int(closed_trades),
        "profitable_trades_pct": round(profitable_pct, 2),
    }
    _agg_cache_set(cache_key, result)
    return result


def account_breakdown(session: Session, user_id: int) -> Dict:
    cache_key = f"account_breakdown:{user_id}"
    cached = _agg_cache_get(cache_key)
    if cached is not None:
        return cached
    accounts = session.exec(select(Account).where(Account.user_id == user_id)).all()
    result = []
    for a in accounts:
        holdings = session.exec(select(Holding).where(Holding.account_id == a.id)).all()
        total_value = 0.0
        unrealized = 0.0
        daily_change = 0.0
        realized = 0.0
        invested = 0.0
        for h in holdings:
            if h.quantity <= 0:
                continue
            p = get_latest_and_prev_close(h.symbol)
            last = p.get("last") or 0.0
            prev = p.get("prev_close") or last
            total_value += last * h.quantity
            unrealized += (last - h.average_price) * h.quantity
            daily_change += (last - prev) * h.quantity
            invested += float(h.total_cost or 0.0)
        txns = session.exec(select(Transaction).where(Transaction.holding_id.in_([h.id for h in holdings]))).all() if holdings else []
        for t in txns:
            realized += t.realized_profit
        total_profit = unrealized + realized
        pct = (total_profit / invested * 100.0) if invested > 0 else 0.0
        result.append({
            "account_id": a.id,
            "name": a.name,
            "broker": a.broker.value if a.broker else None,
            "portfolio_value": round(total_value, 2),
            "total_profit": round(total_profit, 2),
            "invested_value": round(invested, 2),
            "return_pct": round(pct, 2),
        })
    payload = {"accounts": result}
    _agg_cache_set(cache_key, payload)
    return payload


def equity_curve(session: Session, user_id: int, days: int = 60) -> Dict:
    cache_key = f"equity_curve:{user_id}:{days}"
    cached = _agg_cache_get(cache_key)
    if cached is not None:
        if isinstance(cached, dict) and isinstance(cached.get("portfolio_values"), list):
            return cached
    start = date.today() - timedelta(days=days)
    accounts = session.exec(select(Account).where(Account.user_id == user_id)).all()
    holdings = session.exec(select(Holding).where(Holding.account_id.in_([a.id for a in accounts]))).all() if accounts else []
    holding_ids = [h.id for h in holdings]
    holding_symbol = {h.id: h.symbol for h in holdings}
    holding_total_cost = {h.id: float(h.total_cost or 0.0) for h in holdings}
    holding_current_qty = {h.id: float(h.quantity or 0.0) for h in holdings}
    # Window transactions
    txns = session.exec(
        select(Transaction)
        .where(Transaction.holding_id.in_(holding_ids), Transaction.transaction_date >= start)
        .order_by(Transaction.transaction_date)
    ).all() if holding_ids else []

    all_txns = session.exec(
        select(Transaction)
        .where(Transaction.holding_id.in_(holding_ids))
        .order_by(Transaction.transaction_date, Transaction.id)
    ).all() if holding_ids else []

    symbols = sorted(list(set(holding_symbol.values())))
    price_df = get_history(symbols, days=days)
    if price_df is None or price_df.empty:
        total_value = 0.0
        total_unreal = 0.0
        total_realized = 0.0
        qty_by_symbol: Dict[str, float] = {}
        for h in holdings:
            qty_by_symbol[h.symbol] = qty_by_symbol.get(h.symbol, 0.0) + float(h.quantity or 0.0)
        for sym, qty in qty_by_symbol.items():
            if qty <= 0:
                continue
            p = get_latest_and_prev_close(sym)
            last = float(p.get("last") or 0.0)
            total_value += last * qty
        for h in holdings:
            if float(h.quantity or 0.0) <= 0:
                continue
            p = get_latest_and_prev_close(h.symbol)
            last = float(p.get("last") or 0.0)
            total_unreal += (last - float(h.average_price or 0.0)) * float(h.quantity or 0.0)
        if all_txns:
            total_realized = float(sum(float(t.realized_profit or 0.0) for t in all_txns))
        n = max(2, min(int(days or 60), 180))
        idx = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=n)
        payload = {
            "dates": [d.date().isoformat() for d in idx],
            "portfolio_values": [round(float(total_value), 2)] * len(idx),
            "realized_values": [round(float(total_realized), 2)] * len(idx),
            "unrealized_values": [round(float(total_unreal), 2)] * len(idx),
        }
        payload["values"] = payload["portfolio_values"]
        _agg_cache_set(cache_key, payload)
        return payload

    # Build Close dataframe per symbol
    if isinstance(price_df.columns, pd.MultiIndex):
        close_df = pd.DataFrame({sym: price_df[sym]["Close"] for sym in symbols if (sym, "Close") in price_df.columns})
    else:
        close_df = pd.DataFrame({symbols[0]: price_df["Close"]}) if symbols else pd.DataFrame()
    close_df.index = close_df.index.date
    # Ensure unique index to avoid reindex errors
    close_df.index = pd.Index(close_df.index)
    close_df = close_df[~close_df.index.duplicated(keep="last")]

    dates = sorted(list(set(close_df.index) | {t.transaction_date for t in txns}))
    dates = [d for d in dates if d >= start]
    if not dates:
        payload = {"dates": [], "portfolio_values": [], "realized_values": [], "unrealized_values": []}
        payload["values"] = payload["portfolio_values"]
        _agg_cache_set(cache_key, payload)
        return payload

    # Baseline quantity per symbol as of 'start': current qty minus net changes within window
    net_window_delta: Dict[str, float] = {sym: 0.0 for sym in symbols}
    for t in txns:
        sym = holding_symbol.get(t.holding_id)
        if not sym:
            continue
        delta = t.quantity if t.transaction_type == TransactionType.BUY else -t.quantity
        net_window_delta[sym] += float(delta)
    current_qty: Dict[str, float] = {}
    for h in holdings:
        current_qty[h.symbol] = current_qty.get(h.symbol, 0.0) + float(h.quantity or 0.0)
    baseline_qty: Dict[str, float] = {sym: current_qty.get(sym, 0.0) - net_window_delta.get(sym, 0.0) for sym in symbols}

    # Initialize qty df with baseline for the whole date range
    qty_df = pd.DataFrame({sym: baseline_qty.get(sym, 0.0) for sym in symbols}, index=dates, dtype=float)

    # Apply each transaction delta to all subsequent dates
    for t in txns:
        sym = holding_symbol.get(t.holding_id)
        if not sym:
            continue
        delta = t.quantity if t.transaction_type == TransactionType.BUY else -t.quantity
        qty_df.loc[t.transaction_date:, sym] = qty_df.loc[t.transaction_date:, sym] + float(delta)

    # Align and forward-fill prices
    #close_df = close_df.reindex(dates).fillna(method="ffill").fillna(0.0)
    close_df = close_df.reindex(dates).ffill().fillna(0.0)
    txns_by_h: Dict[int, List[Transaction]] = {}
    for t in all_txns:
        txns_by_h.setdefault(int(t.holding_id), []).append(t)

    portfolio_values: List[float] = [0.0] * len(dates)
    realized_values: List[float] = [0.0] * len(dates)
    unrealized_values: List[float] = [0.0] * len(dates)

    for hid, sym in holding_symbol.items():
        sym_txns = txns_by_h.get(int(hid), [])
        i_txn = 0
        qty = 0.0
        cost = 0.0
        realized = 0.0

        if not sym_txns:
            qty = float(holding_current_qty.get(hid, 0.0) or 0.0)
            cost = float(holding_total_cost.get(hid, 0.0) or 0.0)

        for i, d_ in enumerate(dates):
            while i_txn < len(sym_txns) and sym_txns[i_txn].transaction_date <= d_:
                t = sym_txns[i_txn]
                tq = float(t.quantity or 0.0)
                tp = float(t.price or 0.0)
                if t.transaction_type == TransactionType.BUY:
                    cost = cost + tq * tp
                    qty = qty + tq
                else:
                    avg = (cost / qty) if qty > 0 else 0.0
                    realized = realized + (tp - avg) * tq
                    cost = cost - avg * tq
                    qty = qty - tq
                    if qty <= 0:
                        qty = 0.0
                        cost = 0.0
                i_txn += 1

            try:
                px = float(close_df.loc[d_, sym])
            except Exception:
                px = 0.0
            mv = qty * px
            portfolio_values[i] = portfolio_values[i] + mv
            unrealized_values[i] = unrealized_values[i] + (mv - cost)
            realized_values[i] = realized_values[i] + realized

    eq_dates = [d.isoformat() for d in dates]
    payload = {
        "dates": eq_dates,
        "portfolio_values": [round(float(v), 2) for v in portfolio_values],
        "realized_values": [round(float(v), 2) for v in realized_values],
        "unrealized_values": [round(float(v), 2) for v in unrealized_values],
    }
    payload["values"] = payload["portfolio_values"]
    _agg_cache_set(cache_key, payload)
    return payload


def holdings_pl(session: Session, user_id: int) -> Dict:
    cache_key = f"holdings_pl:{user_id}"
    cached = _agg_cache_get(cache_key)
    if cached is not None:
        return cached
    accounts = session.exec(select(Account).where(Account.user_id == user_id)).all()
    if not accounts:
        return {"holdings": []}
    account_ids = [a.id for a in accounts]
    account_name = {a.id: a.name for a in accounts}
    strategies = session.exec(select(Strategy).where(Strategy.user_id == user_id)).all()
    strategy_name_map = {s.id: s.name for s in strategies if s.id is not None}
    holdings = session.exec(select(Holding).where(Holding.account_id.in_(account_ids))).all()
    metas = session.exec(select(HoldingMeta).where(HoldingMeta.holding_id.in_([h.id for h in holdings]))).all() if holdings else []
    sl_map = {m.holding_id: float(m.sl_price or 0.0) for m in metas}
    results = []
    for h in holdings:
        # Sum realized P/L across all transactions of this holding
        txns = session.exec(
            select(Transaction)
            .where(Transaction.holding_id == h.id)
            .order_by(Transaction.transaction_date, Transaction.id)
        ).all()
        realized = sum(float(t.realized_profit) for t in txns)
        entry_notes = None
        entry_strategy_id = None
        entry_strategy_name = None
        for t in txns:
            try:
                if t.transaction_type == TransactionType.BUY and getattr(t, "notes", None):
                    n = str(getattr(t, "notes", "")).strip()
                    if n:
                        entry_notes = n
                        break
            except Exception:
                continue

        for t in txns:
            try:
                if t.transaction_type != TransactionType.BUY:
                    continue
                sid = getattr(t, "strategy_id", None)
                if sid is None:
                    continue
                sname = strategy_name_map.get(sid)
                if sname:
                    entry_strategy_id = int(sid)
                    entry_strategy_name = str(sname)
                    break
            except Exception:
                continue

        p = get_latest_and_prev_close(h.symbol)
        last = p.get("last") or 0.0
        prev = p.get("prev_close") or last
        market_value = float(last) * float(h.quantity)
        unreal = (float(last) - float(h.average_price)) * float(h.quantity)
        daily_pl = (float(last) - float(prev)) * float(h.quantity)
        invested_value = float(h.total_cost or 0.0)
        pct_return = (unreal / invested_value * 100.0) if invested_value > 0 else 0.0
        sl_price = sl_map.get(h.id, 0.0)
        risk = float(h.average_price) - float(sl_price) if sl_price and sl_price > 0 else 0.0
        r1 = float(h.average_price) + risk if risk > 0 else None
        r2 = float(h.average_price) + 2 * risk if risk > 0 else None
        r3 = float(h.average_price) + 3 * risk if risk > 0 else None
        sl_breached = bool(sl_price and sl_price > 0 and last <= sl_price)
        r1_hit = bool(r1 and last >= r1)
        r2_hit = bool(r2 and last >= r2)
        r3_hit = bool(r3 and last >= r3)

        # TLSL (today-only): if yesterday candle red and today's close < yesterday low
        tlsl_price = 0.0
        tlsl_hit = False
        sma23 = None
        sma23_breached = False
        if h.quantity > 0:
            try:
                df_ = get_ohlc(h.symbol, days=90, append_live=True)
                if df_ is not None and len(df_) >= 2:
                    df_ = df_.sort_index()
                    prev = df_.iloc[-2]
                    last_row = df_.iloc[-1]
                    if float(prev['close']) < float(prev['open']):
                        tlsl_price = float(prev['low'])
                        if float(last_row['close']) <= float(prev['low']):
                            tlsl_hit = True
                    if len(df_) >= 23:
                        sma_val = float(df_['close'].rolling(23).mean().iloc[-1])
                        if sma_val == sma_val:
                            sma23 = sma_val
                            sma23_breached = float(last_row['close']) < sma_val
            except Exception:
                pass

        # Show active positions or closed with realized history
        if h.quantity > 0 or abs(realized) > 0:
            results.append({
                "holding_id": h.id,
                "account_id": h.account_id,
                "account_name": account_name.get(h.account_id),
                "symbol": h.symbol,
                "strategy_id": entry_strategy_id,
                "strategy": entry_strategy_name,
                "quantity": round(float(h.quantity), 4),
                "average_price": round(float(h.average_price), 2),
                "total_cost": round(float(h.total_cost), 2),
                "last_price": round(float(last), 2),
                "market_value": round(float(market_value), 2),
                "unrealized_pl": round(float(unreal), 2),
                "realized_pl": round(float(realized), 2),
                "daily_pl": round(float(daily_pl), 2),
                "invested_value": round(float(invested_value), 2),
                "return_pct": round(float(pct_return), 2),
                "notes": entry_notes,
                "sl_price": round(float(sl_price), 2) if sl_price else 0.0,
                "sl_breached": sl_breached,
                "r1": round(float(r1), 2) if r1 else None,
                "r2": round(float(r2), 2) if r2 else None,
                "r3": round(float(r3), 2) if r3 else None,
                "r1_hit": r1_hit,
                "r2_hit": r2_hit,
                "r3_hit": r3_hit,
                "tlsl_price": round(float(tlsl_price), 2) if tlsl_price else 0.0,
                "tlsl_hit": tlsl_hit,
                "sma23": round(float(sma23), 2) if sma23 is not None else None,
                "sma23_breached": bool(sma23_breached),
            })
    payload = {"holdings": results}
    _agg_cache_set(cache_key, payload)
    return payload


def holding_chart(session: Session, user_id: int, holding_id: int, days: int = 90) -> Dict:
    cache_key = f"holding_chart:{user_id}:{holding_id}:{days}"
    cached = _agg_cache_get(cache_key)
    if cached is not None:
        return cached
    h = session.get(Holding, holding_id)
    if not h:
        return {"error": "not_found"}
    acc = session.get(Account, h.account_id)
    if not acc or acc.user_id != user_id:
        return {"error": "forbidden"}
    df = get_ohlc(h.symbol, days=days, append_live=True)
    if df is None or df.empty:
        return {"holding_id": h.id, "symbol": h.symbol, "dates": [], "ohlc": {}, "bb": {}, "buy_price": float(h.average_price)}
    df = df.sort_index()
    ha = heikin_ashi(df)
    bb = bollinger_bands(df['close'])
    rsi = rsi_series(df['close'])
    meta = session.exec(select(HoldingMeta).where(HoldingMeta.holding_id == h.id)).first()
    sl_price = float(meta.sl_price) if meta else 0.0
    risk = float(h.average_price) - float(sl_price) if sl_price and sl_price > 0 else 0.0
    r1 = float(h.average_price) + risk if risk > 0 else None
    r2 = float(h.average_price) + 2 * risk if risk > 0 else None
    r3 = float(h.average_price) + 3 * risk if risk > 0 else None
    # TLSL
    tlsl_price = 0.0
    tlsl_hit = False
    if len(df) >= 2:
        prev = df.iloc[-2]
        last_row = df.iloc[-1]
        if float(prev['close']) < float(prev['open']):
            tlsl_price = float(prev['low'])
            if float(last_row['close']) <= float(prev['low']):
                tlsl_hit = True
    dates = [d.date().isoformat() for d in df.index]
    result = {
        "holding_id": h.id,
        "symbol": h.symbol,
        "buy_price": round(float(h.average_price), 2),
        "sl_price": round(float(sl_price), 2) if sl_price else 0.0,
        "r_levels": [round(float(x), 2) if x else None for x in [r1, r2, r3]],
        "tlsl_price": round(float(tlsl_price), 2) if tlsl_price else 0.0,
        "tlsl_hit": tlsl_hit,
        "dates": dates,
        "ohlc": {
            "open": [round(float(x), 2) for x in df['open'].tolist()],
            "high": [round(float(x), 2) for x in df['high'].tolist()],
            "low": [round(float(x), 2) for x in df['low'].tolist()],
            "close": [round(float(x), 2) for x in df['close'].tolist()],
            "volume": [round(float(x), 2) if (x == x) else 0.0 for x in (df['volume'].tolist() if 'volume' in df.columns else [0]*len(df))],
        },
        "heikin": {
            "open": [round(float(x), 2) for x in ha['open'].tolist()],
            "high": [round(float(x), 2) for x in ha['high'].tolist()],
            "low": [round(float(x), 2) for x in ha['low'].tolist()],
            "close": [round(float(x), 2) for x in ha['close'].tolist()],
        },
        "bb": {
            "upper": [round(float(x), 2) if (x == x) else None for x in bb['upper'].tolist()],
            "middle": [round(float(x), 2) if (x == x) else None for x in bb['middle'].tolist()],
            "lower": [round(float(x), 2) if (x == x) else None for x in bb['lower'].tolist()],
        },
        "rsi": [round(float(x), 2) if (x == x) else None for x in rsi.tolist()],
    }
    _agg_cache_set(cache_key, result)
    return result


def active_holdings_charts(session: Session, user_id: int, days: int = 90) -> Dict:
    cache_key = f"active_charts:{user_id}:{days}"
    cached = _agg_cache_get(cache_key)
    if cached is not None:
        return cached
    accounts = session.exec(select(Account).where(Account.user_id == user_id)).all()
    account_ids = [a.id for a in accounts]
    holdings = session.exec(select(Holding).where(Holding.account_id.in_(account_ids))).all() if account_ids else []
    actives = [h for h in holdings if h.quantity > 0]
    metas = session.exec(select(HoldingMeta).where(HoldingMeta.holding_id.in_([h.id for h in actives]))).all() if actives else []
    sl_map = {m.holding_id: float(m.sl_price or 0.0) for m in metas}
    out = []
    for h in actives:
        df = get_ohlc(h.symbol, days=days, append_live=True)
        if df is None or df.empty:
            continue
        df = df.sort_index()
        ha = heikin_ashi(df)
        bb = bollinger_bands(df['close'])
        dates = [d.date().isoformat() for d in df.index]
        rsi = rsi_series(df['close'])
        sl_price = sl_map.get(h.id, 0.0)
        risk = float(h.average_price) - float(sl_price) if sl_price and sl_price > 0 else 0.0
        r1 = float(h.average_price) + risk if risk > 0 else None
        r2 = float(h.average_price) + 2 * risk if risk > 0 else None
        r3 = float(h.average_price) + 3 * risk if risk > 0 else None
        # TLSL
        tlsl_price = 0.0
        tlsl_hit = False
        if len(df) >= 2:
            prev = df.iloc[-2]
            last_row = df.iloc[-1]
            if float(prev['close']) < float(prev['open']):
                tlsl_price = float(prev['low'])
                if float(last_row['close']) <= float(prev['low']):
                    tlsl_hit = True
        out.append({
            "holding_id": h.id,
            "symbol": h.symbol,
            "buy_price": round(float(h.average_price), 2),
            "sl_price": round(float(sl_price), 2) if sl_price else 0.0,
            "r_levels": [round(float(x), 2) if x else None for x in [r1, r2, r3]],
            "tlsl_price": round(float(tlsl_price), 2) if tlsl_price else 0.0,
            "tlsl_hit": tlsl_hit,
            "dates": dates,
            "ohlc": {
                "open": [round(float(x), 2) for x in df['open'].tolist()],
                "high": [round(float(x), 2) for x in df['high'].tolist()],
                "low": [round(float(x), 2) for x in df['low'].tolist()],
                "close": [round(float(x), 2) for x in df['close'].tolist()],
                "volume": [round(float(x), 2) if (x == x) else 0.0 for x in (df['volume'].tolist() if 'volume' in df.columns else [0]*len(df))],
            },
            "heikin": {
                "open": [round(float(x), 2) for x in ha['open'].tolist()],
                "high": [round(float(x), 2) for x in ha['high'].tolist()],
                "low": [round(float(x), 2) for x in ha['low'].tolist()],
                "close": [round(float(x), 2) for x in ha['close'].tolist()],
            },
            "bb": {
                "upper": [round(float(x), 2) if (x == x) else None for x in bb['upper'].tolist()],
                "middle": [round(float(x), 2) if (x == x) else None for x in bb['middle'].tolist()],
                "lower": [round(float(x), 2) if (x == x) else None for x in bb['lower'].tolist()],
            },
            "rsi": [round(float(x), 2) if (x == x) else None for x in rsi.tolist()],
        })
    payload = {"charts": out}
    _agg_cache_set(cache_key, payload)
    return payload


def get_agg_cache_entry(key: str) -> Any | None:
    return _AGG_CACHE.get(key)
