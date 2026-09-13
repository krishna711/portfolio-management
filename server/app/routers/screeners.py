from typing import Optional
from fastapi import APIRouter, Depends
from sqlmodel import Session
from ..db import get_session
from ..security import get_current_user
from typing import Optional
from ..services.screeners import list_scanners, get_or_fetch_results, list_screener_dates, screener_stock_chart

router = APIRouter(prefix="/screeners", tags=["screeners"])

@router.get("/")
def get_screeners(session: Session = Depends(get_session), user=Depends(get_current_user)):
    return list_scanners(session)

# Define static/specific routes BEFORE dynamic '/{key}' to avoid shadowing
@router.get("/stock_chart")
def get_stock_chart(symbol: str, days: Optional[int] = 90, session: Session = Depends(get_session), user=Depends(get_current_user)):
    return screener_stock_chart(session, symbol, days=days or 90)

@router.get("/{key}/dates")
def get_screener_dates(key: str, session: Session = Depends(get_session), user=Depends(get_current_user)):
    return list_screener_dates(session, key)

@router.get("/{key}")
def get_screener(
    key: str,
    force: bool = False,
    debug: bool = False,
    driver: Optional[str] = None,
    date: Optional[str] = None,
    session: Session = Depends(get_session),
    user=Depends(get_current_user),
):
    return get_or_fetch_results(session, key, force=force, debug=debug, driver=driver, for_date_str=date)
