from __future__ import annotations
from typing import Dict, List, Optional, Tuple
import os
import math
from datetime import datetime, date, timedelta, time as dtime
from zoneinfo import ZoneInfo
import re
import json
import html as htmlmod
from urllib.parse import unquote
import requests
from bs4 import BeautifulSoup
from sqlmodel import Session, select
from sqlalchemy.exc import IntegrityError
from ..models import ScreenerSnapshot, ScreenerRow
from .prices import get_ohlc, heikin_ashi, bollinger_bands, rsi_series

SCANNERS: Dict[str, Dict[str, str]] = {
    "ha-daily-buy-ipo": {"url": "https://chartink.com/screener/ha-daily-buy-ipo", "title": "HA Daily Buy IPO"},
    "ha-daily-buy-41": {"url": "https://chartink.com/screener/ha-daily-buy-41", "title": "HA Daily Buy 41"},
    "ha-daily-buy-nifty-50": {"url": "https://chartink.com/screener/ha-daily-buy-nifty-50", "title": "HA Daily Buy Nifty 50"},
}


def _ist_now() -> datetime:
    return datetime.now(ZoneInfo("Asia/Kolkata"))


def _is_weekend(d: date) -> bool:
    return d.weekday() >= 5


def _previous_business_day(d: date) -> date:
    cur = d
    while True:
        cur = cur - timedelta(days=1)
        if cur.weekday() < 5:
            return cur


def _target_for_date(now: Optional[datetime] = None) -> Tuple[date, bool]:
    now = now or _ist_now()
    d = now.date()
    if _is_weekend(d):
        return (_previous_business_day(d), False)
    if now.time() < dtime(17, 0):
        return (_previous_business_day(d), False)
    return (d, True)


def _clean_pct(text: str) -> Optional[float]:
    if text is None:
        return None
    s = re.sub(r"[^0-9.\-]", "", str(text))
    return float(s) if s else None


def _clean_price(text: str) -> Optional[float]:
    if text is None:
        return None
    s = re.sub(r"[^0-9.\-]", "", str(text))
    return float(s) if s else None


def _clean_volume(text: str) -> Optional[int]:
    if text is None:
        return None
    s = re.sub(r"[^0-9]", "", str(text))
    return int(s) if s else None


def _parse_chartink_table(html: str) -> List[dict]:
    soup = BeautifulSoup(html, "lxml")
    table = None
    for t in soup.find_all("table"):
        ths = [th.get_text(strip=True) for th in t.find_all("th")]
        if any("Stock Name" in h for h in ths) and any("Symbol" in h for h in ths):
            table = t
            break
    if table is None:
        return []
    body = table.find("tbody")
    if not body:
        return []
    rows: List[dict] = []
    for tr in body.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) < 7:
            continue
        sr_txt = tds[0].get_text(strip=True)
        name_el = tds[1]
        sym_el = tds[2]
        links_el = tds[3]
        chg_txt = tds[4].get_text(strip=True)
        price_txt = tds[5].get_text(strip=True)
        vol_txt = tds[6].get_text(strip=True)
        stock_name = name_el.get_text(strip=True) if name_el else None
        symbol = sym_el.get_text(strip=True) if sym_el else None
        # Extract P&F and F.A links
        pf_url = None
        fa_url = None
        if links_el:
            for a in links_el.find_all("a"):
                href = a.get("href") or ""
                title = (a.get("title") or a.get_text(strip=True) or "").lower()
                if href.startswith("/"):
                    href = f"https://chartink.com{href}"
                if "point" in title or "p&f" in title:
                    pf_url = href
                if "fundamental" in title or "f.a" in title:
                    fa_url = href
        rows.append({
            "sr": _clean_price(sr_txt),
            "stock_name": stock_name,
            "symbol": symbol,
            "pf_url": pf_url,
            "fa_url": fa_url,
            "chg_pct": _clean_pct(chg_txt),
            "price": _clean_price(price_txt),
            "volume": _clean_volume(vol_txt),
        })
    return rows


