from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select
from ..db import get_session
from ..models import Strategy, Account, Holding, Transaction
from ..security import get_current_user


router = APIRouter(prefix="/strategies", tags=["strategies"])


class StrategyCreate(BaseModel):
    name: str


class StrategyUpdate(BaseModel):
    name: Optional[str] = None


def _ensure_swing(session: Session, user_id: int) -> Strategy:
    swing = session.exec(select(Strategy).where(Strategy.user_id == user_id, Strategy.name == "Swing")).first()
    if swing:
        return swing
    swing = Strategy(user_id=user_id, name="Swing")
    session.add(swing)
    session.commit()
    session.refresh(swing)
    return swing


@router.get("/", response_model=List[Strategy])
def list_strategies(session: Session = Depends(get_session), user=Depends(get_current_user)):
    _ensure_swing(session, user.id)
    return session.exec(select(Strategy).where(Strategy.user_id == user.id).order_by(Strategy.name)).all()


@router.post("/", response_model=Strategy)
def create_strategy(data: StrategyCreate, session: Session = Depends(get_session), user=Depends(get_current_user)):
    name = (data.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name is required")
    exists = session.exec(select(Strategy).where(Strategy.user_id == user.id, Strategy.name == name)).first()
    if exists:
        raise HTTPException(status_code=400, detail="Strategy already exists")
    st = Strategy(user_id=user.id, name=name)
    session.add(st)
    session.commit()
    session.refresh(st)
    return st


@router.patch("/{strategy_id}", response_model=Strategy)
def update_strategy(strategy_id: int, data: StrategyUpdate, session: Session = Depends(get_session), user=Depends(get_current_user)):
    st = session.get(Strategy, strategy_id)
    if not st or st.user_id != user.id:
        raise HTTPException(status_code=404, detail="Strategy not found")
    if data.name is not None:
        name = (data.name or "").strip()
        if not name:
            raise HTTPException(status_code=400, detail="Name is required")
        if st.name == "Swing" and name != "Swing":
            raise HTTPException(status_code=400, detail="Default strategy cannot be renamed")
        exists = session.exec(select(Strategy).where(Strategy.user_id == user.id, Strategy.name == name, Strategy.id != st.id)).first()
        if exists:
            raise HTTPException(status_code=400, detail="Strategy already exists")
        st.name = name
    session.add(st)
    session.commit()
    session.refresh(st)
    return st


@router.delete("/{strategy_id}")
def delete_strategy(strategy_id: int, session: Session = Depends(get_session), user=Depends(get_current_user)):
    st = session.get(Strategy, strategy_id)
    if not st or st.user_id != user.id:
        raise HTTPException(status_code=404, detail="Strategy not found")
    if st.name == "Swing":
        raise HTTPException(status_code=400, detail="Default strategy cannot be deleted")

    swing = _ensure_swing(session, user.id)

    acct_ids = [a.id for a in session.exec(select(Account).where(Account.user_id == user.id)).all() if a.id is not None]
    if acct_ids:
        holding_ids = [h.id for h in session.exec(select(Holding).where(Holding.account_id.in_(acct_ids))).all() if h.id is not None]
        if holding_ids:
            txns = session.exec(select(Transaction).where(Transaction.holding_id.in_(holding_ids), Transaction.strategy_id == st.id)).all()
            for t in txns:
                t.strategy_id = swing.id
                session.add(t)

    session.delete(st)
    session.commit()
    return {"status": "deleted"}
