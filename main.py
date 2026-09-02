from pathlib import Path
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Depends, Form, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlmodel import Session, select

from app.database import create_db_and_tables, get_session, engine
from app.models import User, UserRole
from app.auth import (
    get_password_hash, get_current_user, verify_password,
    create_access_token, set_auth_cookie, role_val,
)
from app.routers import auth, admin, church, district, members, programs, projects


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
    try:
        with Session(engine) as session:
            admin = session.exec(
                select(User).where(User.email == "admin@knowsoft.com")
            ).first()
            if not admin:
                session.add(User(
                    email="admin@knowsoft.com",
                    hashed_password=get_password_hash("Admin@12345"),
                    full_name="Knowsoft General Admin",
                    role=UserRole.general_admin,
                    is_active=True,
                ))
                session.commit()
                print("✅ General Admin created: admin@knowsoft.com / Admin@12345")
            else:
                admin.role = UserRole.general_admin
                admin.is_active = True
                session.add(admin)
                session.commit()
                print("✅ General Admin present: admin@knowsoft.com")
            from app.seed_sample import seed_knowsoft_bible_church
            seed_knowsoft_bible_church(session)
    except Exception as e:
        print(f"⚠️ Seed: {e}")
    yield


app = FastAPI(title="Knowsoft Churchgate", version="1.0.0", lifespan=lifespan)

BASE_DIR = Path(__file__).resolve().parent
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "app" / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))

app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(church.router)
app.include_router(district.router)
app.include_router(members.router)
app.include_router(programs.router)
app.include_router(projects.router)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    # Browser: send unauthenticated users to login instead of JSON
    if exc.status_code == 401:
        accept = (request.headers.get("accept") or "").lower()
        if "text/html" in accept or "text/html" not in accept:
            # Prefer redirect for normal browser navigations
            path = str(request.url.path)
            if path.startswith("/admin"):
                return RedirectResponse("/auth/login", status_code=303)
            return RedirectResponse("/auth/login", status_code=303)
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.get("/", response_class=HTMLResponse)
async def home(request: Request, user: Optional[User] = Depends(get_current_user)):
    if user:
        rv = role_val(user.role)
        if rv == "general_admin":
            return RedirectResponse("/admin-panel", status_code=303)
        if rv == "member" and not getattr(user, "can_view_church_dashboard", False):
            return RedirectResponse("/member/portal", status_code=303)
        return RedirectResponse("/my-dashboard", status_code=303)
    return templates.TemplateResponse("index.html", {"request": request, "user": None})


@app.get("/health")
async def health():
    return {"status": "ok", "app": "Knowsoft Churchgate"}


