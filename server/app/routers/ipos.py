from __future__ import annotations

import datetime
from datetime import time as dtime
from zoneinfo import ZoneInfo
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from ..db import get_session
from ..models import IPO, IpoBoard, IpoListingOn, IpoDailyMetrics, IpoQuote, IpoUserTag, IpoRowColor
from ..security import get_current_user, require_admin
from ..services.prices import get_latest_and_prev_close, get_ohlc, ema_series, supertrend_direction, supertrend_direction_series


router = APIRouter(prefix="/ipos", tags=["ipos"])


class IpoCreate(BaseModel):
    name: str
    symbol: str
    bse_symbol: Optional[str] = None
    board: IpoBoard = IpoBoard.mainboard
    ipo_price: Optional[float] = None
    listing_price: Optional[float] = None
    lot_size: Optional[int] = None
    total_subscription: Optional[float] = None
    qib_subscription: Optional[float] = None
    retail_subscription: Optional[float] = None
    open_date: Optional[datetime.date] = None
    closing_date: Optional[datetime.date] = None
    listing_date: Optional[datetime.date] = None
    listing_on: Optional[IpoListingOn] = None


class IpoUpdate(BaseModel):
    name: Optional[str] = None
    symbol: Optional[str] = None
    bse_symbol: Optional[str] = None
    board: Optional[IpoBoard] = None
    ipo_price: Optional[float] = None
    listing_price: Optional[float] = None
    lot_size: Optional[int] = None
    total_subscription: Optional[float] = None
    qib_subscription: Optional[float] = None
    retail_subscription: Optional[float] = None
    open_date: Optional[datetime.date] = None
    closing_date: Optional[datetime.date] = None
    listing_date: Optional[datetime.date] = None
    listing_on: Optional[IpoListingOn] = None


def _listing_gain_pct(ipo_price: Optional[float], listing_price: Optional[float]) -> Optional[float]:
    if ipo_price is None or listing_price is None:
        return None
    if ipo_price <= 0:
        return None
    return ((listing_price - ipo_price) / ipo_price) * 100.0


def _ist_now() -> datetime.datetime:
    return datetime.datetime.now(ZoneInfo("Asia/Kolkata"))


def _is_market_hours_ist(now: Optional[datetime.datetime] = None) -> bool:
    now = now or _ist_now()
    if now.weekday() >= 5:
        return False
    t = now.time()
    return dtime(9, 15) <= t < dtime(15, 30)


def _after_close_ist(now: Optional[datetime.datetime] = None) -> bool:
    now = now or _ist_now()
    if now.weekday() >= 5:
        return True
    return now.time() >= dtime(16, 0)


def _age_str(listing_date: Optional[datetime.date], today: Optional[datetime.date] = None) -> Optional[str]:
    if not listing_date:
        return None
    today = today or datetime.datetime.utcnow().date()
    months = (today.year - listing_date.year) * 12 + (today.month - listing_date.month)
    if today.day < listing_date.day:
        months -= 1
    if months < 0:
        return None
    years = months // 12
    rem = months % 12
    if years and rem:
        return f"{years}y {rem}m"
    if years:
        return f"{years}y"
    return f"{rem}m"