def _fetch_chartink(url: str, debug: bool = False, driver: Optional[str] = None) -> Tuple[List[dict], dict]:
    """Fetch screener results using Chartink's process endpoint.
    Steps:
      1) GET screener page -> obtain cookies and atlas_query and csrf token
      2) POST to /screener/process with scan_clause
      3) Normalize rows
      4) Fallback to HTML table parsing if JSON fails
    """
    dbg: dict = {"used_json_api": False, "json_rows": 0, "fallback_rows": 0, "got_token": False, "token_src": None, "atlas_query_len": 0}
    sess = requests.Session()
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Referer": url,
        "Accept-Language": "en-GB,en-US;q=0.9,en;q=0.8",
    }
    # Prime cookies from homepage to ensure ci_session is set
    try:
        home = sess.get("https://chartink.com", headers=headers, timeout=12)
        dbg["home_status"] = home.status_code
    except Exception:
        dbg["home_status"] = None
    r = sess.get(url, headers=headers, timeout=12)
    r.raise_for_status()
    html = r.text
    dbg["page_status"] = r.status_code
    # Try to get csrf token
    token = None
    try:
        soup = BeautifulSoup(html, "lxml")
        mt = soup.find('meta', attrs={'name': 'csrf-token'})
        if mt and mt.get('content'):
            token = mt.get('content')
    except Exception:
        token = None
    if not token:
        try:
            token = unquote(sess.cookies.get('XSRF-TOKEN') or '') or None
        except Exception:
            token = None
    if token:
        dbg.update({"got_token": True, "token_src": "meta_or_cookie"})
    # Capture cookie names for debugging
    try:
        cookie_names = list({c.name for c in sess.cookies if c.domain.endswith("chartink.com")})
        dbg["cookies"] = cookie_names
        dbg["has_ci_session"] = any(n.lower()=="ci_session" for n in cookie_names)
    except Exception:
        pass
    # Extract atlas_query from :scan-json binding on <scanner>
    atlas_query = None
    scan_id = None
    slug = None
    try:
        # Primary: use BeautifulSoup to grab :scan-json attribute
        sc = soup.find('scanner') if 'soup' in locals() and soup else None
        raw = None
        if sc:
            # bs4 may normalize attribute name without the leading ':'
            raw = sc.get(':scan-json') or sc.get('scan-json') or sc.get('data-scan-json')
        if not raw:
            # Regex fallback on attribute value, supporting double/single quotes and newlines
            m_attr = re.search(r':scan-json\s*=\s*"([\s\S]*?)"', html)
            if not m_attr:
                m_attr = re.search(r":scan-json\s*=\s*'([\s\S]*?)'", html)
            if m_attr:
                raw = m_attr.group(1)
        if raw:
            raw = htmlmod.unescape(raw)
            js = json.loads(raw)
            atlas_query = js.get('atlas_query')
            scan_id = js.get('id')
            slug = js.get('slug')
        # Last resort: look for atlas_query literal (with HTML entities) in the page text
        if not atlas_query:
            m = re.search(r'atlas_query\s*[:=]\s*\&quot;([\s\S]*?)\&quot;', html)
            if m:
                atlas_query = htmlmod.unescape(m.group(1))
    except Exception:
        atlas_query = None
    dbg.update({"found_attr": bool(atlas_query is not None), "scan_id": scan_id, "slug": slug})
    if atlas_query:
        dbg["atlas_query_len"] = len(atlas_query)
    # Try JSON API if we have token and atlas_query
    if token and atlas_query:
        try:
            post_headers = {
                "User-Agent": headers["User-Agent"],
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "X-Requested-With": "XMLHttpRequest",
                "X-CSRF-TOKEN": token,
                "X-XSRF-TOKEN": token,
                "Referer": url,
                "Origin": "https://chartink.com",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            }
            # Explicit Cookie header (defensive), in addition to Session cookies
            try:
                cookie_kv = []
                for c in sess.cookies:
                    if c.domain.endswith("chartink.com"):
                        cookie_kv.append(f"{c.name}={c.value}")
                if cookie_kv:
                    post_headers["Cookie"] = "; ".join(cookie_kv)
            except Exception:
                pass
            resp = sess.post("https://chartink.com/screener/process", headers=post_headers, data={"scan_clause": atlas_query}, timeout=20)
            resp.raise_for_status()
            js = resp.json()
            data = js.get('data') or []
            try:
                dbg["resp_keys"] = list(js.keys())
                if not data:
                    dbg["resp_msg"] = js.get('message') or js.get('error')
            except Exception:
                pass
            out: List[dict] = []
            for row in data:
                # Normalize
                chg = row.get('per_chg') or row.get('chng') or row.get('% Chg') or row.get('pchange')
                price = row.get('last_price') or row.get('price') or row.get('close')
                vol = row.get('volume') or row.get('vol')
                symbol = row.get('symbol') or row.get('nsecode') or row.get('Symbol')
                out.append({
                    "sr": row.get('n') or row.get('Sr.') or None,
                    "stock_name": row.get('name') or row.get('Stock Name') or None,
                    "symbol": symbol,
                    "pf_url": None,
                    "fa_url": None,
                    "chg_pct": float(chg) if chg not in (None, '') else None,
                    "price": float(price) if price not in (None, '') else None,
                    "volume": int(re.sub(r"[^0-9]", "", str(vol))) if vol not in (None, '') else None,
                })
            # If we got rows via JSON, return
            dbg.update({"used_json_api": True, "json_rows": len(out), "http_status": resp.status_code})
            if out:
                return (out, dbg if debug else {})
        except Exception:
            dbg.setdefault("error", "process_failed")
            # Retry once after priming cookies via GET
            try:
                prime = sess.get("https://chartink.com/screener/process", headers={"User-Agent": headers["User-Agent"], "Referer": url}, timeout=10)
                dbg["prime_status"] = prime.status_code
                resp = sess.post("https://chartink.com/screener/process", headers=post_headers, data={"scan_clause": atlas_query}, timeout=20)
                resp.raise_for_status()
                js = resp.json()
                data = js.get('data') or []
                out: List[dict] = []
                for row in data:
                    chg = row.get('per_chg') or row.get('chng') or row.get('% Chg') or row.get('pchange')
                    price = row.get('last_price') or row.get('price') or row.get('close')
                    vol = row.get('volume') or row.get('vol')
                    symbol = row.get('symbol') or row.get('nsecode') or row.get('Symbol')
                    out.append({
                        "sr": row.get('n') or row.get('Sr.') or None,
                        "stock_name": row.get('name') or row.get('Stock Name') or None,
                        "symbol": symbol,
                        "pf_url": None,
                        "fa_url": None,
                        "chg_pct": float(chg) if chg not in (None, '') else None,
                        "price": float(price) if price not in (None, '') else None,
                        "volume": int(re.sub(r"[^0-9]", "", str(vol))) if vol not in (None, '') else None,
                    })
                dbg.update({"used_json_api": True, "json_rows": len(out), "http_status": resp.status_code, "retry": True})
                if out:
                    return (out, dbg if debug else {})
            except Exception as e:
                dbg["retry_error"] = "process_retry_failed"
    # Alternate JSON API using scan_id when atlas_query not present
    if token and not atlas_query and scan_id:
        try:
            post_headers = {
                "User-Agent": headers["User-Agent"],
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "X-Requested-With": "XMLHttpRequest",
                "X-CSRF-TOKEN": token,
                "X-XSRF-TOKEN": token,
                "Referer": url,
                "Origin": "https://chartink.com",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            }
            resp = sess.post("https://chartink.com/screener/process", headers=post_headers, data={"scan_id": str(scan_id)}, timeout=20)
            resp.raise_for_status()
            js = resp.json()
            data = js.get('data') or []
            out: List[dict] = []
            for row in data:
                chg = row.get('per_chg') or row.get('chng') or row.get('% Chg') or row.get('pchange')
                price = row.get('last_price') or row.get('price') or row.get('close')
                vol = row.get('volume') or row.get('vol')
                symbol = row.get('symbol') or row.get('nsecode') or row.get('Symbol')
                out.append({
                    "sr": row.get('n') or row.get('Sr.') or None,
                    "stock_name": row.get('name') or row.get('Stock Name') or None,
                    "symbol": symbol,
                    "pf_url": None,
                    "fa_url": None,
                    "chg_pct": float(chg) if chg not in (None, '') else None,
                    "price": float(price) if price not in (None, '') else None,
                    "volume": int(re.sub(r"[^0-9]", "", str(vol))) if vol not in (None, '') else None,
                })
            dbg.update({"used_json_api": True, "used_scan_id": True, "json_rows": len(out), "http_status": resp.status_code})
            if out:
                return (out, dbg if debug else {})
        except Exception:
            dbg.setdefault("error", "process_id_failed")
    # Cloudflare bypass via cloudscraper when requested
    if token and atlas_query and (driver in ("cf", "cloudflare", "auto")):
        try:
            import cloudscraper  # type: ignore
            scraper = cloudscraper.create_scraper(browser={"browser": "chrome", "platform": "macos", "mobile": False})
            # Prime
            scraper.get("https://chartink.com", headers=headers, timeout=12)
            page = scraper.get(url, headers=headers, timeout=12)
            html2 = page.text
            token2 = None
            try:
                soup2 = BeautifulSoup(html2, "lxml")
                mt2 = soup2.find('meta', attrs={'name': 'csrf-token'})
                if mt2 and mt2.get('content'):
                    token2 = mt2.get('content')
            except Exception:
                token2 = None
            if not token2:
                try:
                    token2 = unquote(scraper.cookies.get('XSRF-TOKEN') or '') or None
                except Exception:
                    token2 = None
            post_headers_cs = {
                "User-Agent": headers["User-Agent"],
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "X-Requested-With": "XMLHttpRequest",
                "X-CSRF-TOKEN": token2 or token,
                "X-XSRF-TOKEN": token2 or token,
                "Referer": url,
                "Origin": "https://chartink.com",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "Accept-Language": headers["Accept-Language"],
            }
            rr = scraper.post("https://chartink.com/screener/process", headers=post_headers_cs, data={"scan_clause": atlas_query}, timeout=20)
            js3 = rr.json()
            data3 = js3.get('data') or []
            out3: List[dict] = []
            for row in data3:
                chg = row.get('per_chg') or row.get('chng') or row.get('% Chg') or row.get('pchange')
                price = row.get('last_price') or row.get('price') or row.get('close')
                vol = row.get('volume') or row.get('vol')
                symbol = row.get('symbol') or row.get('nsecode') or row.get('Symbol')
                out3.append({
                    "sr": row.get('n') or row.get('Sr.') or None,
                    "stock_name": row.get('name') or row.get('Stock Name') or None,
                    "symbol": symbol,
                    "pf_url": None,
                    "fa_url": None,
                    "chg_pct": float(chg) if chg not in (None, '') else None,
                    "price": float(price) if price not in (None, '') else None,
                    "volume": int(re.sub(r"[^0-9]", "", str(vol))) if vol not in (None, '') else None,
                })
            dbg.update({"cf_used": True, "cf_rows": len(out3), "cf_status": rr.status_code})
            if out3:
                return (out3, dbg if debug else {})
        except Exception:
            dbg.setdefault("cf_error", "cf_failed")
    # Fallback: parse static table (sometimes pre-rendered)
    try:
        rows = _parse_chartink_table(html)
        dbg["fallback_rows"] = len(rows)
        return (rows, dbg if debug else {})
    except Exception:
        return ([], dbg if debug else {})


