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


@router.get("/globals", response_class=HTMLResponse)
async def list_global_churches(
    request: Request,
    user: User = Depends(require_roles(UserRole.general_admin)),
    session: Session = Depends(get_session)
):
    """All churches registered at Global level."""
    from app.models import ChurchLevel
    globals_ = session.exec(
        select(ChurchUnit).where(ChurchUnit.level == ChurchLevel.global_church)
        .order_by(ChurchUnit.created_at.desc())
    ).all()
    return templates.TemplateResponse("admin/globals.html", {
        "request": request, "user": user, "globals": globals_
    })

@router.get("/churches/{church_id}/dashboard", response_class=HTMLResponse)
async def admin_view_church_dashboard(
    church_id: int,
    request: Request,
    user: User = Depends(require_roles(UserRole.general_admin)),
    session: Session = Depends(get_session)
):
    """General Admin views any church dashboard (especially global level)."""
    from app.models import ChurchMember, WeeklyStat, ChurchLevel
    church = session.get(ChurchUnit, church_id)
    if not church:
        raise HTTPException(404, "Church not found")

    # Collect descendants
    ids = [church.id]
    queue = [church.id]
    while queue:
        pid = queue.pop(0)
        for k in session.exec(select(ChurchUnit).where(ChurchUnit.parent_id == pid)).all():
            ids.append(k.id)
            queue.append(k.id)

    children = session.exec(select(ChurchUnit).where(ChurchUnit.parent_id == church.id)).all()
    members_list = session.exec(
        select(ChurchMember).where(ChurchMember.church_id.in_(ids), ChurchMember.approval_status == "approved")
    ).all()
    members_count = len(members_list)

    def count_sex_age(sex, ages):
        return sum(1 for m in members_list if (m.sex or "").lower() in sex and (m.age_category or "") in ages)

    demo = {
        "men": count_sex_age(["brother", "male"], ["adult", "campus"]),
        "women": count_sex_age(["sister", "female"], ["adult", "campus"]),
        "youth_boys": count_sex_age(["brother", "male"], ["youth"]),
        "youth_girls": count_sex_age(["sister", "female"], ["youth"]),
        "ya_boys": count_sex_age(["brother", "male"], ["campus"]),
        "ya_girls": count_sex_age(["sister", "female"], ["campus"]),
        "children_boys": count_sex_age(["brother", "male"], ["child"]),
        "children_girls": count_sex_age(["sister", "female"], ["child"]),
        "newcomers_men": 0, "newcomers_women": 0, "newcomers_children": 0,
        "converts_men": 0, "converts_women": 0, "converts_children": 0,
    }
    all_stats = session.exec(select(WeeklyStat).where(WeeklyStat.church_id.in_(ids))).all()
    by_week = {}
    for s in all_stats:
        key = s.week_start.isoformat()
        if key not in by_week:
            by_week[key] = {
                "week_start": s.week_start,
                "adult_male": 0, "adult_female": 0, "children_boys": 0, "children_girls": 0,
                "youth_male": 0, "youth_female": 0, "offering": 0.0, "tithe": 0.0, "donation": 0.0,
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
        demo["newcomers_men"] += s.newcomers // 2
        demo["newcomers_women"] += s.newcomers - s.newcomers // 2
        demo["converts_men"] += s.converts // 2
        demo["converts_women"] += s.converts - s.converts // 2

    class Agg:
        def __init__(self, d):
            self.__dict__.update(d)
    ordered = sorted(by_week.values(), key=lambda x: x["week_start"])[-12:]
    stats = [Agg(d) for d in ordered]
    chart_labels, chart_attendance, chart_offering, chart_tithe, chart_donation = [], [], [], [], []
    total_offering = total_tithe = 0.0
    latest_attendance = 0
    for s in stats:
        att = s.adult_male + s.adult_female + s.children_boys + s.children_girls + s.youth_male + s.youth_female
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
        "request": request, "user": user, "church": church,
        "children": children, "stats": stats, "members_count": members_count,
        "chart_labels": chart_labels, "chart_attendance": chart_attendance,
        "chart_offering": chart_offering, "chart_tithe": chart_tithe,
        "chart_donation": chart_donation, "total_offering": total_offering,
        "total_tithe": total_tithe, "latest_attendance": latest_attendance,
        "is_admin_overview": False, "demo": demo,
        "admin_viewing": True,
    })

@router.post("/churches/{church_id}/disapprove")
async def disapprove_church(
    church_id: int,
    user: User = Depends(require_roles(UserRole.general_admin)),
    session: Session = Depends(get_session)
):
    """Disapprove / revoke a church (including global)."""
    church = session.get(ChurchUnit, church_id)
    if not church:
        raise HTTPException(404, "Church not found")
    church.approval_status = "rejected"
    church.is_active = False
    session.add(church)
    # Deactivate linked sub-admins
    for admin in session.exec(select(User).where(User.church_id == church_id)).all():
        if admin.role != UserRole.general_admin:
            admin.is_active = False
            session.add(admin)
    session.commit()
    return RedirectResponse("/admin/globals", status_code=303)