def refresh_ipo_daily_metrics(session: Session, for_date: Optional[datetime.date] = None) -> dict:
    now_ist = _ist_now()
    for_date = for_date or now_ist.date()

    ipos_ = session.exec(select(IPO)).all()
    symbols = [str(i.symbol or "").strip().upper() for i in ipos_ if str(i.symbol or "").strip()]
    symbols = list(dict.fromkeys(symbols))

    done = 0
    for sym in symbols:
        try:
            df = get_ohlc(sym, days=260, append_live=False)
            if df is None or df.empty:
                continue
            df2 = df[['open', 'high', 'low', 'close']].dropna().copy()
            if df2.empty or len(df2) < 120:
                continue

            q = get_latest_and_prev_close(sym)
            last_q = q.get("last")
            if last_q is not None:
                try:
                    last_qf = float(last_q)
                    i = df2.index[-1]
                    df2.loc[i, "close"] = last_qf
                    df2.loc[i, "open"] = last_qf
                    df2.loc[i, "high"] = max(float(df2.loc[i, "high"]), last_qf)
                    df2.loc[i, "low"] = min(float(df2.loc[i, "low"]), last_qf)
                except Exception:
                    pass

            close = df2['close'].astype(float)
            last_close = float(close.iloc[-1])
            e21 = ema_series(close, 21).iloc[-1]
            e50 = ema_series(close, 50).iloc[-1]
            e100 = ema_series(close, 100).iloc[-1]
            st_up = supertrend_direction(df2, period=8, multiplier=3.2)

            row = session.exec(
                select(IpoDailyMetrics).where(IpoDailyMetrics.symbol == sym, IpoDailyMetrics.for_date == for_date)
            ).first()
            if not row:
                row = IpoDailyMetrics(symbol=sym, for_date=for_date)

            row.close = last_close
            row.ema21 = float(e21) if e21 == e21 else None
            row.ema50 = float(e50) if e50 == e50 else None
            row.ema100 = float(e100) if e100 == e100 else None
            row.above_ema21 = bool(last_close >= float(e21)) if e21 == e21 else None
            row.above_ema50 = bool(last_close >= float(e50)) if e50 == e50 else None
            row.above_ema100 = bool(last_close >= float(e100)) if e100 == e100 else None
            row.supertrend_10_3_up = st_up
            row.computed_at = datetime.datetime.utcnow()

            session.add(row)
            session.commit()
            done += 1
        except Exception:
            continue

    return {"ok": True, "for_date": str(for_date), "symbols": len(symbols), "updated": done}


@router.get("/")
def list_ipos(include_prices: bool = True, session: Session = Depends(get_session), user=Depends(get_current_user)):
    ipos_ = session.exec(select(IPO)).all()

    now_ist = _ist_now()
    today_ist = now_ist.date()
    today_utc = datetime.datetime.utcnow().date()

    upcoming: list[IPO] = []
    past: list[IPO] = []

    for x in ipos_:
        ld = x.listing_date
        if ld and ld <= today_ist:
            past.append(x)
        else:
            upcoming.append(x)

    def next_event_date(x: IPO) -> datetime.date:
        for d in (x.open_date, x.closing_date, x.listing_date):
            if d and d >= today_ist:
                return d
        return x.open_date or x.closing_date or x.listing_date or datetime.date.max

    def upcoming_key(x: IPO):
        d = next_event_date(x)
        return (
            d,
            x.open_date or datetime.date.max,
            x.closing_date or datetime.date.max,
            x.listing_date or datetime.date.max,
            (x.name or ""),
            x.id or 0,
        )

    def past_key(x: IPO):
        d = x.listing_date or x.open_date or x.closing_date or datetime.date.min
        return (
            -d.toordinal(),
            (x.name or ""),
            x.id or 0,
        )

    rows_sorted = sorted(upcoming, key=upcoming_key) + sorted(past, key=past_key)

    # Latest daily metrics per symbol
    metrics_rows = session.exec(select(IpoDailyMetrics).order_by(IpoDailyMetrics.for_date.desc())).all()
    metrics_map: dict[str, IpoDailyMetrics] = {}
    for m in metrics_rows:
        if m.symbol and m.symbol not in metrics_map:
            metrics_map[m.symbol] = m

    # Cached quotes
    quote_rows = session.exec(select(IpoQuote)).all()
    quote_map: dict[str, IpoQuote] = {q.symbol: q for q in quote_rows if q.symbol}

    # User tags
    ipo_ids = [r.id for r in rows_sorted if r.id is not None]
    tag_rows = session.exec(select(IpoUserTag).where(IpoUserTag.user_id == user.id, IpoUserTag.ipo_id.in_(ipo_ids))).all() if ipo_ids else []
    tag_map: dict[int, IpoUserTag] = {t.ipo_id: t for t in tag_rows if t.ipo_id is not None}

    out = []
    for r in rows_sorted:
        sym = (r.symbol or "").strip().upper()
        m = metrics_map.get(sym)
        qrow = quote_map.get(sym)
        tag = tag_map.get(int(r.id)) if r.id is not None else None

        cur = None
        # After close: prefer today's computed close (stable EOD)
        if include_prices and sym and _after_close_ist(now_ist) and m and m.for_date == now_ist.date() and m.close is not None:
            cur = m.close
        elif include_prices and sym and qrow and qrow.last is not None:
            # Use cached quote if present
            cur = qrow.last
        # If quote is missing, we leave current_price as None and let the user/admin
        # update quotes on-demand during market hours.

        gain = _listing_gain_pct(r.ipo_price, r.listing_price)

        out.append({
            "id": r.id,
            "name": r.name,
            "symbol": r.symbol,
            "bse_symbol": r.bse_symbol,
            "color": (tag.color if tag else IpoRowColor.none),
            "board": r.board,
            "ipo_price": r.ipo_price,
            "listing_price": r.listing_price,
            "lot_size": r.lot_size,
            "listing_gain_pct": gain,
            "current_price": cur,
            "st": m.supertrend_10_3_up if m else None,
            "e21": m.above_ema21 if m else None,
            "e50": m.above_ema50 if m else None,
            "e100": m.above_ema100 if m else None,
            "metrics_date": str(m.for_date) if m and m.for_date else None,
            "age": _age_str(r.listing_date, today_utc),
            "total_subscription": r.total_subscription,
            "qib_subscription": r.qib_subscription,
            "retail_subscription": r.retail_subscription,
            "open_date": str(r.open_date) if r.open_date else None,
            "closing_date": str(r.closing_date) if r.closing_date else None,
            "listing_date": str(r.listing_date) if r.listing_date else None,
            "listing_on": r.listing_on,
            "created_at": r.created_at,
            "updated_at": r.updated_at,
        })

    return out