def get_or_fetch_results(session: Session, key: str, force: bool = False, debug: bool = False, driver: Optional[str] = None, for_date_str: Optional[str] = None) -> dict:
    meta = SCANNERS.get(key)
    if not meta:
        return {"error": "unknown_scanner"}
    # If a specific date is requested, return snapshot for that day without refetching
    if for_date_str:
        try:
            y, m, d = [int(x) for x in str(for_date_str).split('-')]
            req_date = date(y, m, d)
        except Exception:
            req_date = None
        if req_date:
            snap_req = session.exec(select(ScreenerSnapshot).where(ScreenerSnapshot.scanner_key == key, ScreenerSnapshot.for_date == req_date)).first()
            if snap_req:
                rows_db = session.exec(select(ScreenerRow).where(ScreenerRow.snapshot_id == snap_req.id)).all()
                resp = {
                    "key": key, "title": meta["title"], "for_date": str(snap_req.for_date), "from_cache": True,
                    "rows": [row_as_dict(r) for r in rows_db],
                }
                if debug:
                    resp["debug"] = {"requested_date": str(req_date), "existing_rows": len(rows_db)}
                return resp
            return {"key": key, "title": meta["title"], "for_date": str(req_date), "from_cache": True, "rows": []}
    for_date, allow_fetch = _target_for_date()
    snap = session.exec(select(ScreenerSnapshot).where(ScreenerSnapshot.scanner_key == key, ScreenerSnapshot.for_date == for_date)).first()
    if snap and not force:
        rows_db = session.exec(select(ScreenerRow).where(ScreenerRow.snapshot_id == snap.id)).all()
        # Backfill once if after 5PM and snapshot is empty (possible earlier parse failure)
        if allow_fetch and not rows_db:
            try:
                fresh, dbg = _fetch_chartink(meta["url"], debug=debug, driver=driver)
            except Exception:
                fresh, dbg = [], {}
            try:
                symbols_added = set()
                for r in fresh:
                    sym = (r.get("symbol") or "").strip() or None
                    if sym in symbols_added:
                        continue
                    symbols_added.add(sym)
                    row = ScreenerRow(
                        snapshot_id=snap.id,
                        sr=int(r.get("sr") or 0) if r.get("sr") is not None else None,
                        stock_name=r.get("stock_name"),
                        symbol=sym,
                        pf_url=r.get("pf_url"),
                        fa_url=r.get("fa_url"),
                        chg_pct=float(r.get("chg_pct")) if r.get("chg_pct") is not None else None,
                        price=float(r.get("price")) if r.get("price") is not None else None,
                        volume=int(r.get("volume")) if r.get("volume") is not None else None,
                    )
                    session.add(row)
                session.commit()
            except IntegrityError:
                session.rollback()
            # refresh rows and update row_count
            rows_db = session.exec(select(ScreenerRow).where(ScreenerRow.snapshot_id == snap.id)).all()
            try:
                snap.row_count = len(rows_db)
                session.add(snap)
                session.commit()
            except Exception:
                session.rollback()
        resp = {
            "key": key, "title": meta["title"], "for_date": str(snap.for_date), "from_cache": True,
            "rows": [row_as_dict(r) for r in rows_db],
        }
        if debug:
            resp["debug"] = {"existing_rows": len(rows_db)}
        return resp
    # Not present or forced refresh
    if allow_fetch:
        try:
            rows, dbg = _fetch_chartink(meta["url"], debug=debug, driver=driver)
        except Exception:
            rows, dbg = [], {}
        if snap is None:
            # create a new snapshot for today
            snap = ScreenerSnapshot(scanner_key=key, for_date=for_date, row_count=len(rows))
            try:
                session.add(snap)
                session.commit()
                session.refresh(snap)
            except IntegrityError:
                session.rollback()
                snap = session.exec(select(ScreenerSnapshot).where(ScreenerSnapshot.scanner_key == key, ScreenerSnapshot.for_date == for_date)).first()
                if snap is None:
                    return {"key": key, "title": meta["title"], "for_date": str(for_date), "from_cache": True, "rows": []}
        else:
            # forced refresh: clear previous rows for this snapshot
            try:
                existing = session.exec(select(ScreenerRow).where(ScreenerRow.snapshot_id == snap.id)).all()
                for r in existing:
                    session.delete(r)
                session.commit()
            except Exception:
                session.rollback()
        # Insert rows for snapshot
        try:
            symbols_added = set()
            for r in rows:
                sym = (r.get("symbol") or "").strip() or None
                if sym in symbols_added:
                    continue
                symbols_added.add(sym)
                row = ScreenerRow(
                    snapshot_id=snap.id,
                    sr=int(r.get("sr") or 0) if r.get("sr") is not None else None,
                    stock_name=r.get("stock_name"),
                    symbol=sym,
                    pf_url=r.get("pf_url"),
                    fa_url=r.get("fa_url"),
                    chg_pct=float(r.get("chg_pct")) if r.get("chg_pct") is not None else None,
                    price=float(r.get("price")) if r.get("price") is not None else None,
                    volume=int(r.get("volume")) if r.get("volume") is not None else None,
                )
                session.add(row)
            session.commit()
        except IntegrityError:
            session.rollback()
        # update row_count to actual saved count
        try:
            saved = session.exec(select(ScreenerRow).where(ScreenerRow.snapshot_id == snap.id)).all()
            snap.row_count = len(saved)
            session.add(snap)
            session.commit()
        except Exception:
            session.rollback()
            saved = session.exec(select(ScreenerRow).where(ScreenerRow.snapshot_id == snap.id)).all()
        resp = {
            "key": key, "title": meta["title"], "for_date": str(for_date), "from_cache": False,
            "rows": [row_as_dict(r) for r in saved],
        }
        if debug:
            resp["debug"] = dbg
        return resp
    # Before 5PM or weekend: return latest existing snapshot if any
    latest = session.exec(select(ScreenerSnapshot).where(ScreenerSnapshot.scanner_key == key).order_by(ScreenerSnapshot.for_date.desc())).first()
    if latest:
        rows = session.exec(select(ScreenerRow).where(ScreenerRow.snapshot_id == latest.id)).all()
        resp = {
            "key": key, "title": meta["title"], "for_date": str(latest.for_date), "from_cache": True,
            "rows": [row_as_dict(r) for r in rows],
        }
        if debug:
            resp["debug"] = {"latest_rows": len(rows)}
        return resp
    return {"key": key, "title": meta["title"], "for_date": str(for_date), "from_cache": True, "rows": []}


