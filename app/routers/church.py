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
    """Church dashboard — members without grant are redirected away."""
    from app.auth import role_val
    try:
        if role_val(user.role) == "member" and not getattr(user, "can_view_church_dashboard", False):
            return RedirectResponse("/member/portal", status_code=303)

        church = session.get(ChurchUnit, user.church_id) if user.church_id else None
        children = []
        stats = []
        members_count = 0
        chart_labels, chart_attendance, chart_offering, chart_tithe, chart_donation = [], [], [], [], []
        total_offering = total_tithe = 0.0
        latest_attendance = 0
        demo = {}
        map_markers = []
        state_summary = []
        is_global_view = False
        scope_ids = []

        if role_val(user.role) == "general_admin" and not church:
            churches = list(session.exec(select(ChurchUnit).order_by(ChurchUnit.name)).all())
            try:
                members_count = len(list(session.exec(select(ChurchMember)).all()))
            except Exception:
                members_count = 0
            return templates.TemplateResponse("church/dashboard.html", {
                "request": request, "user": user, "church": None,
                "children": churches, "stats": [], "members_count": members_count,
                "chart_labels": [], "chart_attendance": [], "chart_offering": [],
                "chart_tithe": [], "chart_donation": [],
                "total_offering": 0, "total_tithe": 0, "latest_attendance": 0,
                "is_admin_overview": True, "demo": {},
                "map_markers": [], "is_global_view": False, "state_summary": [],
                "admin_viewing": False,
            })

        if church:
            children = list(session.exec(select(ChurchUnit).where(ChurchUnit.parent_id == church.id)).all())
            scope_ids = collect_descendant_ids(session, church.id)
            try:
                members_list = list(session.exec(
                    select(ChurchMember).where(
                        ChurchMember.church_id.in_(scope_ids),
                        ChurchMember.approval_status == "approved",
                    )
                ).all())
            except Exception:
                members_list = []
            members_count = len(members_list)

            def count_sex_age(sex, ages):
                return sum(
                    1 for m in members_list
                    if (str(m.sex or "")).lower() in sex and (str(m.age_category or "")) in ages
                )

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
            try:
                for s in session.exec(select(WeeklyStat).where(WeeklyStat.church_id.in_(scope_ids))).all():
                    n = int(getattr(s, "newcomers", 0) or 0)
                    c = int(getattr(s, "converts", 0) or 0)
                    demo["newcomers_men"] += n // 2
                    demo["newcomers_women"] += n - n // 2
                    demo["converts_men"] += c // 2
                    demo["converts_women"] += c - c // 2
            except Exception:
                pass

            try:
                own_stats = list(session.exec(
                    select(WeeklyStat).where(WeeklyStat.church_id == church.id)
                    .order_by(WeeklyStat.week_start.desc()).limit(12)
                ).all())
            except Exception:
                own_stats = []
            if own_stats:
                stats = list(reversed(own_stats))
            else:
                try:
                    all_stats = list(session.exec(
                        select(WeeklyStat).where(WeeklyStat.church_id.in_(scope_ids))
                    ).all())
                except Exception:
                    all_stats = []
                by_week = {}
                for s in all_stats:
                    key = str(getattr(s, "week_start", ""))
                    if key not in by_week:
                        by_week[key] = {
                            "week_start": s.week_start,
                            "adult_male": 0, "adult_female": 0,
                            "children_boys": 0, "children_girls": 0,
                            "youth_male": 0, "youth_female": 0,
                            "offering": 0.0, "tithe": 0.0, "donation": 0.0,
                        }
                    b = by_week[key]
                    for k in ("adult_male", "adult_female", "children_boys", "children_girls", "youth_male", "youth_female"):
                        b[k] += int(getattr(s, k, 0) or 0)
                    for k in ("offering", "tithe", "donation"):
                        b[k] += float(getattr(s, k, 0) or 0)

                class Agg:
                    def __init__(self, d):
                        self.__dict__.update(d)

                ordered = sorted(by_week.values(), key=lambda x: str(x["week_start"]))[-12:]
                stats = [Agg(d) for d in ordered]

            for s in stats:
                att = sum(int(getattr(s, k, 0) or 0) for k in (
                    "adult_male", "adult_female", "children_boys", "children_girls", "youth_male", "youth_female"
                ))
                chart_labels.append(str(getattr(s, "week_start", "")))
                chart_attendance.append(att)
                chart_offering.append(float(getattr(s, "offering", 0) or 0))
                chart_tithe.append(float(getattr(s, "tithe", 0) or 0))
                chart_donation.append(float(getattr(s, "donation", 0) or 0))
                total_offering += float(getattr(s, "offering", 0) or 0)
                total_tithe += float(getattr(s, "tithe", 0) or 0)
            if chart_attendance:
                latest_attendance = chart_attendance[-1]

            lv = str(getattr(church.level, "value", church.level)).lower()
            is_global_view = lv in ("global", "global_church")
            if is_global_view and scope_ids:
                state_counts = {}
                for uid in scope_ids:
                    u = session.get(ChurchUnit, uid)
                    if not u:
                        continue
                    if getattr(u, "latitude", None) is not None and getattr(u, "longitude", None) is not None:
                        try:
                            map_markers.append({
                                "name": u.name, "code": u.code,
                                "level": str(getattr(u.level, "value", u.level)),
                                "lat": float(u.latitude), "lng": float(u.longitude),
                                "address": u.address or "",
                                "country": u.country_name or "", "state": u.state_name or "",
                            })
                        except Exception:
                            pass
                    key = (u.country_name or "Unknown", u.state_name or "Unknown")
                    state_counts[key] = state_counts.get(key, 0) + 1
                state_summary = [{"country": a, "state": b, "count": n} for (a, b), n in sorted(state_counts.items())]

        return templates.TemplateResponse("church/dashboard.html", {
            "request": request, "user": user, "church": church,
            "children": children, "stats": stats, "members_count": members_count,
            "chart_labels": chart_labels, "chart_attendance": chart_attendance,
            "chart_offering": chart_offering, "chart_tithe": chart_tithe,
            "chart_donation": chart_donation, "total_offering": total_offering,
            "total_tithe": total_tithe, "latest_attendance": latest_attendance,
            "is_admin_overview": False, "demo": demo,
            "map_markers": map_markers, "is_global_view": is_global_view,
            "state_summary": state_summary, "admin_viewing": False,
        })
    except Exception as e:
        return HTMLResponse(
            f"""<!DOCTYPE html><html><head><title>Dashboard</title>
            <script src="https://cdn.tailwindcss.com"></script></head>
            <body class="bg-slate-100 p-8 font-sans">
            <div class="max-w-lg mx-auto bg-white rounded-2xl border p-8">
              <h1 class="text-xl font-bold mb-2">Dashboard</h1>
              <p class="text-sm text-slate-500 mb-4">Could not load the full dashboard.</p>
              <p class="text-xs text-red-600 mb-4">{e}</p>
              <div class="flex flex-wrap gap-3 text-sm">
                <a class="px-3 py-2 rounded-lg bg-slate-900 text-white" href="/district/members">Members</a>
                <a class="px-3 py-2 rounded-lg border" href="/district/stats/enter">Attendance</a>
                <a class="px-3 py-2 rounded-lg border" href="/programs/">Programs</a>
                <a class="px-3 py-2 rounded-lg border" href="/auth/logout">Sign out</a>
              </div>
            </div></body></html>"""
        )



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