class PriceUpdateRequest(BaseModel):
    symbols: Optional[List[str]] = None


class IpoColorUpdate(BaseModel):
    color: IpoRowColor


@router.post("/metrics/run")
def run_metrics_now(session: Session = Depends(get_session), user=Depends(require_admin)):
    return refresh_ipo_daily_metrics(session)


@router.get("/metrics/alerts")
def ipo_metrics_alerts(session: Session = Depends(get_session), user=Depends(require_admin)):
    now_ist = _ist_now()
    today_ist = now_ist.date()
    window_start = today_ist - datetime.timedelta(days=14)

    ipos_ = session.exec(select(IPO)).all()
    ipo_map: dict[str, IPO] = {}
    for r in ipos_:
        sym = (r.symbol or "").strip().upper()
        if sym:
            ipo_map[sym] = r

    metrics_rows = session.exec(
        select(IpoDailyMetrics)
        .where(IpoDailyMetrics.for_date >= window_start)
        .order_by(IpoDailyMetrics.for_date.desc())
    ).all()

    if not metrics_rows:
        return {
            "as_of": None,
            "st_same_5d": [],
            "above_ema": {"date": None, "all": [], "e21": [], "e50": [], "e100": []},
            "score_upgrades": {"date": None, "items": []},
        }

    dates = sorted({m.for_date for m in metrics_rows if m.for_date is not None}, reverse=True)
    if not dates:
        return {
            "as_of": None,
            "st_same_5d": [],
            "above_ema": {"date": None, "all": [], "e21": [], "e50": [], "e100": []},
            "score_upgrades": {"date": None, "items": []},
        }

    max_date = dates[0]
    prev_date = dates[1] if len(dates) > 1 else None

    by_sym: dict[str, list[IpoDailyMetrics]] = {}
    for m in metrics_rows:
        sym = (m.symbol or "").strip().upper()
        if not sym:
            continue
        by_sym.setdefault(sym, []).append(m)

    for sym, rows in by_sym.items():
        rows.sort(key=lambda x: (x.for_date or datetime.date.min), reverse=True)

    def todays_row(sym: str) -> Optional[IpoDailyMetrics]:
        rows = by_sym.get(sym) or []
        for r in rows:
            if r.for_date == max_date:
                return r
        return None

    def _is_above(close: Optional[float], ema: Optional[float]) -> bool:
        if close is None or ema is None:
            return False
        try:
            return float(close) >= float(ema)
        except Exception:
            return False

    st_same_5d = []

    def _st_same_5(sym: str, rows: list[IpoDailyMetrics], anchor_date: datetime.date):
        xs = [r for r in rows if r.supertrend_10_3_up is not None and r.for_date is not None and r.for_date <= anchor_date]
        if len(xs) >= 5:
            xs5 = xs[:5]
            v0 = bool(xs5[0].supertrend_10_3_up)
            if all(bool(r.supertrend_10_3_up) == v0 for r in xs5):
                return {"ok": True, "st_up": v0, "dates": [str(r.for_date) for r in xs5 if r.for_date]}
            return {"ok": False}

        df = get_ohlc(sym, days=260, append_live=False)
        if df is None or df.empty:
            return {"ok": False}
        df2 = df[['high', 'low', 'close']].dropna().copy()
        s = supertrend_direction_series(df2, period=8, multiplier=3.2)
        if s is None or s.empty:
            return {"ok": False}

        try:
            s2 = s.loc[s.index.date <= anchor_date]
        except Exception:
            s2 = s

        if s2 is None or s2.empty or len(s2) < 5:
            return {"ok": False}

        last5 = s2.tail(5)
        v0 = bool(last5.iloc[0])
        if all(bool(x) == v0 for x in last5.tolist()):
            dates = []
            try:
                dates = [str(d.date()) if hasattr(d, 'date') else str(d) for d in last5.index.tolist()]
            except Exception:
                dates = []
            return {"ok": True, "st_up": v0, "dates": dates}
        return {"ok": False}

    for sym, rows in by_sym.items():
        res = _st_same_5(sym, rows, max_date)
        if not res.get("ok"):
            continue

        is_new = False
        if prev_date and bool(res.get("st_up")) is True:
            prev = _st_same_5(sym, rows, prev_date)
            was_up = bool(prev.get("ok")) and bool(prev.get("st_up")) is True
            is_new = not was_up

        ipo = ipo_map.get(sym)
        st_same_5d.append({
            "symbol": sym,
            "name": (ipo.name if ipo else sym),
            "st_up": bool(res.get("st_up")),
            "dates": res.get("dates") or [],
            "is_new": bool(is_new),
        })

    above_all = []
    above_e21 = []
    above_e50 = []
    above_e100 = []

    prev_above_all: set[str] = set()
    if prev_date is not None:
        for sym in sorted(by_sym.keys()):
            r = None
            for rr in (by_sym.get(sym) or []):
                if rr.for_date == prev_date:
                    r = rr
                    break
            if not r:
                continue
            b21 = _is_above(r.close, r.ema21)
            b50 = _is_above(r.close, r.ema50)
            b100 = _is_above(r.close, r.ema100)
            if b21 and b50 and b100:
                prev_above_all.add(sym)

    for sym in sorted(by_sym.keys()):
        r = todays_row(sym)
        if not r:
            continue
        ipo = ipo_map.get(sym)
        name = (ipo.name if ipo else sym)

        b21 = _is_above(r.close, r.ema21)
        b50 = _is_above(r.close, r.ema50)
        b100 = _is_above(r.close, r.ema100)

        if b21:
            above_e21.append({"symbol": sym, "name": name})
        if b50:
            above_e50.append({"symbol": sym, "name": name})
        if b100:
            above_e100.append({"symbol": sym, "name": name})
        if b21 and b50 and b100:
            above_all.append({
                "symbol": sym,
                "name": name,
                "is_new": bool(prev_date is not None and sym not in prev_above_all),
            })

    def score_for(m: IpoDailyMetrics, ipo: Optional[IPO]) -> int:
        st = bool(m.supertrend_10_3_up) if m.supertrend_10_3_up is not None else False
        e21 = _is_above(m.close, m.ema21)
        e50 = _is_above(m.close, m.ema50)
        e100 = _is_above(m.close, m.ema100)
        close = m.close

        above_listing = False
        above_ipo = False
        if close is not None and ipo is not None:
            if ipo.listing_price is not None:
                above_listing = bool(close >= float(ipo.listing_price))
            if ipo.ipo_price is not None:
                above_ipo = bool(close >= float(ipo.ipo_price))

        return (1 if st else 0) + (1 if e21 else 0) + (1 if e50 else 0) + (1 if e100 else 0) + (1 if above_listing else 0) + (1 if above_ipo else 0)

    upgrades = []
    allowed = {(4, 5), (4, 6), (5, 6)}

    for sym, rows in by_sym.items():
        if len(rows) < 2:
            continue
        latest = rows[0]
        prev = None
        for r in rows[1:]:
            if latest.for_date and r.for_date and r.for_date < latest.for_date:
                prev = r
                break
        if not prev:
            continue
        if not latest.for_date or not prev.for_date:
            continue

        ipo = ipo_map.get(sym)
        s0 = score_for(prev, ipo)
        s1 = score_for(latest, ipo)
        if (s0, s1) not in allowed:
            continue

        upgrades.append({
            "symbol": sym,
            "name": (ipo.name if ipo else sym),
            "from_score": s0,
            "to_score": s1,
            "prev_date": str(prev.for_date),
            "cur_date": str(latest.for_date),
        })

    upgrades.sort(key=lambda x: (-(x.get("to_score") or 0), x.get("symbol") or ""))

    return {
        "as_of": str(max_date),
        "st_same_5d": st_same_5d,
        "above_ema": {
            "date": str(max_date),
            "all": above_all,
            "e21": above_e21,
            "e50": above_e50,
            "e100": above_e100,
        },
        "score_upgrades": {
            "date": str(max_date),
            "items": upgrades,
        },
    }