def list_scanners(session: Session) -> dict:
    out = []
    for key, meta in SCANNERS.items():
        latest = session.exec(select(ScreenerSnapshot).where(ScreenerSnapshot.scanner_key == key).order_by(ScreenerSnapshot.for_date.desc())).first()
        out.append({
            "key": key, "title": meta["title"],
            "latest_for_date": str(latest.for_date) if latest else None,
            "latest_rows": latest.row_count if latest else 0,
        })
    return {"scanners": out}


def row_as_dict(r: ScreenerRow) -> dict:
    return {
        "sr": r.sr, "stock_name": r.stock_name, "symbol": r.symbol,
        "pf_url": r.pf_url, "fa_url": r.fa_url, "chg_pct": r.chg_pct, "price": r.price, "volume": r.volume,
    }


# ---- Screener utilities ----
def list_screener_dates(session: Session, key: str) -> dict:
    snaps = session.exec(
        select(ScreenerSnapshot)
        .where(ScreenerSnapshot.scanner_key == key)
        .order_by(ScreenerSnapshot.for_date.desc())
    ).all()
    return {"dates": [{"date": str(s.for_date), "rows": int(s.row_count or 0)} for s in snaps]}


def _get_trade_risk() -> float:
    try:
        return float(os.environ.get("TRADE_RISK", "1000"))
    except Exception:
        return 1000.0


