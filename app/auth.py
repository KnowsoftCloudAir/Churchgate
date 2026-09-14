from datetime import datetime, timedelta
from typing import Optional
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPBearer
from jose import jwt, JWTError
from passlib.context import CryptContext
from sqlmodel import Session, select
import os
from app.database import get_session
from app.models import User, UserRole, UserStatus

SECRET = os.getenv("ELEON_SECRET", "eleon-knowsoft-secret-change-me")
ALGO = "HS256"
pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(p: str) -> str:
    return pwd.hash(p[:72])

def verify_password(plain: str, hashed: str) -> bool:
    try:
        return pwd.verify(plain[:72], hashed)
    except Exception:
        return False

def create_token(user_id: int) -> str:
    payload = {"sub": str(user_id), "exp": datetime.utcnow() + timedelta(days=7)}
    return jwt.encode(payload, SECRET, algorithm=ALGO)

def user_from_request(request: Request, session: Session) -> Optional[User]:
    token = request.cookies.get("eleon_token")
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
        raise HTTPException(status_code=303, headers={"Location": "/login"})
    if user.status != UserStatus.approved and user.role != UserRole.general_admin:
        raise HTTPException(status_code=403, detail="Account not approved")
    if user.access_expires_at and user.access_expires_at < datetime.utcnow():
        if user.role != UserRole.general_admin:
            raise HTTPException(status_code=403, detail="Access code expired — contact admin")
    return user

def require_admin(request: Request, session: Session = Depends(get_session)) -> User:
    user = require_user(request, session)
    if user.role != UserRole.general_admin:
        raise HTTPException(status_code=403, detail="Admin only")
    return user