@router.put("/{ipo_id}/color")
def set_ipo_color(ipo_id: int, data: IpoColorUpdate, session: Session = Depends(get_session), user=Depends(get_current_user)):
    ipo = session.get(IPO, ipo_id)
    if not ipo:
        raise HTTPException(status_code=404, detail="IPO not found")

    tag = session.exec(select(IpoUserTag).where(IpoUserTag.user_id == user.id, IpoUserTag.ipo_id == ipo_id)).first()
    if not tag:
        tag = IpoUserTag(user_id=user.id, ipo_id=ipo_id, color=data.color)
    else:
        tag.color = data.color
        tag.updated_at = datetime.datetime.utcnow()

    session.add(tag)
    session.commit()
    return {"ok": True}


@router.post("/prices/update")
def update_prices(data: PriceUpdateRequest, session: Session = Depends(get_session), user=Depends(get_current_user)):
    # Allow on-demand quote refresh outside market hours too (useful on weekends).
    now_ist = _ist_now()

    if data.symbols:
        syms = [s.strip().upper() for s in data.symbols if str(s or '').strip()]
    else:
        syms = [str(i.symbol or '').strip().upper() for i in session.exec(select(IPO.symbol)).all() if str(i or '').strip()]

    syms = list(dict.fromkeys(syms))[:120]

    now_utc = datetime.datetime.utcnow()
    updated = 0
    prices = {}

    existing = session.exec(select(IpoQuote).where(IpoQuote.symbol.in_(syms))).all() if syms else []
    qmap = {q.symbol: q for q in existing if q.symbol}

    for sym in syms:
        q = get_latest_and_prev_close(sym)
        last = q.get('last')
        if last is None:
            continue
        try:
            lastf = float(last)
        except Exception:
            continue

        row = qmap.get(sym)
        if not row:
            row = IpoQuote(symbol=sym)
        row.last = lastf
        row.fetched_at = now_utc
        session.add(row)
        prices[sym] = lastf
        updated += 1

    session.commit()
    return {"ok": True, "updated": updated, "prices": prices}


