from pathlib import Path
from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select
import secrets, string

from app.database import get_session
from app.models import User, UserRole, ChurchUnit, ChurchLevel, ChurchMember, WeeklyStat
from app.auth import require_user, require_roles, get_password_hash

router = APIRouter(tags=["church"])
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))

def gen_code(prefix="CG"):
    return f"{prefix}-" + ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(5))

def _level_val(level) -> str:
    return getattr(level, "value", str(level))

def collect_descendant_ids(session: Session, root_id: int) -> list:
    """All unit ids under root including root."""
    ids = [root_id]
    queue = [root_id]
    while queue:
        pid = queue.pop(0)
        kids = session.exec(select(ChurchUnit).where(ChurchUnit.parent_id == pid)).all()
        for k in kids:
            ids.append(k.id)
            queue.append(k.id)
    return ids

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
    chart_labels = []
    chart_attendance = []
    chart_offering = []
    chart_tithe = []
    chart_donation = []
    total_offering = 0.0
    total_tithe = 0.0
    latest_attendance = 0
    scope_ids = []

    if user.role == UserRole.general_admin and not church:
        # Show global sample overview
        churches = session.exec(select(ChurchUnit).order_by(ChurchUnit.name)).all()
        members_count = len(session.exec(select(ChurchMember)).all())
        return templates.TemplateResponse("church/dashboard.html", {
            "request": request, "user": user, "church": None,
            "children": churches, "stats": [], "members_count": members_count,
            "chart_labels": [], "chart_attendance": [], "chart_offering": [],
            "chart_tithe": [], "chart_donation": [],
            "total_offering": 0, "total_tithe": 0, "latest_attendance": 0,
            "is_admin_overview": True,
        })

    if church:
        children = session.exec(select(ChurchUnit).where(ChurchUnit.parent_id == church.id)).all()
        scope_ids = collect_descendant_ids(session, church.id)

        # Members in this unit + all descendants (so Global/Country see district members)
        members_count = len(session.exec(
            select(ChurchMember).where(ChurchMember.church_id.in_(scope_ids))
        ).all())

        # Stats: prefer this unit; if empty (higher levels), aggregate from descendants
        own_stats = session.exec(
            select(WeeklyStat).where(WeeklyStat.church_id == church.id)
            .order_by(WeeklyStat.week_start.desc()).limit(12)
        ).all()

        if own_stats:
            stats = list(reversed(own_stats))
        else:
            # Aggregate by week_start across descendants
            all_stats = session.exec(
                select(WeeklyStat).where(WeeklyStat.church_id.in_(scope_ids))
            ).all()
            by_week = {}
            for s in all_stats:
                key = s.week_start.isoformat()
                if key not in by_week:
                    by_week[key] = {
                        "week_start": s.week_start,
                        "adult_male": 0, "adult_female": 0,
                        "children_boys": 0, "children_girls": 0,
                        "youth_male": 0, "youth_female": 0,
                        "offering": 0.0, "tithe": 0.0, "donation": 0.0,
                        "newcomers": 0, "converts": 0,
                    }
                b = by_week[key]
                b["adult_male"] += s.adult_male
                b["adult_female"] += s.adult_female
                b["children_boys"] += s.children_boys
                b["children_girls"] += s.children_girls
                b["youth_male"] += s.youth_male
                b["youth_female"] += s.youth_female
                b["offering"] += s.offering
                b["tithe"] += s.tithe
                b["donation"] += s.donation
                b["newcomers"] += s.newcomers
                b["converts"] += s.converts
            # fake objects for template
            class Agg:
                def __init__(self, d):
                    self.__dict__.update(d)
            ordered = sorted(by_week.values(), key=lambda x: x["week_start"])[-12:]
            stats = [Agg(d) for d in ordered]

        for s in stats:
            att = (s.adult_male + s.adult_female + s.children_boys +
                   s.children_girls + s.youth_male + s.youth_female)
            chart_labels.append(str(s.week_start))
            chart_attendance.append(att)
            chart_offering.append(float(s.offering))
            chart_tithe.append(float(s.tithe))
            chart_donation.append(float(s.donation))
            total_offering += float(s.offering)
            total_tithe += float(s.tithe)
        if chart_attendance:
            latest_attendance = chart_attendance[-1]

    return templates.TemplateResponse("church/dashboard.html", {
        "request": request,
        "user": user,
        "church": church,
        "children": children,
        "stats": stats,
        "members_count": members_count,
        "chart_labels": chart_labels,
        "chart_attendance": chart_attendance,
        "chart_offering": chart_offering,
        "chart_tithe": chart_tithe,
        "chart_donation": chart_donation,
        "total_offering": total_offering,
        "total_tithe": total_tithe,
        "latest_attendance": latest_attendance,
        "is_admin_overview": False,
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
    level_map = {"global": "country", "country": "state", "state": "group", "group": "district"}
    next_level = level_map.get(_level_val(church.level))
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

    level_map = {
        "global": ChurchLevel.country, "country": ChurchLevel.state,
        "state": ChurchLevel.group, "group": ChurchLevel.district
    }
    next_level = level_map.get(_level_val(parent.level))
    if not next_level:
        raise HTTPException(400, "Cannot create child under district")

    code = gen_code("CG")
    while session.exec(select(ChurchUnit).where(ChurchUnit.code == code)).first():
        code = gen_code("CG")

    child = ChurchUnit(
        code=code, name=name.strip(), level=next_level, parent_id=parent.id,
        global_code=parent.global_code or parent.code,
        country_code=parent.country_code, state_code=parent.state_code,
        group_code=parent.group_code, approval_status="approved",
        resident_pastor=resident_pastor.strip() or None, email=admin_email.strip()
    )
    lv = _level_val(next_level)
    if lv == "country":
        child.country_code = code
    elif lv == "state":
        child.state_code = code
    elif lv == "group":
        child.group_code = code
    elif lv == "district":
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
        is_active=True,
        can_create_churches=True,
        can_approve_members=True,
    )
    session.add(admin)
    session.commit()
    return RedirectResponse("/dashboard", status_code=303)
