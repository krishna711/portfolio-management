from __future__ import annotations

import json
import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from ..db import get_session
from ..models import UserPreference
from ..security import get_current_user


router = APIRouter(prefix="/prefs", tags=["prefs"])


_ALLOWED_KEYS = {"ipo_tracker_columns"}


class PrefUpsert(BaseModel):
    value: Any


@router.get("/{key}")
def get_pref(key: str, session: Session = Depends(get_session), user=Depends(get_current_user)):
    if key not in _ALLOWED_KEYS:
        raise HTTPException(status_code=404, detail="Unknown preference")
    pref = session.exec(select(UserPreference).where(UserPreference.user_id == user.id, UserPreference.key == key)).first()
    if not pref:
        raise HTTPException(status_code=404, detail="Preference not set")
    parsed: Optional[Any] = None
    try:
        parsed = json.loads(pref.value)
    except Exception:
        parsed = None
    return {"key": key, "value": parsed if parsed is not None else pref.value}


@router.put("/{key}")
def put_pref(key: str, data: PrefUpsert, session: Session = Depends(get_session), user=Depends(get_current_user)):
    if key not in _ALLOWED_KEYS:
        raise HTTPException(status_code=404, detail="Unknown preference")

    try:
        stored = json.dumps(data.value)
    except Exception:
        stored = json.dumps(str(data.value))

    pref = session.exec(select(UserPreference).where(UserPreference.user_id == user.id, UserPreference.key == key)).first()
    if not pref:
        pref = UserPreference(user_id=user.id, key=key, value=stored)
    else:
        pref.value = stored
        pref.updated_at = datetime.datetime.utcnow()

    session.add(pref)
    session.commit()
    session.refresh(pref)
    return {"ok": True}