@router.get("/technicals")
def get_ipo_technicals(symbols: str, debug: bool = False, session: Session = Depends(get_session), user=Depends(get_current_user)):
    syms = [s.strip().upper() for s in (symbols or "").split(",") if s.strip()]
    syms = syms[:80]
    out = {}
    for sym in syms:
        try:
            df = get_ohlc(sym, days=260, append_live=True)
            if df is None or df.empty:
                out[sym] = {
                    "ok": False,
                    "above_ema21": None,
                    "above_ema50": None,
                    "above_ema100": None,
                    "supertrend_10_3_up": None,
                    **({"reason": "no_ohlc"} if debug else {}),
                }
                continue
            df2 = df[['open', 'high', 'low', 'close']].dropna().copy()
            if df2.empty or len(df2) < 120:
                out[sym] = {
                    "ok": False,
                    "above_ema21": None,
                    "above_ema50": None,
                    "above_ema100": None,
                    "supertrend_10_3_up": None,
                    **({"reason": "insufficient_history", "rows": int(len(df2))} if debug else {}),
                }
                continue
            # Use the latest quote for calculations (even outside market hours)
            q = get_latest_and_prev_close(sym)
            last_q = q.get("last")
            if last_q is not None:
                try:
                    last_qf = float(last_q)
                    i = df2.index[-1]
                    df2.loc[i, "close"] = last_qf
                    df2.loc[i, "open"] = last_qf
                    df2.loc[i, "high"] = max(float(df2.loc[i, "high"]), last_qf)
                    df2.loc[i, "low"] = min(float(df2.loc[i, "low"]), last_qf)
                except Exception:
                    pass

            close = df2['close'].astype(float)
            last_close = float(close.iloc[-1])
            e21 = ema_series(close, 21).iloc[-1]
            e50 = ema_series(close, 50).iloc[-1]
            e100 = ema_series(close, 100).iloc[-1]
            st_up = supertrend_direction(df2, period=8, multiplier=3.2)
            out[sym] = {
                "ok": True,
                "close": last_close,
                "ema21": float(e21) if e21 == e21 else None,
                "ema50": float(e50) if e50 == e50 else None,
                "ema100": float(e100) if e100 == e100 else None,
                "above_ema21": bool(last_close >= float(e21)) if e21 == e21 else None,
                "above_ema50": bool(last_close >= float(e50)) if e50 == e50 else None,
                "above_ema100": bool(last_close >= float(e100)) if e100 == e100 else None,
                "supertrend_10_3_up": st_up,
                **({"rows": int(len(df2)), "last_quote": float(last_q) if last_q is not None else None} if debug else {}),
            }
        except Exception as e:
            out[sym] = {
                "ok": False,
                "above_ema21": None,
                "above_ema50": None,
                "above_ema100": None,
                "supertrend_10_3_up": None,
                **({"reason": "exception", "error": str(e)} if debug else {}),
            }
    return out


