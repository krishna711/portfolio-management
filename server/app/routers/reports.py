from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from ..db import get_session
from ..models import Account, Holding, Strategy, Transaction, TransactionType
from ..security import get_current_user


router = APIRouter(prefix="/reports", tags=["reports"])


def _enum_value(v: Any) -> Any:
    try:
        return getattr(v, "value")
    except Exception:
        return v


def _ist_today() -> date:
    return datetime.now(ZoneInfo("Asia/Kolkata")).date()


def _financial_year_bounds(start_year: int) -> tuple[date, date]:
    # Indian FY: 1 April -> 31 March
    return date(start_year, 4, 1), date(start_year + 1, 3, 31)


@router.get("/financial_year")
def financial_year_report(
    start_year: Optional[int] = None,
    session: Session = Depends(get_session),
    user=Depends(get_current_user),
) -> Dict[str, Any]:
    today = _ist_today()
    if start_year is None:
        start_year = today.year if today.month >= 4 else today.year - 1

    fy_start, fy_end = _financial_year_bounds(int(start_year))

    # Load user's accounts for auth + names
    accounts = session.exec(select(Account).where(Account.user_id == user.id)).all()
    account_map = {a.id: a for a in accounts if a.id is not None}
    account_ids = list(account_map.keys())

    if not account_ids:
        return {
            "financial_year": f"{start_year}-{start_year + 1}",
            "start_year": int(start_year),
            "start_date": fy_start.isoformat(),
            "end_date": fy_end.isoformat(),
            "total_realized_profit": 0.0,
            "accounts": [],
            "trades": [],
        }

    strategies = session.exec(select(Strategy).where(Strategy.user_id == user.id)).all()
    strategy_name = {s.id: s.name for s in strategies if s.id is not None}

    rows = session.exec(
        select(Transaction, Holding, Account)
        .join(Holding, Transaction.holding_id == Holding.id)
        .join(Account, Holding.account_id == Account.id)
        .where(
            Account.user_id == user.id,
            Transaction.transaction_date <= fy_end,
        )
        .order_by(Transaction.transaction_date, Transaction.id)
    ).all()

    trades: List[Dict[str, Any]] = []
    realized_by_account: Dict[int, float] = {aid: 0.0 for aid in account_ids}
    trade_count_by_account: Dict[int, int] = {aid: 0 for aid in account_ids}
    total_realized = 0.0

    # holding_id -> position state (average cost method)
    pos: Dict[int, Dict[str, Any]] = {}

    for t, h, a in rows:
        hid = int(h.id) if h.id is not None else None
        aid = int(a.id) if a.id is not None else None
        if hid is None or aid is None:
            continue

        st = pos.get(hid)
        if not st:
            st = {
                "qty": 0.0,
                "total_cost": 0.0,
                "avg_cost": 0.0,
                "entry_date": None,
                "entry_strategy_id": None,
                "entry_strategy": None,
                "entry_notes": None,
            }
            pos[hid] = st

        if t.transaction_type == TransactionType.BUY:
            if float(st.get("qty") or 0.0) <= 0:
                st["entry_date"] = t.transaction_date
                st["entry_strategy_id"] = getattr(t, "strategy_id", None)
                sid0 = st.get("entry_strategy_id")
                st["entry_strategy"] = strategy_name.get(sid0) if sid0 is not None else None
            if not st.get("entry_notes"):
                n = str(getattr(t, "notes", "") or "").strip()
                if n:
                    st["entry_notes"] = n
            st["total_cost"] = float(st.get("total_cost") or 0.0) + float(t.quantity) * float(t.price)
            st["qty"] = float(st.get("qty") or 0.0) + float(t.quantity)
            q = float(st.get("qty") or 0.0)
            st["avg_cost"] = (float(st.get("total_cost") or 0.0) / q) if q > 0 else 0.0
            continue

        # SELL
        avg_cost_before = float(st.get("avg_cost") or 0.0)
        realized = float(getattr(t, "realized_profit", 0.0) or 0.0)
        sell_date = t.transaction_date
        sell_qty = float(t.quantity)
        investment = avg_cost_before * sell_qty
        if fy_start <= sell_date <= fy_end:
            entry_date = st.get("entry_date")
            holding_days = None
            try:
                if isinstance(entry_date, date):
                    holding_days = int((sell_date - entry_date).days)
            except Exception:
                holding_days = None

            entry_sid = st.get("entry_strategy_id")
            entry_sname = st.get("entry_strategy")
            if entry_sid is None:
                entry_sid = getattr(t, "strategy_id", None)
            if not entry_sname and entry_sid is not None:
                entry_sname = strategy_name.get(entry_sid)

            trades.append(
                {
                    "transaction_id": int(t.id) if t.id is not None else None,
                    "account_id": int(aid),
                    "account_name": a.name,
                    "broker": _enum_value(getattr(a, "broker", None)) if getattr(a, "broker", None) is not None else None,
                    "holding_id": int(hid),
                    "symbol": h.symbol,
                    "buy_date": entry_date.isoformat() if isinstance(entry_date, date) else None,
                    "sell_date": sell_date.isoformat() if isinstance(sell_date, date) else None,
                    "holding_days": holding_days,
                    "quantity": sell_qty,
                    "price": round(float(t.price), 2),
                    "sell_value": round(float(t.total), 2),
                    "investment": round(float(investment), 2),
                    "realized_profit": round(float(realized), 2),
                    "strategy_id": int(entry_sid) if entry_sid is not None else None,
                    "strategy": entry_sname,
                    "notes": st.get("entry_notes"),
                }
            )
            realized_by_account[aid] = float(realized_by_account.get(aid, 0.0)) + float(realized)
            trade_count_by_account[aid] = int(trade_count_by_account.get(aid, 0)) + 1
            total_realized += float(realized)

        # Update position using avg cost method
        st["qty"] = float(st.get("qty") or 0.0) - sell_qty
        st["total_cost"] = float(st.get("total_cost") or 0.0) - avg_cost_before * sell_qty
        if float(st.get("qty") or 0.0) <= 1e-9:
            st["qty"] = 0.0
            st["total_cost"] = 0.0
            st["avg_cost"] = 0.0
            st["entry_date"] = None
            st["entry_strategy_id"] = None
            st["entry_strategy"] = None
            st["entry_notes"] = None
        else:
            q = float(st.get("qty") or 0.0)
            st["avg_cost"] = (float(st.get("total_cost") or 0.0) / q) if q > 0 else 0.0

    acct_payload = []
    for aid in account_ids:
        a = account_map.get(aid)
        if not a:
            continue
        acct_payload.append(
            {
                "account_id": int(aid),
                "account_name": a.name,
                "broker": _enum_value(getattr(a, "broker", None)) if getattr(a, "broker", None) is not None else None,
                "trades": int(trade_count_by_account.get(aid, 0)),
                "realized_profit": round(float(realized_by_account.get(aid, 0.0)), 2),
            }
        )

    acct_payload.sort(key=lambda x: str(x.get("account_name") or ""))

    return {
        "financial_year": f"{start_year}-{start_year + 1}",
        "start_year": int(start_year),
        "start_date": fy_start.isoformat(),
        "end_date": fy_end.isoformat(),
        "total_realized_profit": round(float(total_realized), 2),
        "accounts": acct_payload,
        "trades": trades,
    }
