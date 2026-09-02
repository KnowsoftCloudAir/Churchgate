from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from fastapi.responses import RedirectResponse
from sqlmodel import Session, select
from dotenv import load_dotenv
import os

from app.database import get_session
from app.models import User, UserRole

load_dotenv()
SECRET_KEY = os.getenv("SECRET_KEY", "knowsoft-churchgate-change-this-in-production-32chars")
ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 1440 * 7))  # 7 days

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token", auto_error=False)


def role_val(role) -> str:
    if role is None:
        return ""
    return str(getattr(role, "value", role)).lower().replace("userrole.", "")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        if isinstance(plain, str):
            plain = plain.encode("utf-8")[:72].decode("utf-8", errors="ignore")
        return pwd_context.verify(plain, hashed)
    except Exception:
        return False


def get_password_hash(password: str) -> str:
    if isinstance(password, str):
        password = password.encode("utf-8")[:72].decode("utf-8", errors="ignore")
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def get_user_by_email(session: Session, email: str) -> Optional[User]:
    return session.exec(select(User).where(User.email == email)).first()


def set_auth_cookie(response, token: str, request: Optional[Request] = None) -> None:
    """Set session cookie so it works on Render HTTPS."""
    secure = False
    if request is not None:
        # Render terminates TLS; X-Forwarded-Proto is https
        proto = request.headers.get("x-forwarded-proto", "")
        url_scheme = str(request.url.scheme)
        secure = proto == "https" or url_scheme == "https"
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        expires=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/",
        samesite="lax",
        secure=secure,
    )


def clear_auth_cookie(response) -> None:
    response.delete_cookie("access_token", path="/")


def extract_token(request: Request, bearer: Optional[str] = None) -> Optional[str]:
    if bearer:
        return bearer
    # Cookie (primary for browser forms)
    tok = request.cookies.get("access_token")
    if tok:
        return tok
    # Authorization header fallback
    auth = request.headers.get("authorization") or request.headers.get("Authorization")
    if auth and auth.lower().startswith("bearer "):
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


async def require_user(request: Request, user: Optional[User] = Depends(get_current_user)) -> User:
    """Require login — redirect to HTML login (never bare JSON for browsers)."""
    if user is None:
        accept = (request.headers.get("accept") or "").lower()
        # API-ish clients still get JSON
        if "application/json" in accept and "text/html" not in accept:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated",
            )
        # Default: send browser to sign-in
        return_to = str(request.url.path)
        login = "/auth/login"
        if return_to.startswith("/admin") or return_to.startswith("/ks-admin"):
            login = "/ks-admin/login"
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            detail="Not authenticated",
            headers={"Location": login},
        )
    return user


def require_roles(*roles: UserRole):
    async def checker(
        request: Request,
        user: User = Depends(require_user),
    ) -> User:
        rv = role_val(user.role)
        allowed = {role_val(r) for r in roles} | {"general_admin"}
        if rv not in allowed:
            accept = (request.headers.get("accept") or "").lower()
            if "text/html" in accept or "text/html" not in accept:
                # Redirect browsers away from forbidden JSON
                raise HTTPException(
                    status_code=status.HTTP_303_SEE_OTHER,
                    detail="Forbidden",
                    headers={"Location": "/auth/login"},
                )
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user

    return checker
