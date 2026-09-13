from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select
from ..db import get_session
from ..models import Holding, Account, Transaction, HoldingMeta
from ..security import get_current_user
from ..services.portfolio import invalidate_user_cache


router = APIRouter(prefix="/holdings", tags=["holdings"])


class HoldingUpdate(BaseModel):
    symbol: Optional[str] = None
    sl_price: Optional[float] = None


@router.get("/", response_model=List[Holding])
def list_holdings(account_id: Optional[int] = None, session: Session = Depends(get_session), user=Depends(get_current_user)):
    accounts = session.exec(select(Account).where(Account.user_id == user.id)).all()
    account_ids = [a.id for a in accounts]
    if account_id:
        if account_id not in account_ids:
            return []
        account_ids = [account_id]
    holdings = session.exec(select(Holding).where(Holding.account_id.in_(account_ids))).all() if account_ids else []
    return holdings


@router.patch("/{holding_id}", response_model=Holding)
def update_holding(holding_id: int, data: HoldingUpdate, session: Session = Depends(get_session), user=Depends(get_current_user)):
    holding = session.get(Holding, holding_id)
    if not holding:
        raise HTTPException(status_code=404, detail="Holding not found")
    account = session.get(Account, holding.account_id)
    if not account or account.user_id != user.id:
        raise HTTPException(status_code=404, detail="Holding not found")
    if data.symbol is not None and data.symbol != holding.symbol:
        # ensure uniqueness per (account_id, symbol)
        exists = session.exec(select(Holding).where(Holding.account_id == holding.account_id, Holding.symbol == data.symbol)).first()
        if exists:
            raise HTTPException(status_code=400, detail="Holding with this symbol already exists in the account")
        holding.symbol = data.symbol
    if data.sl_price is not None:
        meta = session.exec(select(HoldingMeta).where(HoldingMeta.holding_id == holding.id)).first()
        if not meta:
            meta = HoldingMeta(holding_id=holding.id, sl_price=float(data.sl_price or 0.0))
        else:
            meta.sl_price = float(data.sl_price or 0.0)
        session.add(meta)
    session.add(holding)
    session.commit()
    session.refresh(holding)
    # Invalidate user caches so SL and targets reflect immediately on refresh
    invalidate_user_cache(user.id, holding.id)
    return holding


@router.delete("/{holding_id}")
def delete_holding(holding_id: int, session: Session = Depends(get_session), user=Depends(get_current_user)):
    holding = session.get(Holding, holding_id)
    if not holding:
        raise HTTPException(status_code=404, detail="Holding not found")
    account = session.get(Account, holding.account_id)
    if not account or account.user_id != user.id:
        raise HTTPException(status_code=404, detail="Holding not found")
    txns = session.exec(select(Transaction).where(Transaction.holding_id == holding.id)).all()
    for t in txns:
        session.delete(t)
    session.delete(holding)
    session.commit()
    invalidate_user_cache(user.id, holding.id)
    return {"status": "deleted"}
