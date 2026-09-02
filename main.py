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
            return RedirectResponse("/admin/", status_code=303)
        if rv == "member" and not getattr(user, "can_view_church_dashboard", False):
            return RedirectResponse("/member/portal", status_code=303)
        return RedirectResponse("/dashboard", status_code=303)
    return templates.TemplateResponse("index.html", {"request": request, "user": None})


@app.get("/health")
async def health():
    return {"status": "ok", "app": "Knowsoft Churchgate"}


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
    resp = RedirectResponse("/admin/", status_code=303)
    set_auth_cookie(resp, token)
    return resp