def screener_stock_chart(session: Session, symbol: str, days: int = 90) -> dict:
    df = get_ohlc(symbol, days=days, append_live=True)
    if df is None or df.empty:
        return {"symbol": symbol, "dates": [], "ohlc": {}, "bb": {}, "buy_price": 0.0}
    df = df.sort_index()
    ha = heikin_ashi(df)
    bb = bollinger_bands(df['close'])
    rsi = rsi_series(df['close'])
    dates = [d.date().isoformat() for d in df.index]
    # Entry above today's high; SL = previous day's low
    if len(df) >= 2:
        prev = df.iloc[-2]
        today = df.iloc[-1]
    else:
        prev = df.iloc[-1]
        today = df.iloc[-1]
    # Base prices
    sl_price = float(prev['low'])
    entry = float(today['high'])
    # Apply scanner-only buffers: +0.03% on entry, -0.03% on SL
    buf_pct = 0.0003
    entry = entry * (1.0 + buf_pct)
    sl_price = sl_price * (1.0 - buf_pct)
    # Risk and targets using buffered prices
    risk_pts = max(entry - sl_price, 0.0)
    r1 = entry + risk_pts if risk_pts > 0 else None
    r2 = entry + 2 * risk_pts if risk_pts > 0 else None
    r3 = entry + 3 * risk_pts if risk_pts > 0 else None
    trade_risk = _get_trade_risk()
    raw_qty = round(trade_risk / risk_pts) if risk_pts > 0 else 0
    qty = int(math.floor(raw_qty / 2) * 2) if raw_qty > 0 else 0
    sl_pct = (risk_pts / entry * 100.0) if (entry and risk_pts > 0) else 0.0
    amount_required = float(qty) * float(entry)
    return {
        "symbol": symbol,
        "buy_price": round(float(entry), 2),
        "sl_price": round(float(sl_price), 2) if sl_price else 0.0,
        "r_levels": [round(float(x), 2) if x else None for x in [r1, r2, r3]],
        "sl_points": round(float(risk_pts), 2),
        "sl_pct": round(float(sl_pct), 2),
        "qty": qty,
        "amount_required": round(float(amount_required), 2),
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
