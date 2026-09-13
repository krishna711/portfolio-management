from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select
from ..db import get_session
from ..models import Account, Broker, Holding, Transaction
from ..security import get_current_user
from ..services.portfolio import invalidate_user_cache


router = APIRouter(prefix="/accounts", tags=["accounts"])


class AccountCreate(BaseModel):
    name: str
    broker: Optional[Broker] = None
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    access_token: Optional[str] = None


class AccountUpdate(BaseModel):
    name: Optional[str] = None
    broker: Optional[Broker] = None
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    access_token: Optional[str] = None


@router.get("/", response_model=List[Account])
def list_accounts(session: Session = Depends(get_session), user=Depends(get_current_user)):
    accounts = session.exec(select(Account).where(Account.user_id == user.id)).all()
    return accounts


@router.post("/", response_model=Account)
def create_account(data: AccountCreate, session: Session = Depends(get_session), user=Depends(get_current_user)):
    account = Account(user_id=user.id, name=data.name, broker=data.broker, api_key=data.api_key, api_secret=data.api_secret, access_token=data.access_token)
    session.add(account)
    session.commit()
    session.refresh(account)
    invalidate_user_cache(user.id)
    return account


@router.get("/{account_id}", response_model=Account)
def get_account(account_id: int, session: Session = Depends(get_session), user=Depends(get_current_user)):
    account = session.get(Account, account_id)
    if not account or account.user_id != user.id:
        raise HTTPException(status_code=404, detail="Account not found")
    return account


@router.patch("/{account_id}", response_model=Account)
def update_account(account_id: int, data: AccountUpdate, session: Session = Depends(get_session), user=Depends(get_current_user)):
    account = session.get(Account, account_id)
    if not account or account.user_id != user.id:
        raise HTTPException(status_code=404, detail="Account not found")
    if data.name is not None:
        account.name = data.name
    if data.broker is not None:
        account.broker = data.broker
    if data.api_key is not None:
        account.api_key = data.api_key
    if data.api_secret is not None:
        account.api_secret = data.api_secret
    if data.access_token is not None:
        account.access_token = data.access_token
    session.add(account)
    session.commit()
    session.refresh(account)
    invalidate_user_cache(user.id)
    return account


@router.delete("/{account_id}")
def delete_account(account_id: int, session: Session = Depends(get_session), user=Depends(get_current_user)):
    account = session.get(Account, account_id)
    if not account or account.user_id != user.id:
        raise HTTPException(status_code=404, detail="Account not found")
    holdings = session.exec(select(Holding).where(Holding.account_id == account.id)).all()
    for h in holdings:
        txns = session.exec(select(Transaction).where(Transaction.holding_id == h.id)).all()
        for t in txns:
            session.delete(t)
        session.delete(h)
    session.delete(account)
    session.commit()
    invalidate_user_cache(user.id)
    return {"status": "deleted"}
