from pathlib import Path
from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select
from datetime import datetime, date, timedelta
import secrets, string

from app.database import get_session
from app.models import User, UserRole, ChurchUnit, ChurchLevel, ChurchMember, WeeklyStat, MemberStatus
from app.auth import require_user, require_roles, get_password_hash

router = APIRouter(tags=["church"])
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))

def gen_code(prefix="CG"):
    return f"{prefix}-" + ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(5))

@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    user: User = Depends(require_user),
    session: Session = Depends(get_session)
):
    church = session.get(ChurchUnit, user.church_id) if user.church_id else None
    children = []
    stats = []
    members_count = 0
    if church:
        children = session.exec(select(ChurchUnit).where(ChurchUnit.parent_id == church.id)).all()
        stats = session.exec(
            select(WeeklyStat).where(WeeklyStat.church_id == church.id).order_by(WeeklyStat.week_start.desc()).limit(12)
        ).all()
        members_count = len(session.exec(select(ChurchMember).where(ChurchMember.church_id == church.id)).all())

        # Aggregate from children for higher levels
        if church.level != ChurchLevel.district and children:
            # Simple roll-up of latest week from children (MVP)
            pass

    return templates.TemplateResponse("church/dashboard.html", {
        "request": request, "user": user, "church": church,
        "children": children, "stats": stats, "members_count": members_count
    })

@router.get("/church/create-child", response_class=HTMLResponse)
async def create_child_page(
    request: Request,
    user: User = Depends(require_roles(UserRole.church_admin, UserRole.general_admin)),
    session: Session = Depends(get_session)
):
    if user.role != UserRole.general_admin and not getattr(user, "can_create_churches", False):
        raise HTTPException(403, "General Admin has not granted you permission to create churches")
    church = session.get(ChurchUnit, user.church_id) if user.church_id else None
    if not church or church.approval_status != "approved":
        raise HTTPException(403, "Only approved churches can create sub-units")
    # Global can create country; country→state; state→group; group→district
    level_map = {
        "global": "country",
        "country": "state",
        "state": "group",
        "group": "district"
    }
    next_level = level_map.get(church.level.value)
    if not next_level:
        return templates.TemplateResponse("church/message.html", {
            "request": request, "user": user,
            "title": "District is the lowest level",
            "message": "District churches cannot create child units."
        })
    return templates.TemplateResponse("church/create_child.html", {
        "request": request, "user": user, "parent": church, "next_level": next_level
    })

@router.post("/church/create-child")
async def create_child(
    request: Request,
    name: str = Form(...),
    admin_email: str = Form(...),
    admin_full_name: str = Form(...),
    admin_password: str = Form(...),
    resident_pastor: str = Form(""),
    user: User = Depends(require_roles(UserRole.church_admin, UserRole.general_admin)),
    session: Session = Depends(get_session)
):
    if user.role != UserRole.general_admin and not getattr(user, "can_create_churches", False):
        raise HTTPException(403, "General Admin has not granted you permission to create churches")
    parent = session.get(ChurchUnit, user.church_id)
    if not parent or parent.approval_status != "approved":
        raise HTTPException(403, "Not allowed")

    level_map = {"global": ChurchLevel.country, "country": ChurchLevel.state,
                 "state": ChurchLevel.group, "group": ChurchLevel.district}
    next_level = level_map.get(parent.level.value)
    if not next_level:
        raise HTTPException(400, "Cannot create child under district")

    code = gen_code("CG")
    while session.exec(select(ChurchUnit).where(ChurchUnit.code == code)).first():
        code = gen_code("CG")

    child = ChurchUnit(
        code=code,
        name=name.strip(),
        level=next_level,
        parent_id=parent.id,
        global_code=parent.global_code or parent.code,
        country_code=parent.country_code,
        state_code=parent.state_code,
        group_code=parent.group_code,
        approval_status="approved",  # created by parent → already trusted
        resident_pastor=resident_pastor.strip() or None,
        email=admin_email.strip()
    )
    # Set the appropriate code field
    if next_level == ChurchLevel.country:
        child.country_code = code
    elif next_level == ChurchLevel.state:
        child.state_code = code
    elif next_level == ChurchLevel.group:
        child.group_code = code
    elif next_level == ChurchLevel.district:
        child.district_code = code

    session.add(child)
    session.commit()
    session.refresh(child)

    if session.exec(select(User).where(User.email == admin_email)).first():
        raise HTTPException(400, "Email already used")

    admin = User(
        email=admin_email.strip(),
        hashed_password=get_password_hash(admin_password),
        full_name=admin_full_name.strip(),
        role=UserRole.church_admin,
        church_id=child.id,
        is_active=True
    )
    session.add(admin)
    session.commit()

    return RedirectResponse("/dashboard", status_code=303)
