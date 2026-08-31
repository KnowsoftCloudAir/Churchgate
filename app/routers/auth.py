from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Depends, Request, Form, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select
from datetime import datetime
import secrets
import string

from app.database import get_session
from app.models import User, UserRole, ChurchUnit, ChurchLevel, ApprovalStatus
from app.auth import (
    verify_password, get_password_hash, create_access_token,
    get_current_user, ACCESS_TOKEN_EXPIRE_MINUTES
)

router = APIRouter(prefix="/auth", tags=["auth"])
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))

def generate_code(prefix: str = "CG") -> str:
    suffix = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(6))
    return f"{prefix}-{suffix}"

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, user: Optional[User] = Depends(get_current_user)):
    if user:
        return RedirectResponse("/dashboard", status_code=303)
    return templates.TemplateResponse("auth/login.html", {"request": request})

@router.post("/login")
async def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    session: Session = Depends(get_session)
):
    user = session.exec(select(User).where(User.email == email)).first()
    if not user or not verify_password(password, user.hashed_password):
        return templates.TemplateResponse("auth/login.html", {
            "request": request, "error": "Invalid email or password"
        }, status_code=400)
    if not user.is_active:
        return templates.TemplateResponse("auth/login.html", {
            "request": request, "error": "Account deactivated. Contact Knowsoft Churchgate support."
        }, status_code=400)

    # Church admins must belong to an approved church
    if user.role == UserRole.church_admin and user.church_id:
        church = session.get(ChurchUnit, user.church_id)
        if church and church.approval_status != "approved":
            return templates.TemplateResponse("auth/login.html", {
                "request": request, "error": "Your church is still pending approval by Knowsoft Admin."
            }, status_code=400)

    token = create_access_token({"sub": user.email})
    user.last_login = datetime.utcnow()
    session.add(user)
    session.commit()
    resp = RedirectResponse("/dashboard", status_code=303)
    resp.set_cookie("access_token", token, httponly=True, max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60, samesite="lax")
    return resp

@router.get("/register-church", response_class=HTMLResponse)
async def register_church_page(request: Request):
    return templates.TemplateResponse("auth/register_church.html", {"request": request})

@router.post("/register-church")
async def register_church(
    request: Request,
    name: str = Form(...),
    level: str = Form(...),  # global | country | state | group | district
    global_code: str = Form(""),
    country_code: str = Form(""),
    state_code: str = Form(""),
    group_code: str = Form(""),
    district_code: str = Form(""),
    country_name: str = Form(""),
    state_name: str = Form(""),
    doctrine: str = Form(""),
    activity_days: str = Form(""),
    owner_name: str = Form(...),
    resident_pastor: str = Form(...),
    address: str = Form(""),
    phone: str = Form(""),
    email: str = Form(...),
    admin_full_name: str = Form(...),
    admin_password: str = Form(...),
    session: Session = Depends(get_session)
):
    # Validate level
    try:
        church_level = ChurchLevel(level)
    except ValueError:
        return templates.TemplateResponse("auth/register_church.html", {
            "request": request, "error": "Invalid church level"
        }, status_code=400)

    # For non-global, parent codes are required
    if church_level != ChurchLevel.global_church:
        if not global_code.strip():
            return templates.TemplateResponse("auth/register_church.html", {
                "request": request, "error": "Global Church Code is required for non-global churches."
            }, status_code=400)

    # Generate unique code
    code = generate_code("CG")
    while session.exec(select(ChurchUnit).where(ChurchUnit.code == code)).first():
        code = generate_code("CG")

    # Resolve parent if possible
    parent_id = None
    if church_level != ChurchLevel.global_church and global_code.strip():
        parent = session.exec(
            select(ChurchUnit).where(
                ChurchUnit.code == global_code.strip(),
                ChurchUnit.level == ChurchLevel.global_church,
                ChurchUnit.approval_status == "approved"
            )
        ).first()
        # Parent may also be country/state/group depending on level
        if not parent and country_code:
            parent = session.exec(select(ChurchUnit).where(ChurchUnit.code == country_code.strip())).first()
        if parent:
            parent_id = parent.id

    existing_user = session.exec(select(User).where(User.email == email)).first()
    if existing_user:
        return templates.TemplateResponse("auth/register_church.html", {
            "request": request, "error": "Email already registered"
        }, status_code=400)

    church = ChurchUnit(
        code=code,
        name=name.strip(),
        level=church_level,
        parent_id=parent_id,
        global_code=global_code.strip() or (code if church_level == ChurchLevel.global_church else None),
        country_code=country_code.strip() or None,
        state_code=state_code.strip() or None,
        group_code=group_code.strip() or None,
        district_code=district_code.strip() or None,
        country_name=country_name.strip() or None,
        state_name=state_name.strip() or None,
        doctrine=doctrine.strip() or None,
        activity_days=activity_days.strip() or None,
        owner_name=owner_name.strip(),
        resident_pastor=resident_pastor.strip(),
        address=address.strip() or None,
        phone=phone.strip() or None,
        email=email.strip(),
        approval_status="pending"
    )
    session.add(church)
    session.commit()
    session.refresh(church)

    # Create pending church admin user (cannot login until approved)
    admin = User(
        email=email.strip(),
        hashed_password=get_password_hash(admin_password),
        full_name=admin_full_name.strip(),
        role=UserRole.church_admin,
        church_id=church.id,
        is_active=True
    )
    session.add(admin)
    session.commit()

    return templates.TemplateResponse("auth/pending.html", {
        "request": request,
        "church_name": name,
        "code": code,
        "email": email
    })

@router.get("/logout")
async def logout():
    resp = RedirectResponse("/auth/login", status_code=303)
    resp.delete_cookie("access_token")
    return resp