@router.post("/", response_model=IPO)
def create_ipo(data: IpoCreate, session: Session = Depends(get_session), user=Depends(require_admin)):
    name = (data.name or "").strip()
    symbol = (data.symbol or "").strip().upper()
    if not name:
        raise HTTPException(status_code=400, detail="Name is required")
    if not symbol:
        raise HTTPException(status_code=400, detail="Symbol is required")

    exists = session.exec(select(IPO).where(IPO.symbol == symbol)).first()
    if exists:
        raise HTTPException(status_code=400, detail="IPO already exists")

    now = datetime.datetime.utcnow()
    row = IPO(
        name=name,
        symbol=symbol,
        bse_symbol=(data.bse_symbol.strip() if isinstance(data.bse_symbol, str) and data.bse_symbol.strip() else None),
        board=data.board,
        ipo_price=data.ipo_price,
        listing_price=data.listing_price,
        lot_size=data.lot_size,
        total_subscription=data.total_subscription,
        qib_subscription=data.qib_subscription,
        retail_subscription=data.retail_subscription,
        open_date=data.open_date,
        closing_date=data.closing_date,
        listing_date=data.listing_date,
        listing_on=data.listing_on,
        created_at=now,
        updated_at=now,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


@router.patch("/{ipo_id}", response_model=IPO)
def update_ipo(ipo_id: int, data: IpoUpdate, session: Session = Depends(get_session), user=Depends(require_admin)):
    row = session.get(IPO, ipo_id)
    if not row:
        raise HTTPException(status_code=404, detail="IPO not found")

    fields_set = getattr(data, "__fields_set__", set())

    if "name" in fields_set:
        name = (data.name or "").strip()
        if not name:
            raise HTTPException(status_code=400, detail="Name is required")
        row.name = name

    if "symbol" in fields_set:
        sym = (data.symbol or "").strip().upper()
        if not sym:
            raise HTTPException(status_code=400, detail="Symbol is required")
        exists = session.exec(select(IPO).where(IPO.symbol == sym, IPO.id != row.id)).first()
        if exists:
            raise HTTPException(status_code=400, detail="Symbol already exists")
        row.symbol = sym

    if "bse_symbol" in fields_set:
        row.bse_symbol = (data.bse_symbol.strip() if isinstance(data.bse_symbol, str) and data.bse_symbol.strip() else None)

    if "board" in fields_set:
        row.board = data.board or IpoBoard.mainboard

    for k in (
        "ipo_price",
        "listing_price",
        "lot_size",
        "total_subscription",
        "qib_subscription",
        "retail_subscription",
        "open_date",
        "closing_date",
        "listing_date",
        "listing_on",
    ):
        if k in fields_set:
            setattr(row, k, getattr(data, k))

    row.updated_at = datetime.datetime.utcnow()
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


@router.delete("/{ipo_id}")
def delete_ipo(ipo_id: int, session: Session = Depends(get_session), user=Depends(require_admin)):
    row = session.get(IPO, ipo_id)
    if not row:
        raise HTTPException(status_code=404, detail="IPO not found")
    session.delete(row)
    session.commit()
    return {"status": "deleted"}
