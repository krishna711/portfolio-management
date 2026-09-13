from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr
from sqlmodel import Session, select
import datetime
import hashlib
import logging
import secrets
import smtplib
from email.message import EmailMessage

from ..db import get_session
from ..models import User, PasswordResetAttempt
from ..security import get_password_hash, verify_password, create_access_token, get_current_user
from ..config import settings


router = APIRouter(prefix="/auth", tags=["auth"])


_log = logging.getLogger(__name__)


_RESET_PASSWORD_MAX_PER_DAY = 4


def _email_hash(email: str) -> str:
    return hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str


class PasswordResetRequest(BaseModel):
    email: EmailStr


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


def _send_email(to_email: str, subject: str, body: str) -> None:
    if not settings.smtp_host:
        raise HTTPException(status_code=500, detail="SMTP not configured")
    from_addr = settings.smtp_from or settings.smtp_user
    if not from_addr:
        raise HTTPException(status_code=500, detail="SMTP_FROM not configured")

    msg = EmailMessage()
    msg["From"] = from_addr
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(body)

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as s:
            if settings.smtp_use_tls:
                s.starttls()
            if settings.smtp_user:
                s.login(settings.smtp_user, settings.smtp_password)
            s.send_message(msg)
    except HTTPException:
        raise
    except Exception:
        _log.exception("failed to send email")
        raise HTTPException(status_code=500, detail="Failed to send email")


@router.post("/register")
def register(data: RegisterRequest, session: Session = Depends(get_session)):
    existing = session.exec(select(User).where(User.email == data.email)).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    user = User(email=data.email, hashed_password=get_password_hash(data.password), must_change_password=False)
    session.add(user)
    session.commit()
    session.refresh(user)

    admin_exists = session.exec(select(User.id).where(User.is_admin == True)).first()
    if not admin_exists:
        user.is_admin = True
        session.add(user)
        session.commit()
        session.refresh(user)

    token = create_access_token({"sub": user.email})
    return {"access_token": token, "token_type": "bearer", "must_change_password": bool(getattr(user, "must_change_password", False)), "is_admin": bool(getattr(user, "is_admin", False))}


@router.post("/login")
def login(form_data: OAuth2PasswordRequestForm = Depends(), session: Session = Depends(get_session)):
    user = session.exec(select(User).where(User.email == form_data.username)).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Incorrect email or password")
    token = create_access_token({"sub": user.email})
    return {"access_token": token, "token_type": "bearer", "must_change_password": bool(getattr(user, "must_change_password", False)), "is_admin": bool(getattr(user, "is_admin", False))}


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return {"email": user.email, "must_change_password": bool(getattr(user, "must_change_password", False)), "is_admin": bool(getattr(user, "is_admin", False))}


@router.post("/reset_password")
def reset_password(data: PasswordResetRequest, session: Session = Depends(get_session)):
    now = datetime.datetime.utcnow()
    today = now.date()
    email_hash = _email_hash(str(data.email))

    attempt = session.exec(
        select(PasswordResetAttempt).where(
            PasswordResetAttempt.email_hash == email_hash,
            PasswordResetAttempt.for_date == today,
        )
    ).first()

    if not attempt:
        attempt = PasswordResetAttempt(
            email_hash=email_hash,
            for_date=today,
            count=0,
            first_attempt_at=now,
            last_attempt_at=now,
        )

    if attempt.count >= _RESET_PASSWORD_MAX_PER_DAY:
        attempt.last_attempt_at = now
        session.add(attempt)
        session.commit()
        raise HTTPException(
            status_code=429,
            detail="Too many password reset attempts today. Please try again tomorrow.",
        )

    attempt.count += 1
    attempt.last_attempt_at = now
    session.add(attempt)
    session.commit()

    user = session.exec(select(User).where(User.email == data.email)).first()
    # Do not reveal if account exists
    if not user:
        return {"ok": True}

    temp_password = secrets.token_urlsafe(9)
    _send_email(
        to_email=user.email,
        subject="Portfolio: Password Reset",
        body=(
            "Your password has been reset. Use this temporary password to login:\n\n"
            f"{temp_password}\n\n"
            "After login, please change your password immediately."
        ),
    )

    user.hashed_password = get_password_hash(temp_password)
    user.must_change_password = True
    session.add(user)
    session.commit()
    return {"ok": True}


@router.post("/change_password")
def change_password(data: ChangePasswordRequest, session: Session = Depends(get_session), user: User = Depends(get_current_user)):
    db_user = session.get(User, user.id)
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")
    if not verify_password(data.current_password, db_user.hashed_password):
        raise HTTPException(status_code=400, detail="Incorrect current password")
    if not data.new_password or len(data.new_password) < 6:
        raise HTTPException(status_code=400, detail="New password must be at least 6 characters")
    db_user.hashed_password = get_password_hash(data.new_password)
    db_user.must_change_password = False
    session.add(db_user)
    session.commit()
    return {"ok": True}
