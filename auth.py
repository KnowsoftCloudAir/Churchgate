"""Simple JWT cookie auth for Knowsoft Churchgate."""
from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from sqlmodel import Session, select
from dotenv import load_dotenv
import os

from app.database import get_session
from app.models import User, UserRole

load_dotenv()
SECRET_KEY = os.getenv("SECRET_KEY", "knowsoft-churchgate-change-this-in-production-32chars")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "10080"))  # 7 days

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token", auto_error=False)


def role_val(role) -> str:
    if role is None:
        return ""
    return str(getattr(role, "value", role)).lower().replace("userrole.", "")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        if not plain or not hashed:
            return False
        # bcrypt 72-byte limit
        if isinstance(plain, str):
            plain = plain[:72]
        return pwd_context.verify(plain, hashed)
    except Exception:
        return False


def get_password_hash(password: str) -> str:
    if isinstance(password, str):
        password = password[:72]
    return pwd_context.hash(password)


def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def get_user_by_email(session: Session, email: str) -> Optional[User]:
    if not email:
        return None
    email = email.strip().lower()
    return session.exec(select(User).where(User.email == email)).first()


def set_auth_cookie(response, token: str) -> None:
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/",
        samesite="lax",
    )


def clear_auth_cookie(response) -> None:
    response.delete_cookie("access_token", path="/")


async def get_current_user(
    request: Request,
    token: Optional[str] = Depends(oauth2_scheme),
    session: Session = Depends(get_session),
) -> Optional[User]:
    if not token:
        token = request.cookies.get("access_token")
    if not token:
        return None
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email = payload.get("sub")
        if not email:
            return None
    except JWTError:
        return None
    user = get_user_by_email(session, email)
    if not user or not user.is_active:
        return None
    # Extra flags for templates
    rv = role_val(user.role)
    user.can_view_church_dashboard = rv in ("general_admin", "church_admin", "data_officer")
    user.member_status = None
    if rv == "member":
        try:
            from app.models import ChurchMember
            m = None
            if user.member_id:
                m = session.get(ChurchMember, user.member_id)
            if not m:
                m = session.exec(select(ChurchMember).where(ChurchMember.email == user.email)).first()
            if m and (str(m.status or "")).lower() == "pastor":
                user.can_view_church_dashboard = True
            user.member_status = m.status if m else None
        except Exception:
            pass
    return user


async def require_user(user: Optional[User] = Depends(get_current_user)) -> User:
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return user


def require_roles(*roles: UserRole):
    async def _check(user: User = Depends(require_user)) -> User:
        rv = role_val(user.role)
        allowed = {role_val(r) for r in roles} | {"general_admin"}
        if rv not in allowed:
            raise HTTPException(status_code=403, detail="Forbidden")
        return user
    return _check
