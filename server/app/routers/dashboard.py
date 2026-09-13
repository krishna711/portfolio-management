from typing import Optional, Any, Callable, Dict
from concurrent.futures import ThreadPoolExecutor
import logging
import threading
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Depends
from sqlmodel import Session
from sqlmodel import Session as SQLSession
from ..db import get_session
from ..db import engine
from ..security import get_current_user
from ..services.portfolio import (
    portfolio_summary,
    account_breakdown,
    equity_curve,
    holdings_pl,
    holding_chart,
    active_holdings_charts,
    get_agg_cache_entry,
)


router = APIRouter(prefix="/dashboard", tags=["dashboard"])


_EXECUTOR = ThreadPoolExecutor(max_workers=4)
_REFRESH_LOCK = threading.Lock()
_REFRESHING: set[str] = set()

_log = logging.getLogger(__name__)


def _ist_now() -> datetime:
    return datetime.now(ZoneInfo("Asia/Kolkata"))


def _with_meta(
    payload: Dict[str, Any],
    status: str,
    *,
    cache_updated_at: datetime | None = None,
    cache_expiry: datetime | None = None,
) -> Dict[str, Any]:
    out = dict(payload or {})
    meta: Dict[str, Any] = {"status": status, "server_time": _ist_now().isoformat()}
    if isinstance(cache_updated_at, datetime):
        meta["cache_updated_at"] = cache_updated_at.isoformat()
    if isinstance(cache_expiry, datetime):
        meta["cache_expiry"] = cache_expiry.isoformat()
    out["_meta"] = meta
    return out


def _schedule_refresh(key: str, fn: Callable[[], None]) -> None:
    with _REFRESH_LOCK:
        if key in _REFRESHING:
            return
        _REFRESHING.add(key)

    def _run():
        try:
            fn()
        except Exception:
            _log.exception("dashboard refresh failed: %s", key)
        finally:
            with _REFRESH_LOCK:
                _REFRESHING.discard(key)

    _EXECUTOR.submit(_run)


def _cached_or_warm(
    *,
    cache_key: str,
    compute_fn: Callable[[], None],
    placeholder: Dict[str, Any],
) -> Dict[str, Any]:
    item = get_agg_cache_entry(cache_key)
    now = _ist_now()
    if isinstance(item, dict) and "value" in item and "expiry" in item:
        exp = item.get("expiry")
        upd = item.get("updated_at")
        val = item.get("value")
        if (
            isinstance(val, dict)
            and isinstance(val.get("dates"), list)
            and isinstance(val.get("values"), list)
            and len(val.get("dates")) == 0
            and cache_key.startswith("equity_curve:")
        ):
            _schedule_refresh(cache_key, compute_fn)
            return _with_meta(placeholder, "warming", cache_updated_at=upd, cache_expiry=exp)
        if (
            isinstance(val, dict)
            and cache_key.startswith("equity_curve:")
            and not isinstance(val.get("portfolio_values"), list)
        ):
            _schedule_refresh(cache_key, compute_fn)
            return _with_meta(placeholder, "warming", cache_updated_at=upd, cache_expiry=exp)
        if isinstance(exp, datetime) and exp > now:
            if isinstance(val, dict):
                return _with_meta(val, "hit", cache_updated_at=upd, cache_expiry=exp)
        if isinstance(val, dict):
            _schedule_refresh(cache_key, compute_fn)
            return _with_meta(val, "stale", cache_updated_at=upd, cache_expiry=exp if isinstance(exp, datetime) else None)
    _schedule_refresh(cache_key, compute_fn)
    return _with_meta(placeholder, "warming")


@router.get("/summary")
def get_summary(session: Session = Depends(get_session), user=Depends(get_current_user)):
    cache_key = f"summary:{user.id}"

    def compute():
        with SQLSession(engine) as s:
            portfolio_summary(s, user.id)

    placeholder = {
        "portfolio_value": None,
        "total_profit": None,
        "daily_change": None,
        "unrealized": None,
        "realized": None,
        "invested_value": None,
        "total_return_pct": None,
        "total_trades": 0,
        "active_trades": 0,
        "closed_trades": 0,
        "profitable_trades_pct": 0,
    }
    return _cached_or_warm(cache_key=cache_key, compute_fn=compute, placeholder=placeholder)


@router.get("/account_breakdown")
def get_account_breakdown(session: Session = Depends(get_session), user=Depends(get_current_user)):
    cache_key = f"account_breakdown:{user.id}"

    def compute():
        with SQLSession(engine) as s:
            account_breakdown(s, user.id)

    return _cached_or_warm(cache_key=cache_key, compute_fn=compute, placeholder={"accounts": []})


@router.get("/equity_curve")
def get_equity_curve(days: Optional[int] = 60, session: Session = Depends(get_session), user=Depends(get_current_user)):
    d = days or 60
    cache_key = f"equity_curve:{user.id}:{d}"

    def compute():
        with SQLSession(engine) as s:
            equity_curve(s, user.id, days=d)

    n = max(2, min(int(d), 180))
    today = _ist_now().date()
    placeholder_dates = [(today - timedelta(days=(n - 1 - i))).isoformat() for i in range(n)]
    return _cached_or_warm(
        cache_key=cache_key,
        compute_fn=compute,
        placeholder={
            "dates": placeholder_dates,
            "portfolio_values": [0.0] * len(placeholder_dates),
            "realized_values": [0.0] * len(placeholder_dates),
            "unrealized_values": [0.0] * len(placeholder_dates),
            "values": [0.0] * len(placeholder_dates),
        },
    )


@router.get("/holdings_pl")
def get_holdings_pl(session: Session = Depends(get_session), user=Depends(get_current_user)):
    cache_key = f"holdings_pl:{user.id}"

    def compute():
        with SQLSession(engine) as s:
            holdings_pl(s, user.id)

    return _cached_or_warm(cache_key=cache_key, compute_fn=compute, placeholder={"holdings": []})


@router.get("/holding_chart")
def get_holding_chart(holding_id: int, days: Optional[int] = 90, session: Session = Depends(get_session), user=Depends(get_current_user)):
    d = days or 90
    cache_key = f"holding_chart:{user.id}:{holding_id}:{d}"

    def compute():
        with SQLSession(engine) as s:
            holding_chart(s, user.id, holding_id=holding_id, days=d)

    placeholder = {
        "holding_id": holding_id,
        "symbol": "",
        "buy_price": 0.0,
        "dates": [],
        "ohlc": {},
        "bb": {},
    }
    return _cached_or_warm(cache_key=cache_key, compute_fn=compute, placeholder=placeholder)


@router.get("/active_holdings_charts")
def get_active_holdings_charts(days: Optional[int] = 90, session: Session = Depends(get_session), user=Depends(get_current_user)):
    d = days or 90
    cache_key = f"active_charts:{user.id}:{d}"

    def compute():
        with SQLSession(engine) as s:
            active_holdings_charts(s, user.id, days=d)

    return _cached_or_warm(cache_key=cache_key, compute_fn=compute, placeholder={"charts": []})
