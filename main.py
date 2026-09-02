from fastapi import FastAPI, Request, Depends, Form
from typing import Optional
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse
from contextlib import asynccontextmanager
from sqlmodel import Session, select
from pathlib import Path

from app.database import create_db_and_tables, get_session, engine
from app.models import User, UserRole
from app.auth import get_password_hash, get_current_user, verify_password, create_access_token, ACCESS_TOKEN_EXPIRE_MINUTES
from app.routers import auth, admin, church, district, members, programs, projects

@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
    try:
        with Session(engine) as session:
            admin = session.exec(select(User).where(User.email == "admin@knowsoft.com")).first()
            if not admin:
                admin = User(
                    email="admin@knowsoft.com",
                    hashed_password=get_password_hash("Admin@12345"),
                    full_name="Knowsoft General Admin",
                    role=UserRole.general_admin,
                    is_active=True
                )
                session.add(admin)
                session.commit()
            else:
                # Keep known password working after deploys
                admin.hashed_password = get_password_hash("Admin@12345")
                admin.role = UserRole.general_admin
                admin.is_active = True
                session.add(admin)
                session.commit()
            print("✅ General Admin: admin@knowsoft.com / Admin@12345")
            # Full sample: Knowsoft Bible Church hierarchy + members + stats
            from app.seed_sample import seed_knowsoft_bible_church
            seed_knowsoft_bible_church(session)
    except Exception as e:
        print(f"⚠️ Seed: {e}")
    yield

app = FastAPI(
    title="Knowsoft Churchgate",
    description="Church hierarchy, membership & growth analytics platform",
    version="1.0.0",
    lifespan=lifespan
)

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

@app.get("/", response_class=HTMLResponse)
async def home(request: Request, user: Optional[User] = Depends(get_current_user)):
    if user:
        from app.auth import role_val
        rv = role_val(user.role)
        if rv == "member":
            # pastors may use church dashboard
            if getattr(user, "can_view_church_dashboard", False):
                return RedirectResponse("/dashboard", status_code=303)
            return RedirectResponse("/member/portal", status_code=303)
        if rv == "general_admin":
            return RedirectResponse("/admin/", status_code=303)
        return RedirectResponse("/dashboard", status_code=303)
    try:
        return templates.TemplateResponse("index.html", {"request": request, "user": None})
    except Exception as e:
        return HTMLResponse(f"<h1>Churchgate</h1><p><a href='/auth/login'>Sign in</a></p><!-- {e} -->")

@app.get("/health")
async def health():
    return {"status": "ok", "app": "Knowsoft Churchgate"}

# Hidden admin portal
@app.get("/ks-admin/login", response_class=HTMLResponse)
async def ks_admin_login_page(request: Request):
    return templates.TemplateResponse("admin/login.html", {"request": request})

@app.post("/ks-admin/login")
async def ks_admin_login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    session: Session = Depends(get_session)
):
    user = session.exec(select(User).where(User.email == email)).first()
    if not user or not verify_password(password, user.hashed_password):
        return templates.TemplateResponse("admin/login.html", {
            "request": request, "error": "Invalid credentials"
        }, status_code=400)
    if user.role != UserRole.general_admin:
        return templates.TemplateResponse("admin/login.html", {
            "request": request, "error": "General Admin only"
        }, status_code=403)
    token = create_access_token({"sub": user.email})
    resp = RedirectResponse("/admin/", status_code=303)
    resp.set_cookie("access_token", token, httponly=True, max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60, samesite="lax")
    return resp
