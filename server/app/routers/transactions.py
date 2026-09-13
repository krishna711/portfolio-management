from datetime import date, datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select
from ..db import get_session
from ..models import Account, Holding, Transaction, TransactionType, Strategy
from ..security import get_current_user
from ..services.portfolio import invalidate_user_cache


router = APIRouter(prefix="/transactions", tags=["transactions"])


class TransactionCreate(BaseModel):
    account_id: int
    symbol: str
    transaction_type: TransactionType
    quantity: float
    price: float
    transaction_date: Optional[date] = None
    strategy_id: Optional[int] = None
    notes: Optional[str] = None


class TransactionUpdate(BaseModel):
    transaction_type: Optional[TransactionType] = None
    quantity: Optional[float] = None
    price: Optional[float] = None
    transaction_date: Optional[date] = None
    strategy_id: Optional[int] = None
    notes: Optional[str] = None


def _get_default_strategy_id(session: Session, user_id: int) -> Optional[int]:
    s = session.exec(select(Strategy).where(Strategy.user_id == user_id, Strategy.name == "Swing")).first()
    if s:
        return s.id
    s = Strategy(user_id=user_id, name="Swing")
    session.add(s)
    session.flush()
    return s.id


@router.get("/", response_model=List[Transaction])
def list_transactions(account_id: Optional[int] = None, holding_id: Optional[int] = None, session: Session = Depends(get_session), user=Depends(get_current_user)):
    accounts = session.exec(select(Account).where(Account.user_id == user.id)).all()
    account_ids = [a.id for a in accounts]
    if account_id and account_id not in account_ids:
        return []
    holdings_query = select(Holding).where(Holding.account_id.in_([account_id] if account_id else account_ids))
    holdings = session.exec(holdings_query).all() if account_ids else []
    holding_ids = [h.id for h in holdings]
    if holding_id and holding_id in holding_ids:
        holding_ids = [holding_id]
    txns = session.exec(select(Transaction).where(Transaction.holding_id.in_(holding_ids))).all() if holding_ids else []
    return txns


@router.post("/", response_model=Transaction)
def create_transaction(data: TransactionCreate, session: Session = Depends(get_session), user=Depends(get_current_user)):
    account = session.get(Account, data.account_id)
    if not account or account.user_id != user.id:
        raise HTTPException(status_code=404, detail="Account not found")
    holding = session.exec(select(Holding).where(Holding.account_id == account.id, Holding.symbol == data.symbol)).first()
    if not holding:
        holding = Holding(account_id=account.id, symbol=data.symbol, quantity=0.0, average_price=0.0, total_cost=0.0)
        session.add(holding)
        session.flush()
    if data.transaction_type == TransactionType.BUY:
        new_total_cost = holding.total_cost + data.quantity * data.price
        new_quantity = holding.quantity + data.quantity
        new_avg = (new_total_cost / new_quantity) if new_quantity > 0 else 0.0
        holding.total_cost = new_total_cost
        holding.quantity = new_quantity
        holding.average_price = new_avg
        realized_profit = 0.0
    else:
        if data.quantity > holding.quantity:
            raise HTTPException(status_code=400, detail="Sell quantity exceeds holding quantity")
        realized_profit = (data.price - holding.average_price) * data.quantity
        holding.quantity = holding.quantity - data.quantity
        holding.total_cost = holding.total_cost - holding.average_price * data.quantity
        if holding.quantity == 0:
            holding.average_price = 0.0
            holding.total_cost = 0.0
    holding.updated_at = datetime.utcnow()
    txn_date = data.transaction_date or date.today()

    strategy_id: Optional[int] = None
    if data.strategy_id is not None:
        st = session.get(Strategy, data.strategy_id)
        if not st or st.user_id != user.id:
            raise HTTPException(status_code=400, detail="Invalid strategy")
        strategy_id = st.id
    else:
        strategy_id = _get_default_strategy_id(session, user.id)

    txn = Transaction(
        holding_id=holding.id,
        strategy_id=strategy_id,
        notes=data.notes,
        transaction_type=data.transaction_type,
        quantity=data.quantity,
        price=data.price,
        total=data.quantity * data.price,
        transaction_date=txn_date,
        realized_profit=realized_profit,
    )
    session.add(txn)
    session.commit()
    session.refresh(txn)
    invalidate_user_cache(user.id, holding.id)
    return txn


def _recompute_holding(session: Session, holding_id: int) -> None:
    holding = session.get(Holding, holding_id)
    if not holding:
        raise HTTPException(status_code=404, detail="Holding not found")
    txns = session.exec(
        select(Transaction).where(Transaction.holding_id == holding_id).order_by(Transaction.transaction_date, Transaction.id)
    ).all()
    qty = 0.0
    avg = 0.0
    total_cost = 0.0
    for t in txns:
        if t.transaction_type == TransactionType.BUY:
            total_cost = total_cost + t.quantity * t.price
            qty = qty + t.quantity
            avg = (total_cost / qty) if qty > 0 else 0.0
            t.realized_profit = 0.0
        else:
            # validate available qty
            if t.quantity > qty:
                raise HTTPException(status_code=400, detail="Sell quantity exceeds available quantity during recompute")
            t.realized_profit = (t.price - avg) * t.quantity
            qty = qty - t.quantity
            total_cost = total_cost - avg * t.quantity
            if qty == 0:
                avg = 0.0
                total_cost = 0.0
        session.add(t)
    holding.quantity = qty
    holding.average_price = avg
    holding.total_cost = total_cost
    holding.updated_at = datetime.utcnow()
    session.add(holding)


@router.patch("/{transaction_id}", response_model=Transaction)
def update_transaction(transaction_id: int, data: TransactionUpdate, session: Session = Depends(get_session), user=Depends(get_current_user)):
    txn = session.get(Transaction, transaction_id)
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")
    holding = session.get(Holding, txn.holding_id)
    if not holding:
        raise HTTPException(status_code=404, detail="Holding not found")
    account = session.get(Account, holding.account_id)
    if not account or account.user_id != user.id:
        raise HTTPException(status_code=404, detail="Transaction not found")
    # Apply updates in-session
    if data.transaction_type is not None:
        txn.transaction_type = data.transaction_type
    if data.quantity is not None:
        txn.quantity = data.quantity
    if data.price is not None:
        txn.price = data.price
    if data.transaction_date is not None:
        txn.transaction_date = data.transaction_date
    if data.notes is not None:
        txn.notes = data.notes
    if data.strategy_id is not None:
        st = session.get(Strategy, data.strategy_id)
        if not st or st.user_id != user.id:
            raise HTTPException(status_code=400, detail="Invalid strategy")
        txn.strategy_id = st.id
    try:
        _recompute_holding(session, holding.id)
    except HTTPException:
        session.rollback()
        raise
    session.commit()
    session.refresh(txn)
    invalidate_user_cache(user.id, holding.id)
    return txn


@router.delete("/{transaction_id}")
def delete_transaction(transaction_id: int, session: Session = Depends(get_session), user=Depends(get_current_user)):
    txn = session.get(Transaction, transaction_id)
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")
    holding = session.get(Holding, txn.holding_id)
    if not holding:
        raise HTTPException(status_code=404, detail="Holding not found")
    account = session.get(Account, holding.account_id)
    if not account or account.user_id != user.id:
        raise HTTPException(status_code=404, detail="Transaction not found")
    session.delete(txn)
    try:
        _recompute_holding(session, holding.id)
    except HTTPException:
        session.rollback()
        raise
    session.commit()
    invalidate_user_cache(user.id, holding.id)
    return {"status": "deleted"}
