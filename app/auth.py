from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from sqlmodel import Session, select
from dotenv import load_dotenv
import os
import bcrypt

from app.database import get_session
from app.models import User, UserRole

load_dotenv()
SECRET_KEY = os.getenv("SECRET_KEY", "knowsoft-churchgate-prod-secret-key-32chars!!")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", str(60 * 24 * 14)))  # 14 days

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token", auto_error=False)


def role_val(role) -> str:
    if role is None:
        return ""
    return str(getattr(role, "value", role)).lower().replace("userrole.", "")


def _truncate(password: str) -> bytes:
    raw = password if isinstance(password, str) else str(password)
    return raw.encode("utf-8")[:72]


def verify_password(plain: str, hashed: str) -> bool:
    if not plain or not hashed:
        return False
    try:
        h = hashed.encode("utf-8") if isinstance(hashed, str) else hashed
        return bcrypt.checkpw(_truncate(plain), h)
    except Exception:
        return False


def get_password_hash(password: str) -> str:
    return bcrypt.hashpw(_truncate(password), bcrypt.gensalt()).decode("utf-8")


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def get_user_by_email(session: Session, email: str) -> Optional[User]:
    if not email:
        return None
    return session.exec(select(User).where(User.email == email.strip().lower())).first()


def set_auth_cookie(response, token: str, request: Optional[Request] = None) -> None:
    """HTTPS-safe session cookie for Render."""
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        expires=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/",
        samesite="lax",
        secure=True,  # Render serves HTTPS; required for reliable cookies
    )


def clear_auth_cookie(response) -> None:
    response.delete_cookie("access_token", path="/", samesite="lax", secure=True)


def extract_token(request: Request, bearer: Optional[str] = None) -> Optional[str]:
    if bearer:
        return bearer
    tok = request.cookies.get("access_token")
    if tok:
        return tok
    auth = request.headers.get("authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth.split(" ", 1)[1].strip()
    return None


async def get_current_user(
    request: Request,
    token: Optional[str] = Depends(oauth2_scheme),
    session: Session = Depends(get_session),
) -> Optional[User]:
    try:
        raw = extract_token(request, token)
        if not raw:
            return None
        try:
            payload = jwt.decode(raw, SECRET_KEY, algorithms=[ALGORITHM])
            email = payload.get("sub")
            if not email:
                return None
        except JWTError:
            return None
        user = get_user_by_email(session, email)
        if not user or not user.is_active:
            return None
        try:
            rv = role_val(user.role)
            user.can_view_church_dashboard = rv in (
                "general_admin", "church_admin", "data_officer"
            )
            user.member_status = None
            if rv == "member":
                from app.models import ChurchMember
                m = None
                try:
                    if user.member_id:
                        m = session.get(ChurchMember, user.member_id)
                    if not m and user.email:
                        m = session.exec(
                            select(ChurchMember).where(ChurchMember.email == user.email)
                        ).first()
                except Exception:
                    m = None
                user.can_view_church_dashboard = bool(
                    m and (str(m.status or "")).lower() == "pastor"
                )
                user.member_status = m.status if m else None
        except Exception:
            user.can_view_church_dashboard = False
            user.member_status = None
        return user
    except Exception:
        return None


async def require_user(
    request: Request,
    user: Optional[User] = Depends(get_current_user),
) -> User:
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return user


def require_roles(*roles: UserRole):
    async def checker(request: Request, user: User = Depends(require_user)) -> User:
        rv = role_val(user.role)
        allowed = {role_val(r) for r in roles} | {"general_admin"}
        if rv not in allowed:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user
    return checker
