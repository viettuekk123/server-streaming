import hashlib
import secrets
import uuid
from datetime import timedelta

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db, now
from app.models import LoginSession, User
from app.schemas import Credentials, Register

router = APIRouter(prefix="/api/auth", tags=["auth"])
hasher = PasswordHasher()


def check_origin(request: Request):
    if request.headers.get("origin") != settings.app_origin:
        raise HTTPException(403, "Origin không hợp lệ")


def session_user(request: Request, db: Session) -> tuple[LoginSession, User]:
    raw = request.cookies.get("bvg_session", "")
    login = db.get(LoginSession, hashlib.sha256(raw.encode()).hexdigest()) if raw else None
    if not login or login.expires_at <= now():
        raise HTTPException(401, "Vui lòng đăng nhập")
    user = db.get(User, login.user_id)
    if not user:
        raise HTTPException(401, "Phiên đăng nhập không hợp lệ")
    return login, user


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    return session_user(request, db)[1]


def write_user(request: Request, db: Session = Depends(get_db)) -> User:
    check_origin(request)
    login, user = session_user(request, db)
    if not secrets.compare_digest(login.csrf_token, request.headers.get("x-csrf-token", "")):
        raise HTTPException(403, "CSRF token không hợp lệ")
    return user


def start_session(user: User, db: Session, response: Response) -> dict:
    raw = secrets.token_urlsafe(32)
    csrf = secrets.token_hex(32)
    db.add(LoginSession(token_hash=hashlib.sha256(raw.encode()).hexdigest(), user_id=user.id, csrf_token=csrf,
                        expires_at=now() + timedelta(days=settings.session_days)))
    db.commit()
    response.set_cookie("bvg_session", raw, httponly=True, secure=settings.cookie_secure, samesite="lax", max_age=settings.session_days * 86400, path="/")
    return {"user": {"id": user.id, "username": user.username}, "csrf_token": csrf}


@router.post("/register", status_code=201)
def register(body: Register, request: Request, response: Response, db: Session = Depends(get_db)):
    check_origin(request)
    if body.password != body.confirm_password:
        raise HTTPException(400, "Mật khẩu xác nhận không khớp")
    user = User(id=uuid.uuid4().hex, username=body.username.lower(), password_hash=hasher.hash(body.password))
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Tài khoản đã tồn tại")
    return start_session(user, db, response)


@router.post("/login")
def login(body: Credentials, request: Request, response: Response, db: Session = Depends(get_db)):
    check_origin(request)
    user = db.scalar(select(User).where(User.username == body.username.lower()))
    try:
        if not user:
            raise HTTPException(401, "Tài khoản hoặc mật khẩu không đúng")
        hasher.verify(user.password_hash, body.password)
    except (VerifyMismatchError, VerificationError):
        raise HTTPException(401, "Tài khoản hoặc mật khẩu không đúng")
    return start_session(user, db, response)


@router.get("/me")
def me(request: Request, db: Session = Depends(get_db)):
    login, user = session_user(request, db)
    return {"user": {"id": user.id, "username": user.username}, "csrf_token": login.csrf_token}


@router.post("/logout")
def logout(request: Request, response: Response, user: User = Depends(write_user), db: Session = Depends(get_db)):
    login, _ = session_user(request, db)
    db.delete(login)
    db.commit()
    response.delete_cookie("bvg_session", path="/")
    return {"ok": True}
