from pathlib import Path
from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select

from app.database import get_session
from app.models import User, UserRole, ChurchUnit, ChurchMember, WeeklyStat
from app.auth import require_roles, get_password_hash

router = APIRouter(prefix="/admin", tags=["admin"])
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))

@router.get("/", response_class=HTMLResponse)
async def admin_home(
    request: Request,
    user: User = Depends(require_roles(UserRole.general_admin)),
    session: Session = Depends(get_session)
):
    churches = session.exec(select(ChurchUnit).order_by(ChurchUnit.created_at.desc())).all()
    users = session.exec(select(User).order_by(User.created_at.desc()).limit(100)).all()
    pending = [c for c in churches if c.approval_status == "pending"]
    subadmins = [u for u in users if u.role == UserRole.church_admin]
    return templates.TemplateResponse("admin/dashboard.html", {
        "request": request, "user": user,
        "churches": churches, "pending": pending, "users": users, "subadmins": subadmins
    })

@router.get("/churches/{church_id}", response_class=HTMLResponse)
async def view_church(
    church_id: int,
    request: Request,
    user: User = Depends(require_roles(UserRole.general_admin)),
    session: Session = Depends(get_session)
):
    church = session.get(ChurchUnit, church_id)
    if not church:
        raise HTTPException(404, "Church not found")
    members = session.exec(select(ChurchMember).where(ChurchMember.church_id == church_id).limit(100)).all()
    stats = session.exec(select(WeeklyStat).where(WeeklyStat.church_id == church_id).order_by(WeeklyStat.week_start.desc()).limit(12)).all()
    children = session.exec(select(ChurchUnit).where(ChurchUnit.parent_id == church_id)).all()
    admins = session.exec(select(User).where(User.church_id == church_id)).all()
    return templates.TemplateResponse("admin/church_edit.html", {
        "request": request, "user": user, "church": church,
        "members": members, "stats": stats, "children": children, "admins": admins
    })

@router.post("/churches/{church_id}/edit")
async def edit_church(
    church_id: int,
    name: str = Form(...),
    resident_pastor: str = Form(""),
    address: str = Form(""),
    phone: str = Form(""),
    email: str = Form(""),
    doctrine: str = Form(""),
    activity_days: str = Form(""),
    approval_status: str = Form("approved"),
    is_active: str = Form("yes"),
    user: User = Depends(require_roles(UserRole.general_admin)),
    session: Session = Depends(get_session)
):
    church = session.get(ChurchUnit, church_id)
    if not church:
        raise HTTPException(404, "Church not found")
    church.name = name.strip()
    church.resident_pastor = resident_pastor.strip() or None
    church.address = address.strip() or None
    church.phone = phone.strip() or None
    church.email = email.strip() or None
    church.doctrine = doctrine.strip() or None
    church.activity_days = activity_days.strip() or None
    church.approval_status = approval_status
    church.is_active = is_active == "yes"
    session.add(church)
    session.commit()
    return RedirectResponse(f"/admin/churches/{church_id}", status_code=303)

@router.post("/churches/{church_id}/approve")
async def approve_church(
    church_id: int,
    user: User = Depends(require_roles(UserRole.general_admin)),
    session: Session = Depends(get_session)
):
    church = session.get(ChurchUnit, church_id)
    if not church:
        raise HTTPException(404, "Church not found")
    church.approval_status = "approved"
    try:
        if str(getattr(church.level, "value", church.level)) == "global" and not church.global_code:
            church.global_code = church.code
    except Exception:
        pass
    session.add(church)
    admin = session.exec(select(User).where(User.church_id == church_id, User.role == UserRole.church_admin)).first()
    if admin:
        admin.is_active = True
        # Default permissions when GA approves church — GA can tighten later
        admin.can_approve_members = True
        admin.can_create_churches = True
        session.add(admin)
    session.commit()
    return RedirectResponse("/admin/", status_code=303)

@router.post("/churches/{church_id}/reject")
async def reject_church(
    church_id: int,
    user: User = Depends(require_roles(UserRole.general_admin)),
    session: Session = Depends(get_session)
):
    church = session.get(ChurchUnit, church_id)
    if not church:
        raise HTTPException(404, "Church not found")
    church.approval_status = "rejected"
    session.add(church)
    session.commit()
    return RedirectResponse("/admin/", status_code=303)

@router.post("/users/{user_id}/permissions")
async def set_subadmin_permissions(
    user_id: int,
    can_create_churches: str = Form(""),
    can_approve_members: str = Form(""),
    can_enter_stats: str = Form(""),
    user: User = Depends(require_roles(UserRole.general_admin)),
    session: Session = Depends(get_session)
):
    """General Admin grants/revokes sub-admin powers."""
    target = session.get(User, user_id)
    if not target:
        raise HTTPException(404, "User not found")
    if target.role == UserRole.general_admin:
        raise HTTPException(400, "Cannot change general admin")
    target.can_create_churches = can_create_churches == "yes"
    target.can_approve_members = can_approve_members == "yes"
    target.can_enter_stats = can_enter_stats == "yes"
    session.add(target)
    session.commit()
    return RedirectResponse("/admin/", status_code=303)

@router.post("/users/{user_id}/deactivate")
async def deactivate(
    user_id: int,
    user: User = Depends(require_roles(UserRole.general_admin)),
    session: Session = Depends(get_session)
):
    target = session.get(User, user_id)
    if not target or target.role == UserRole.general_admin:
        raise HTTPException(400, "Cannot deactivate")
    target.is_active = False
    session.add(target)
    session.commit()
    return RedirectResponse("/admin/", status_code=303)

@router.post("/users/{user_id}/activate")
async def activate(
    user_id: int,
    user: User = Depends(require_roles(UserRole.general_admin)),
    session: Session = Depends(get_session)
):
    target = session.get(User, user_id)
    if not target:
        raise HTTPException(404)
    target.is_active = True
    session.add(target)
    session.commit()
    return RedirectResponse("/admin/", status_code=303)