@router.get("/church/settings", response_class=HTMLResponse)
async def church_settings_page(
    request: Request,
    user: User = Depends(require_roles(UserRole.church_admin, UserRole.general_admin)),
    session: Session = Depends(get_session)
):
    church = session.get(ChurchUnit, user.church_id) if user.church_id else None
    if not church:
        raise HTTPException(400, "No church linked")
    return templates.TemplateResponse("church/settings.html", {"request": request, "user": user, "church": church})

@router.post("/church/settings")
async def church_settings_save(
    address: str = Form(""),
    resident_pastor: str = Form(""),
    pastor_phone: str = Form(""),
    pastor_email: str = Form(""),
    weekly_activities_note: str = Form(""),
    tithe_account_name: str = Form(""),
    tithe_account_number: str = Form(""),
    tithe_bank_name: str = Form(""),
    offering_account_name: str = Form(""),
    offering_account_number: str = Form(""),
    offering_bank_name: str = Form(""),
    user: User = Depends(require_roles(UserRole.church_admin, UserRole.general_admin)),
    session: Session = Depends(get_session)
):
    church = session.get(ChurchUnit, user.church_id) if user.church_id else None
    if not church:
        raise HTTPException(400, "No church linked")
    church.address = address.strip() or None
    church.resident_pastor = resident_pastor.strip() or None
    church.pastor_phone = pastor_phone.strip() or None
    church.pastor_email = pastor_email.strip() or None
    church.weekly_activities_note = weekly_activities_note.strip() or None
    church.tithe_account_name = tithe_account_name.strip() or None
    church.tithe_account_number = tithe_account_number.strip() or None
    church.tithe_bank_name = tithe_bank_name.strip() or None
    church.offering_account_name = offering_account_name.strip() or None
    church.offering_account_number = offering_account_number.strip() or None
    church.offering_bank_name = offering_bank_name.strip() or None
    session.add(church)
    session.commit()
    return RedirectResponse("/church/settings", status_code=303)
