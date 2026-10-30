import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .db import get_db
from .models import AuthSession, User


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 600_000).hex()
    return f"{salt}:{digest}"


def verify_password(password: str, encoded: str) -> bool:
    salt, expected = encoded.split(":")
    actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 600_000).hex()
    return hmac.compare_digest(actual, expected)


def token_hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def create_session(db, user_id, response):
    token = secrets.token_urlsafe(32)
    csrf = secrets.token_urlsafe(32)
    db.add(
        AuthSession(
            token_hash=token_hash(token),
            user_id=user_id,
            csrf=csrf,
            expires=(datetime.now(timezone.utc) + timedelta(hours=12)).isoformat(),
        )
    )
    db.commit()
    response.set_cookie(
        "lf_session",
        token,
        httponly=True,
        samesite="strict",
        max_age=43200,
        path="/",
        secure=os.getenv("SECURE_COOKIES", "").lower() in ("1", "true", "yes"),
    )
    return csrf


def current_user(request: Request, db: Session = Depends(get_db)):
    session = db.get(AuthSession, token_hash(request.cookies.get("lf_session", "")))
    if not session or datetime.fromisoformat(session.expires) <= datetime.now(timezone.utc):
        raise HTTPException(401, "Vui lòng đăng nhập lại.")
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        supplied = request.headers.get("x-csrf-token", "")
        if not hmac.compare_digest(supplied, session.csrf):
            raise HTTPException(403, "Phiên thao tác không hợp lệ. Hãy tải lại trang.")
    request.state.auth_session = session
    return db.get(User, session.user_id)
