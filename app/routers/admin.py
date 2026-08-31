from pathlib import Path
from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select
import secrets, string

from app.database import get_session
from app.models import User, UserRole, ChurchUnit
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
    users = session.exec(select(User).order_by(User.created_at.desc()).limit(50)).all()
    pending = [c for c in churches if c.approval_status == "pending"]
    return templates.TemplateResponse("admin/dashboard.html", {
        "request": request, "user": user,
        "churches": churches, "pending": pending, "users": users
    })

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
    # Ensure global churches get their code as global_code
    if church.level.value == "global" and not church.global_code:
        church.global_code = church.code
    session.add(church)
    # Activate church admin
    admin = session.exec(select(User).where(User.church_id == church_id, User.role == UserRole.church_admin)).first()
    if admin:
        admin.is_active = True
        session.add(admin)
    session.commit()
    # In production: send email with login details + church code
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