@app.get("/admin-panel", response_class=HTMLResponse)
async def admin_panel(
    request: Request,
    user: Optional[User] = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Crash-proof General Admin page (no template engine)."""
    if not user or role_val(user.role) != "general_admin":
        return RedirectResponse("/auth/login", status_code=303)
    churches, pending, note = [], [], ""
    try:
        from app.models import ChurchUnit
        churches = list(session.exec(select(ChurchUnit)).all())
        pending = [c for c in churches if (getattr(c, "approval_status", "") or "") == "pending"]
    except Exception as e:
        note = str(e)
    rows = ""
    for c in churches[:40]:
        rows += (
            f"<tr><td class='p-2 border-b'>{getattr(c,'name','')}</td>"
            f"<td class='p-2 border-b text-xs'><code>{getattr(c,'code','')}</code></td>"
            f"<td class='p-2 border-b'>{getattr(c,'approval_status','')}</td>"
            f"<td class='p-2 border-b text-xs'>"
            f"<form class='inline' method='post' action='/admin/churches/{c.id}/approve'>"
            f"<button class='text-teal-700 underline'>Approve</button></form></td></tr>"
        )
    pend = ""
    for c in pending:
        pend += f"<li class='mb-2'>{c.name} ({c.code}) "
        pend += f"<form class='inline' method='post' action='/admin/churches/{c.id}/approve'>"
        pend += f"<button class='ml-2 text-sm bg-teal-600 text-white px-2 py-1 rounded'>Approve</button></form></li>"
    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
    <title>General Admin</title><script src="https://cdn.tailwindcss.com"></script></head>
    <body class="bg-slate-100 min-h-screen">
    <header class="bg-white border-b px-4 py-3 flex justify-between items-center">
      <strong>Knowsoft Churchgate · General Admin</strong>
      <span class="text-sm text-slate-500">{user.email}</span>
      <a class="text-red-600 text-sm" href="/auth/logout">Sign out</a>
    </header>
    <main class="max-w-4xl mx-auto p-6">
      <h1 class="text-2xl font-bold mb-2">Admin panel</h1>
      {"<p class='text-amber-700 text-sm mb-4'>"+note+"</p>" if note else ""}
      <h2 class="font-semibold mt-6 mb-2">Pending ({len(pending)})</h2>
      <ul class="bg-white rounded-xl border p-4 mb-6">{pend or '<li class=text-slate-400>None</li>'}</ul>
      <h2 class="font-semibold mb-2">Churches ({len(churches)})</h2>
      <div class="bg-white rounded-xl border overflow-x-auto">
        <table class="w-full text-sm"><thead><tr class="bg-slate-50 text-left">
          <th class="p-2">Name</th><th class="p-2">Code</th><th class="p-2">Status</th><th class="p-2"></th>
        </tr></thead><tbody>{rows or '<tr><td class=p-4 colspan=4>No churches</td></tr>'}</tbody></table>
      </div>
      <p class="mt-6 text-sm text-slate-500"><a class="text-blue-700" href="/auth/change-password">Change password</a></p>
    </main></body></html>"""
    return HTMLResponse(html)


@app.get("/my-dashboard", response_class=HTMLResponse)
async def my_dashboard(
    request: Request,
    user: Optional[User] = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Crash-proof church dashboard."""
    if not user:
        return RedirectResponse("/auth/login", status_code=303)
    rv = role_val(user.role)
    if rv == "general_admin":
        return RedirectResponse("/admin-panel", status_code=303)
    if rv == "member" and not getattr(user, "can_view_church_dashboard", False):
        return RedirectResponse("/member/portal", status_code=303)
    church = None
    members_count = 0
    try:
        from app.models import ChurchUnit, ChurchMember
        if user.church_id:
            church = session.get(ChurchUnit, user.church_id)
        if church:
            members_count = len(list(session.exec(
                select(ChurchMember).where(ChurchMember.church_id == church.id)
            ).all()))
    except Exception:
        pass
    name = getattr(church, "name", None) or "My church"
    code = getattr(church, "code", None) or ""
    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
    <title>{name}</title><script src="https://cdn.tailwindcss.com"></script></head>
    <body class="bg-slate-100 min-h-screen">
    <header class="bg-white border-b px-4 py-3 flex flex-wrap gap-3 justify-between items-center">
      <strong>Churchgate</strong>
      <nav class="text-sm flex gap-3">
        <a href="/district/members">Members</a>
        <a href="/district/stats/enter">Attendance</a>
        <a href="/programs/">Programs</a>
        <a href="/auth/change-password">Password</a>
        <a class="text-red-600" href="/auth/logout">Sign out</a>
      </nav>
    </header>
    <main class="max-w-3xl mx-auto p-6">
      <h1 class="text-2xl font-bold">{name}</h1>
      <p class="text-sm text-slate-500 mb-6">{code} · {user.email}</p>
      <div class="bg-white rounded-2xl border p-6 mb-4">
        <p class="text-xs uppercase text-slate-500">Members in this unit</p>
        <p class="text-4xl font-bold text-blue-700">{members_count}</p>
      </div>
      <div class="flex flex-wrap gap-3 text-sm">
        <a class="px-4 py-2 rounded-xl bg-slate-900 text-white" href="/district/members">View members</a>
        <a class="px-4 py-2 rounded-xl border bg-white" href="/district/stats/enter">Weekly attendance</a>
        <a class="px-4 py-2 rounded-xl border bg-white" href="/programs/">Programs</a>
      </div>
    </main></body></html>"""
    return HTMLResponse(html)



# Keep /ks-admin/login as alias to public login
@app.get("/ks-admin/login", response_class=HTMLResponse)
async def ks_admin_login_page(request: Request):
    return RedirectResponse("/auth/login", status_code=303)


@app.post("/ks-admin/login")
async def ks_admin_login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    session: Session = Depends(get_session),
):
    # Same as public login, then go admin if general_admin
    user = session.exec(select(User).where(User.email == email.strip().lower())).first()
    if not user or not verify_password(password, user.hashed_password):
        return templates.TemplateResponse("auth/login.html", {
            "request": request, "error": "Invalid credentials"
        }, status_code=400)
    if role_val(user.role) != "general_admin":
        return templates.TemplateResponse("auth/login.html", {
            "request": request, "error": "General Admin only — use /auth/login for other accounts"
        }, status_code=403)
    token = create_access_token({"sub": user.email})
    resp = RedirectResponse("/admin-panel", status_code=303)
    set_auth_cookie(resp, token)
    return resp
