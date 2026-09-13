from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging
import threading
from datetime import datetime, timedelta, time as dtime
from zoneinfo import ZoneInfo
from sqlmodel import Session as SQLSession, select
from .config import settings
from .db import init_db
from .db import engine
from .models import User
from .routers import auth, accounts, holdings, transactions, dashboard, screeners, strategies, reports, ipos, prefs
from .services.portfolio import portfolio_summary, account_breakdown, holdings_pl, equity_curve, active_holdings_charts
from .services.screeners import SCANNERS, get_or_fetch_results


app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(accounts.router)
app.include_router(holdings.router)
app.include_router(transactions.router)
app.include_router(dashboard.router)
app.include_router(screeners.router)
app.include_router(strategies.router)
app.include_router(reports.router)
app.include_router(ipos.router)
app.include_router(prefs.router)


_log = logging.getLogger(__name__)


def _ist_now() -> datetime:
    return datetime.now(ZoneInfo("Asia/Kolkata"))


def _next_run_at(target_time: dtime, now: datetime | None = None) -> datetime:
    now = now or _ist_now()
    cur_date = now.date()
    candidate = datetime.combine(cur_date, target_time, tzinfo=ZoneInfo("Asia/Kolkata"))
    if candidate <= now:
        candidate = candidate + timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate = candidate + timedelta(days=1)
    return candidate


def _parse_hhmm(value: str, fallback: dtime) -> dtime:
    try:
        parts = str(value).strip().split(":")
        if len(parts) != 2:
            return fallback
        hh = int(parts[0])
        mm = int(parts[1])
        if hh < 0 or hh > 23 or mm < 0 or mm > 59:
            return fallback
        return dtime(hh, mm)
    except Exception:
        return fallback


def _warm_dashboard_for_all_users() -> None:
    try:
        with SQLSession(engine) as s:
            user_ids = [u for u in s.exec(select(User.id)).all() if u is not None]
            for uid in user_ids:
                try:
                    portfolio_summary(s, int(uid))
                    account_breakdown(s, int(uid))
                    holdings_pl(s, int(uid))
                    equity_curve(s, int(uid), days=60)
                    active_holdings_charts(s, int(uid), days=90)
                except Exception:
                    _log.exception("scheduler: dashboard warm failed for user_id=%s", uid)
    except Exception:
        _log.exception("scheduler: dashboard warm failed")


def _run_scanners_snapshot() -> None:
    try:
        with SQLSession(engine) as s:
            for key in list(SCANNERS.keys()):
                try:
                    get_or_fetch_results(s, key, force=False, debug=False, driver=None, for_date_str=None)
                except Exception:
                    _log.exception("scheduler: scanner failed key=%s", key)
    except Exception:
        _log.exception("scheduler: scanners run failed")


def _run_ipo_metrics_snapshot() -> None:
    try:
        with SQLSession(engine) as s:
            try:
                ipos.refresh_ipo_daily_metrics(s)
            except Exception:
                _log.exception("scheduler: ipo metrics refresh failed")
    except Exception:
        _log.exception("scheduler: ipo metrics run failed")


def _scheduler_loop(stop_event: threading.Event) -> None:
    dashboard_time = _parse_hhmm(settings.dashboard_warm_time, dtime(16, 5))
    scanners_time = _parse_hhmm(settings.scanners_warm_time, dtime(17, 5))
    ipo_time = _parse_hhmm(getattr(settings, "ipo_metrics_warm_time", "16:30"), dtime(16, 30))
    while not stop_event.is_set():
        now = _ist_now()
        next_dash = _next_run_at(dashboard_time, now)
        next_scan = _next_run_at(scanners_time, now)
        next_ipo = _next_run_at(ipo_time, now)
        next_run = min(next_dash, next_scan, next_ipo)
        sleep_s = max(1.0, (next_run - now).total_seconds())
        stop_event.wait(timeout=sleep_s)
        if stop_event.is_set():
            break
        now2 = _ist_now()
        if abs((now2 - next_dash).total_seconds()) < 90:
            _warm_dashboard_for_all_users()
        if abs((now2 - next_scan).total_seconds()) < 90:
            _run_scanners_snapshot()
        if abs((now2 - next_ipo).total_seconds()) < 90:
            _run_ipo_metrics_snapshot()


@app.on_event("startup")
def on_startup() -> None:
    init_db()
    if settings.enable_internal_scheduler:
        stop = threading.Event()
        app.state._scheduler_stop = stop
        t = threading.Thread(target=_scheduler_loop, args=(stop,), daemon=True)
        app.state._scheduler_thread = t
        t.start()


@app.on_event("shutdown")
def on_shutdown() -> None:
    stop = getattr(app.state, "_scheduler_stop", None)
    if isinstance(stop, threading.Event):
        stop.set()


@app.get("/")
def root():
    return {"status": "ok"}
