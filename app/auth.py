from datetime import datetime, timedelta
from typing import Optional
from fastapi import Depends, HTTPException, Request
from jose import jwt, JWTError
from passlib.context import CryptContext
from sqlmodel import Session
import os
import hashlib
from app.database import get_session
from app.models import User, UserRole, UserStatus

SECRET = os.getenv("ELEON_SECRET", "eleon-knowsoft-secret-change-me")
ALGO = "HS256"
pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")

def _bcrypt_safe(p: str) -> str:
    # bcrypt only uses 72 bytes; hash long passwords first
    raw = (p or "").encode("utf-8")
    if len(raw) > 72:
        return hashlib.sha256(raw).hexdigest()
    return p or ""

def hash_password(p: str) -> str:
    return pwd.hash(_bcrypt_safe(p))

def verify_password(plain: str, hashed: str) -> bool:
    try:
        return pwd.verify(_bcrypt_safe(plain), hashed)
    except Exception:
        return False

def create_token(user_id: int) -> str:
    payload = {"sub": str(user_id), "exp": datetime.utcnow() + timedelta(days=14)}
    return jwt.encode(payload, SECRET, algorithm=ALGO)

def user_from_request(request: Request, session: Session) -> Optional[User]:
    token = request.cookies.get("eleon_token")
    if not token:
        auth = request.headers.get("Authorization") or ""
        if auth.lower().startswith("bearer "):
            token = auth.split(" ", 1)[1].strip()
    if not token:
        return None
    try:
        data = jwt.decode(token, SECRET, algorithms=[ALGO])
        uid = int(data.get("sub"))
    except (JWTError, ValueError, TypeError):
        return None
    return session.get(User, uid)

def require_user(request: Request, session: Session = Depends(get_session)) -> User:
    user = user_from_request(request, session)
    if not user:
        raise HTTPException(status_code=401, detail="Login required")
    if user.role == UserRole.general_admin:
        return user
    if user.status == UserStatus.suspended:
        raise HTTPException(status_code=403, detail="Account suspended")
    if user.status != UserStatus.approved:
        raise HTTPException(status_code=403, detail="Account not approved")
    if user.access_expires_at and user.access_expires_at < datetime.utcnow():
        raise HTTPException(status_code=403, detail="Access expired")
    return user

def require_admin(request: Request, session: Session = Depends(get_session)) -> User:
    user = require_user(request, session)
    if user.role != UserRole.general_admin:
        raise HTTPException(status_code=403, detail="Admin only")
    return user
