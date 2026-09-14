"""Eleon — Your presentation partner (Knowsoft branding)."""
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path
import secrets
import string
import re
import io
from fastapi.responses import StreamingResponse

from fastapi import FastAPI, Request, Depends, Form, UploadFile, File, HTTPException, WebSocket, WebSocketDisconnect, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select

from app.database import create_db_and_tables, get_session, engine
from app.live_hub import hub
from app.models import User, UserRole, UserStatus, LoginCode, Presentation, Slide, EvalSession, EvalQuestion, EvalResponse, PresentationQANote, LiveSession, LiveViewer, LiveQuestion, AppSetting
from app.auth import (
    hash_password, verify_password, create_token,
    require_user, require_admin, user_from_request,
)

BASE = Path(__file__).resolve().parent
UPLOAD_SLIDES = BASE / "app" / "static" / "uploads" / "slides"
UPLOAD_SLIDES.mkdir(parents=True, exist_ok=True)
UPLOAD_DOCS = BASE / "app" / "static" / "uploads" / "docs"
UPLOAD_DOCS.mkdir(parents=True, exist_ok=True)

templates = Jinja2Templates(directory=str(BASE / "app" / "templates"))


def gen_login_number() -> str:
    return "EL-" + "".join(secrets.choice(string.digits) for _ in range(8))


def gen_code() -> str:
    return "ELEON-" + "".join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8))


DURATION_DAYS = {"week": 7, "month": 30, "year": 365}


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
    from sqlmodel import Session as S
    with S(engine) as session:
        # --- Admin (always reset password so login works) ---
        admin = session.exec(select(User).where(User.email == "admin@eleon.knowsoft")).first()
        if not admin:
            admin = User(
                email="admin@eleon.knowsoft",
                full_name="Eleon General Admin",
                hashed_password=hash_password("admin123"),
                role=UserRole.general_admin,
                status=UserStatus.approved,
                login_number="EL-ADMIN",
            )
            session.add(admin)
        else:
            admin.hashed_password = hash_password("admin123")
            admin.status = UserStatus.approved
            admin.role = UserRole.general_admin
            session.add(admin)

        # --- Demo presenter ---
        demo = session.exec(select(User).where(User.email == "demo@eleon.app")).first()
        if not demo:
            demo = User(
                email="demo@eleon.app",
                full_name="Demo Presenter",
                hashed_password=hash_password("demo123"),
                role=UserRole.presenter,
                status=UserStatus.approved,
                login_number="EL-DEMO001",
                access_expires_at=datetime.utcnow() + timedelta(days=365),
            )
            session.add(demo)
            session.commit()
            session.refresh(demo)
        else:
            demo.hashed_password = hash_password("demo123")
            demo.status = UserStatus.approved
            demo.access_expires_at = datetime.utcnow() + timedelta(days=365)
            session.add(demo)
            session.commit()
            session.refresh(demo)

        # --- Demo presentation ---
        pres = session.exec(
            select(Presentation).where(Presentation.owner_id == demo.id, Presentation.title == "Eleon Demo Deck")
        ).first()
        if not pres:
            pres = Presentation(owner_id=demo.id, title="Eleon Demo Deck", theme="churchgate")
            session.add(pres)
            session.commit()
            session.refresh(pres)
            demo_slides = [
                ("Welcome to Eleon", "Your presentation partner from Knowsoft.\nDesign · Present · Answer.", "Eleon helps you turn documents into attractive slides and present with voice commands."),
                ("What Eleon can do", "• Import PDF or text into slides\n• Enhance colours and animations\n• Voice: next, previous, go to slide\n• Q&A from your content", "Document import, enhance panel, PDF export, share link, and Eleon probe."),
                ("Demo talking points", "Revenue grew 24% year on year.\nThree regions: Lagos, Abuja, Port Harcourt.\nNext goal: expand training workshops.", "Sample figures for Q&A: growth 24%, cities Lagos Abuja Port Harcourt, focus on workshops."),  # chart filled below
                ("Thank you", "Thank you for your attention.\nAny questions?", "Closing slide. Eleon waits one minute for questions then goes off."),
            ]
            for i, (title, body, extra) in enumerate(demo_slides):
                session.add(Slide(
                    presentation_id=pres.id, position=i, title=title, body=body, extra_data=extra,
                    animation_in=["float3d", "cube", "bounceIn", "zoom"][i % 4],
                    accent="#14b8a6", bg_color="#0f172a",
                    layout_style="centered" if i == 0 else ("chart" if i == 2 else "title_body"),
                    icon_name=["rocket", "star", "growth", "check"][i % 4],
                    chart_type="doughnut" if i == 2 else "",
                    chart_data="Lagos:40,Abuja:30,PH:20,Others:10" if i == 2 else "",
                    word_animation="cascade",
                    keyword_animation=True,
                    online_image_url="https://picsum.photos/seed/eleon" + str(i) + "/900/500" if i == 1 else None,
                ))
            session.commit()
        session.commit()
        print("✅ Admin: admin@eleon.knowsoft / admin123")
        print("✅ Demo:  demo@eleon.app / demo123  (login number EL-DEMO001 optional)")
    yield


app = FastAPI(title="Eleon", lifespan=lifespan)

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    if exc.status_code in (401, 303) and "text/html" in (request.headers.get("accept") or ""):
        if exc.status_code == 401 or (exc.headers and exc.headers.get("Location") == "/login"):
            return RedirectResponse("/login", status_code=303)
    from fastapi.responses import JSONResponse as _JC
    return _JC({"detail": exc.detail}, status_code=exc.status_code)

app.mount("/static", StaticFiles(directory=str(BASE / "app" / "static")), name="static")



def extract_text_from_upload(filename: str, data: bytes) -> str:
    name = (filename or "").lower()
    if name.endswith(".txt") or name.endswith(".md"):
        return data.decode("utf-8", errors="ignore")
    if name.endswith(".pdf"):
        try:
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(data))
            parts = []
            for page in reader.pages:
                parts.append(page.extract_text() or "")
            return "\n".join(parts)
        except Exception as e:
            return f"[PDF extract error: {e}]"
    return data.decode("utf-8", errors="ignore")


def document_to_slide_payloads(text: str, max_slides: int = 20) -> list:
    """Split document into slide-sized chunks with title + body + extra_data."""
    text = (text or "").strip()
    if not text:
        return [{"title": "Empty document", "body": "No text extracted.", "extra_data": ""}]
    # Prefer markdown/numbered headings
    blocks = re.split(r"\n(?=#{1,3}\s|\d+\.\s+[A-Z]|[A-Z][A-Z0-9 ]{8,}$)", text)
    if len(blocks) < 2:
        # paragraph chunks
        paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
        blocks = paras if paras else [text]
    slides = []
    for i, block in enumerate(blocks[:max_slides]):
        lines = [ln.strip() for ln in block.strip().splitlines() if ln.strip()]
        if not lines:
            continue
        title = re.sub(r"^#{1,3}\s*", "", lines[0])[:120]
        body = "\n".join(lines[1:6]) if len(lines) > 1 else lines[0][:500]
        extra = block.strip()[:2000]
        slides.append({"title": title or f"Slide {i+1}", "body": body, "extra_data": extra})
    if not slides:
        slides.append({"title": "Document overview", "body": text[:600], "extra_data": text[:3000]})
    # Closing slide
    slides.append({
        "title": "Thank you",
        "body": "Thank you for your attention.\nAny questions?",
        "extra_data": text[:4000],
    })
    return slides


# ---------- Public / Auth ----------

@app.get("/manifest.webmanifest")
@app.get("/manifest.json")
async def web_manifest():
    path = BASE / "app" / "static" / "manifest.webmanifest"
    return FileResponse(path, media_type="application/manifest+json")


@app.get("/sw.js")
async def service_worker():
    path = BASE / "app" / "static" / "sw.js"
    return FileResponse(path, media_type="application/javascript")


@app.get("/", response_class=HTMLResponse)
async def splash(request: Request, session: Session = Depends(get_session)):
    user = user_from_request(request, session)
    return templates.TemplateResponse("splash.html", {"request": request, "user": user})


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("auth/login.html", {"request": request})


@app.post("/login")
async def login_post(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    session: Session = Depends(get_session),
):
    email_n = (email or "").strip().lower()
    user = session.exec(select(User).where(User.email == email_n)).first()
    if not user or not verify_password(password, user.hashed_password):
        return templates.TemplateResponse("auth/login.html", {
            "request": request, "error": "Invalid email or password. Try demo@eleon.app / demo123",
        }, status_code=400)
    if user.role != UserRole.general_admin:
        if user.status == UserStatus.suspended:
            return templates.TemplateResponse("auth/login.html", {
                "request": request, "error": "Account suspended",
            }, status_code=403)
        if user.status != UserStatus.approved:
            return templates.TemplateResponse("auth/login.html", {
                "request": request, "error": "Account pending approval",
            }, status_code=403)
        if user.access_expires_at and user.access_expires_at < datetime.utcnow():
            return templates.TemplateResponse("auth/login.html", {
                "request": request, "error": "Access expired — ask admin for a new code",
            }, status_code=403)
    token = create_token(user.id)
    dest = "/admin" if user.role == UserRole.general_admin else "/dashboard"
    resp = RedirectResponse(dest, status_code=303)
    resp.set_cookie("eleon_token", token, httponly=True, max_age=14 * 86400, samesite="lax", path="/")
    return resp


@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return templates.TemplateResponse("auth/register.html", {"request": request})


@app.post("/register")
async def register_post(
    request: Request,
    full_name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    access_code: str = Form(""),
    session: Session = Depends(get_session),
):
    email = email.strip().lower()
    if session.exec(select(User).where(User.email == email)).first():
        return templates.TemplateResponse("auth/register.html", {
            "request": request, "error": "Email already registered",
        }, status_code=400)
    user = User(
        email=email,
        full_name=full_name.strip(),
        hashed_password=hash_password(password),
        role=UserRole.presenter,
        status=UserStatus.pending,
    )
    # Optional: redeem access code at registration
    code_row = None
    if access_code.strip():
        code_row = session.exec(
            select(LoginCode).where(LoginCode.code == access_code.strip().upper(), LoginCode.is_used == False)
        ).first()
        if code_row:
            days = DURATION_DAYS.get(code_row.duration, 30)
            user.status = UserStatus.approved
            user.login_number = gen_login_number()
            user.access_expires_at = datetime.utcnow() + timedelta(days=days)
            code_row.is_used = True
            code_row.issued_to_email = email
            session.add(code_row)
    session.add(user)
    session.commit()
    session.refresh(user)
    if code_row:
        msg = f"Approved! Your login number is {user.login_number}. Access for {code_row.duration}."
    else:
        msg = "Registration received. Wait for admin approval and your login number."
    return templates.TemplateResponse("auth/register.html", {
        "request": request, "success": msg,
    })


@app.get("/logout")
async def logout():
    resp = RedirectResponse("/", status_code=303)
    resp.delete_cookie("eleon_token")
    return resp


# ---------- Presenter dashboard ----------
@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, user: User = Depends(require_user), session: Session = Depends(get_session)):
    pres = session.exec(
        select(Presentation).where(Presentation.owner_id == user.id).order_by(Presentation.updated_at.desc())
    ).all()
    return templates.TemplateResponse("presenter/dashboard.html", {
        "request": request, "user": user, "presentations": pres,
    })


@app.post("/presentations/new")
async def new_presentation(
    title: str = Form("Untitled presentation"),
    user: User = Depends(require_user),
    session: Session = Depends(get_session),
):
    p = Presentation(owner_id=user.id, title=title.strip() or "Untitled presentation")
    session.add(p)
    session.commit()
    session.refresh(p)
    # starter slide
    session.add(Slide(
        presentation_id=p.id, position=0, title="Welcome",
        body="Start editing this slide.\nAdd images and notes for Eleon.",
        extra_data="This is a new Eleon presentation.",
    ))
    session.commit()
    return RedirectResponse(f"/presentations/{p.id}/edit", status_code=303)


@app.get("/presentations/{pid}/edit", response_class=HTMLResponse)
async def edit_presentation(
    pid: int, request: Request,
    user: User = Depends(require_user), session: Session = Depends(get_session),
):
    p = session.get(Presentation, pid)
    if not p or p.owner_id != user.id:
        raise HTTPException(404)
    slides = session.exec(
        select(Slide).where(Slide.presentation_id == pid).order_by(Slide.position)
    ).all()
    return templates.TemplateResponse("presenter/editor.html", {
        "request": request, "user": user, "presentation": p, "slides": slides,
    })


@app.post("/presentations/{pid}/slides")
async def add_slide(
    pid: int,
    title: str = Form("New slide"),
    body: str = Form(""),
    extra_data: str = Form(""),
    animation_in: str = Form("fade"),
    animation_out: str = Form("fade"),
    user: User = Depends(require_user),
    session: Session = Depends(get_session),
):
    p = session.get(Presentation, pid)
    if not p or p.owner_id != user.id:
        raise HTTPException(404)
    n = len(session.exec(select(Slide).where(Slide.presentation_id == pid)).all())
    session.add(Slide(
        presentation_id=pid, position=n, title=title.strip(),
        body=body, extra_data=extra_data,
        animation_in=animation_in, animation_out=animation_out,
    ))
    p.updated_at = datetime.utcnow()
    session.add(p)
    session.commit()
    return RedirectResponse(f"/presentations/{pid}/edit", status_code=303)


@app.post("/presentations/{pid}/slides/{sid}")
async def update_slide(
    pid: int, sid: int,
    title: str = Form(""),
    body: str = Form(""),
    extra_data: str = Form(""),
    animation_in: str = Form("fade"),
    animation_out: str = Form("fade"),
    bg_color: str = Form("#0f172a"),
    accent: str = Form("#14b8a6"),
    notes: str = Form(""),
    layout_style: str = Form("title_body"),
    icon_name: str = Form(""),
    chart_type: str = Form(""),
    chart_data: str = Form(""),
    keyword_animation: str = Form("on"),
    word_animation: str = Form("fadeUp"),
    online_image_url: str = Form(""),
    pattern: str = Form("gradient_teal"),
    image_style: str = Form("frame"),
    word_emphasis: str = Form("on"),
    user: User = Depends(require_user),
    session: Session = Depends(get_session),
):
    p = session.get(Presentation, pid)
    s = session.get(Slide, sid)
    if not p or not s or p.owner_id != user.id or s.presentation_id != pid:
        raise HTTPException(404)
    s.title = title
    s.body = body
    s.extra_data = extra_data
    s.animation_in = animation_in
    s.animation_out = animation_out
    s.bg_color = bg_color
    s.accent = accent
    s.notes = notes
    s.layout_style = layout_style or "title_body"
    s.icon_name = icon_name or ""
    s.chart_type = chart_type or ""
    s.chart_data = chart_data or ""
    s.keyword_animation = (keyword_animation == "on")
    s.word_animation = word_animation or "fadeUp"
    s.online_image_url = (online_image_url or "").strip() or None
    s.pattern = pattern or "gradient_teal"
    s.image_style = image_style or "frame"
    s.word_emphasis = (word_emphasis == "on")
    p.updated_at = datetime.utcnow()
    session.add(s)
    session.add(p)
    session.commit()
    return RedirectResponse(f"/presentations/{pid}/edit?sid={sid}", status_code=303)


@app.get("/presentations/{pid}/notes.txt")
async def generate_notes(pid: int, user: User = Depends(require_user), session: Session = Depends(get_session)):
    p = session.get(Presentation, pid)
    if not p or p.owner_id != user.id:
        raise HTTPException(404)
    slides = session.exec(select(Slide).where(Slide.presentation_id == pid).order_by(Slide.position)).all()
    lines = [f"PRESENTATION NOTES — {p.title}", f"Generated by Eleon (Knowsoft)", ""]
    for i, s in enumerate(slides, 1):
        lines.append(f"=== SLIDE {i}: {s.title} ===")
        lines.append(s.body or "")
        if s.extra_data:
            lines.append("--- Eleon data ---")
            lines.append(s.extra_data)
        if s.notes:
            lines.append("--- Presenter notes ---")
            lines.append(s.notes)
        lines.append("")
    text = "\n".join(lines)
    return StreamingResponse(io.BytesIO(text.encode("utf-8")), media_type="text/plain",
                             headers={"Content-Disposition": f'attachment; filename="eleon_notes_{pid}.txt"'})


@app.post("/presentations/{pid}/slides/{sid}/image")
async def upload_slide_image(
    pid: int, sid: int,
    image: UploadFile = File(...),
    user: User = Depends(require_user),
    session: Session = Depends(get_session),
):
    p = session.get(Presentation, pid)
    s = session.get(Slide, sid)
    if not p or not s or p.owner_id != user.id or s.presentation_id != pid:
        raise HTTPException(404)
    data = await image.read()
    if len(data) > 8_000_000:
        raise HTTPException(400, "Image too large")
    ext = Path(image.filename or "img.png").suffix.lower() or ".png"
    if ext not in (".png", ".jpg", ".jpeg", ".webp", ".gif"):
        ext = ".png"
    fname = f"s{sid}_{secrets.token_hex(6)}{ext}"
    (UPLOAD_SLIDES / fname).write_bytes(data)
    s.image_path = f"/static/uploads/slides/{fname}"
    session.add(s)
    session.commit()
    return RedirectResponse(f"/presentations/{pid}/edit?sid={sid}", status_code=303)


@app.post("/presentations/{pid}/slides/{sid}/delete")
async def delete_slide(
    pid: int, sid: int,
    user: User = Depends(require_user),
    session: Session = Depends(get_session),
):
    p = session.get(Presentation, pid)
    s = session.get(Slide, sid)
    if not p or not s or p.owner_id != user.id:
        raise HTTPException(404)
    session.delete(s)
    session.commit()
    return RedirectResponse(f"/presentations/{pid}/edit", status_code=303)


@app.post("/presentations/{pid}/settings")
async def presentation_settings(
    pid: int,
    footer_text: str = Form(""),
    default_pattern: str = Form("gradient_teal"),
    user: User = Depends(require_user),
    session: Session = Depends(get_session),
    logo: UploadFile = File(None),
):
    p = session.get(Presentation, pid)
    if not p or p.owner_id != user.id:
        raise HTTPException(404)
    p.footer_text = (footer_text or "")[:500]
    p.default_pattern = default_pattern or "gradient_teal"
    if logo and getattr(logo, "filename", None):
        data = await logo.read()
        if data and len(data) < 5_000_000:
            ext = (logo.filename.rsplit(".", 1)[-1] or "png").lower()[:4]
            name = f"logo_{pid}_{secrets.token_hex(4)}.{ext}"
            dest = UPLOAD_SLIDES / name
            dest.write_bytes(data)
            p.logo_path = f"/static/uploads/slides/{name}"
    session.add(p)
    session.commit()
    return RedirectResponse(f"/presentations/{pid}/edit", status_code=303)


@app.post("/presentations/{pid}/chart-from-file")
async def chart_from_file(
    pid: int,
    user: User = Depends(require_user),
    session: Session = Depends(get_session),
    datafile: UploadFile = File(...),
    chart_type: str = Form("bar"),
    chart_animation: str = Form("float3d"),
    slide_title: str = Form("Chart"),
):
    p = session.get(Presentation, pid)
    if not p or p.owner_id != user.id:
        raise HTTPException(404)
    raw = await datafile.read()
    fname = (datafile.filename or "").lower()
    labels, values = [], []
    if fname.endswith(".xlsx") or fname.endswith(".xlsm"):
        try:
            import openpyxl
            wb = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
            ws = wb.active
            for row in ws.iter_rows(values_only=True):
                if not row or row[0] is None:
                    continue
                lab = str(row[0]).strip()
                try:
                    val = float(row[1]) if len(row) > 1 and row[1] is not None else None
                except (TypeError, ValueError):
                    continue
                if lab and val is not None:
                    labels.append(lab[:40])
                    values.append(val)
        except Exception as e:
            raise HTTPException(400, f"Excel read error: {e}")
    elif fname.endswith(".csv") or fname.endswith(".txt"):
        text = raw.decode("utf-8", errors="ignore")
        for line in text.splitlines():
            parts = [x.strip() for x in line.replace(";", ",").split(",")]
            if len(parts) >= 2:
                try:
                    values.append(float(parts[1]))
                    labels.append(parts[0][:40])
                except ValueError:
                    continue
    elif fname.endswith(".pdf"):
        text = extract_text_from_upload(fname, raw)
        for m in re.finditer(r"([A-Za-z][A-Za-z0-9 /%\-]{1,30})\s*[:\|-]?\s*(\d+(?:\.\d+)?)", text):
            labels.append(m.group(1).strip()[:40])
            values.append(float(m.group(2)))
            if len(labels) >= 12:
                break
    else:
        raise HTTPException(400, "Upload .xlsx, .csv, or .pdf")
    if not labels:
        raise HTTPException(400, "No numeric data found in file")
    chart_data = ",".join(f"{l}:{v}" for l, v in zip(labels, values))
    n = len(session.exec(select(Slide).where(Slide.presentation_id == pid)).all())
    session.add(Slide(
        presentation_id=pid, position=n, title=slide_title or "Chart",
        body="Data visualisation", extra_data=chart_data,
        chart_type=chart_type or "bar", chart_data=chart_data,
        animation_in=chart_animation or "float3d", layout_style="chart",
        icon_name="chart", pattern="mesh_indigo",
    ))
    p.updated_at = datetime.utcnow()
    session.add(p)
    session.commit()
    return RedirectResponse(f"/presentations/{pid}/edit", status_code=303)



@app.get("/presentations/{pid}/present", response_class=HTMLResponse)
async def present_mode(
    pid: int, request: Request,
    user: User = Depends(require_user), session: Session = Depends(get_session),
):
    p = session.get(Presentation, pid)
    if not p or p.owner_id != user.id:
        raise HTTPException(404)
    slides = session.exec(
        select(Slide).where(Slide.presentation_id == pid).order_by(Slide.position)
    ).all()
    return templates.TemplateResponse("presenter/present.html", {
        "request": request, "user": user, "presentation": p, "slides": slides, "shared": False,
    })


@app.post("/api/eleon/ask")
async def eleon_ask(
    request: Request,
    session: Session = Depends(get_session),
):
    """Eleon probe: navigate, enhance, Q&A from all loaded slide information."""
    # Allow shared viewers without full user cookie for Q&A only
    user = user_from_request(request, session)
    try:
        data = await request.json()
    except Exception:
        data = {}
    q = (data.get("question") or data.get("q") or "").strip()
    pid = data.get("presentation_id")
    idx = int(data.get("slide_index") or 0)
    phase = (data.get("phase") or "present").lower()  # present | closing_qa
    ql = q.lower().strip()

    slides = []
    if pid:
        p = session.get(Presentation, int(pid))
        if p:
            if user and p.owner_id == user.id:
                pass
            elif p.share_token:
                pass
            elif not user:
                return JSONResponse({"ok": False, "speak": "Please sign in."})
            slides = session.exec(
                select(Slide).where(Slide.presentation_id == int(pid)).order_by(Slide.position)
            ).all()

    # Full corpus for Q&A
    corpus_parts = []
    for i, s in enumerate(slides):
        corpus_parts.append(f"Slide {i+1}: {s.title}\n{s.body}\n{s.extra_data}\n{s.notes}")
    full_text = "\n\n".join(corpus_parts).lower()

    def outside_knowledge():
        return JSONResponse({
            "ok": True,
            "action": "outside",
            "speak": "Sorry I can't help with that, however, my partner can.",
            "go_off": False,
        })

    # Closing phase — only Q&A, no nav required
    if phase == "closing_qa":
        if not q:
            return JSONResponse({"ok": True, "action": "speak", "speak": "Any questions?"})
        words = [w for w in re.findall(r"[a-z0-9']{3,}", ql)]
        score = sum(1 for w in words if w in full_text)
        if score < 1 or not slides:
            return outside_knowledge()
        best_i, best_score = 0, -1
        for i, s in enumerate(slides):
            text = f"{s.title} {s.body} {s.extra_data} {s.notes}".lower()
            sc = sum(1 for w in words if w in text)
            if sc > best_score:
                best_score, best_i = sc, i
        s = slides[best_i]
        ans = f"{(s.extra_data or s.body or s.title)[:450]}"
        return JSONResponse({"ok": True, "action": "speak", "speak": ans, "go_off": False})

    if not q:
        return JSONResponse({"ok": True, "action": "speak", "speak": "How may I help you?"})

    # Voice / text commands
    if ql in ("next", "next slide", "go next", "forward"):
        return JSONResponse({"ok": True, "action": "next", "speak": "Moving to the next slide."})
    if ql in ("previous", "prev", "back", "go back", "previous slide"):
        return JSONResponse({"ok": True, "action": "prev", "speak": "Going to the previous slide."})
    if ql in ("stay", "stay here", "current", "this slide"):
        return JSONResponse({"ok": True, "action": "stay", "speak": "Staying on this slide."})
    if ql in ("stop", "eleon stop", "pause", "hold"):
        return JSONResponse({"ok": True, "action": "stop", "speak": "Paused."})
    if ql in ("continue", "eleon continue", "resume"):
        return JSONResponse({"ok": True, "action": "continue", "speak": "Continuing."})
    if ql in ("start", "eleon start", "begin", "start autoplay", "start auto play"):
        return JSONResponse({"ok": True, "action": "start", "speak": "Starting presentation."})
    if ql in ("read", "read slide", "read the slide", "read this", "read this slide", "read everything", "what does this say"):
        return JSONResponse({"ok": True, "action": "read", "speak": ""})
    if ql in ("read all", "summarize", "summary", "overview"):
        return JSONResponse({"ok": True, "action": "read_all", "speak": ""})
    if "be attentive" in ql or ql in ("listen", "listen up", "pay attention"):
        return JSONResponse({"ok": True, "action": "listen", "speak": "I am attentive and listening."})
    if "thank you" in ql and "attention" in ql:
        return JSONResponse({"ok": True, "action": "closing", "speak": "Thank you for your attention. Any questions?"})
    if ql in ("end", "end presentation", "finish", "close presentation", "conclude"):
        return JSONResponse({"ok": True, "action": "closing", "speak": "Thank you for your attention. Any questions?"})
    if ql.startswith("go to slide") or (ql.startswith("slide ") and any(x.isdigit() for x in ql.split())):
        nums = [int(x) for x in ql.split() if x.isdigit()]
        if nums:
            return JSONResponse({"ok": True, "action": "goto", "index": max(0, nums[0]-1), "speak": f"Opening slide {nums[0]}."})
    # enhance commands
    enhance_map = {
        "make it teal": "accent_teal", "teal accent": "accent_teal",
        "gold accent": "accent_gold", "violet accent": "accent_violet",
        "dark background": "bg_dark", "indigo background": "bg_indigo",
        "zoom animation": "anim_zoom", "fade animation": "anim_fade",
        "slide animation": "anim_slide", "flip animation": "anim_flip",
    }
    for phrase, act in enhance_map.items():
        if phrase in ql:
            return JSONResponse({"ok": True, "action": "enhance", "enhance": act, "speak": f"Enhancing slide: {phrase}."})

    if "animation" in ql and ("in" in ql or "entrance" in ql):
        for anim in ("fade", "slideleft", "slideup", "zoom", "flip"):
            if anim in ql.replace(" ", ""):
                val = "slideLeft" if anim == "slideleft" else ("slideUp" if anim == "slideup" else anim)
                return JSONResponse({"ok": True, "action": "set_anim_in", "value": val, "speak": f"Entrance set to {val}."})
    if "animation" in ql and ("out" in ql or "exit" in ql):
        for anim in ("fade", "slideleft", "slideup", "zoom", "flip"):
            if anim in ql.replace(" ", ""):
                val = "slideLeft" if anim == "slideleft" else ("slideUp" if anim == "slideup" else anim)
                return JSONResponse({"ok": True, "action": "set_anim_out", "value": val, "speak": f"Exit set to {val}."})

    if not slides:
        return JSONResponse({"ok": True, "action": "speak", "speak": "No presentation data loaded yet."})

    words = [w for w in re.findall(r"[a-z0-9']{3,}", ql) if w not in ("what", "the", "and", "for", "about", "tell", "please", "from", "eleon")]
    best_i, best_score = idx, -1
    for i, s in enumerate(slides):
        text = f"{s.title} {s.body} {s.extra_data} {s.notes}".lower()
        score = sum(1 for w in words if w in text)
        if score > best_score:
            best_score, best_i = score, i
    if best_score <= 0:
        return outside_knowledge()
    s = slides[best_i]
    ans = f"{s.title}. {(s.extra_data or s.body or '')[:420]}"
    return JSONResponse({
        "ok": True,
        "action": "goto" if best_i != idx else "speak",
        "index": best_i,
        "speak": ans,
        "go_off": False,
    })



@app.post("/presentations/{pid}/import-document")
async def import_document(
    pid: int,
    document: UploadFile = File(...),
    user: User = Depends(require_user),
    session: Session = Depends(get_session),
):
    p = session.get(Presentation, pid)
    if not p or p.owner_id != user.id:
        raise HTTPException(404)
    data = await document.read()
    if len(data) > 15_000_000:
        raise HTTPException(400, "File too large (max 15MB)")
    text = extract_text_from_upload(document.filename or "doc.txt", data)
    payloads = document_to_slide_payloads(text)
    # replace existing slides
    old = session.exec(select(Slide).where(Slide.presentation_id == pid)).all()
    for s in old:
        session.delete(s)
    session.commit()
    for i, pl in enumerate(payloads):
        session.add(Slide(
            presentation_id=pid,
            position=i,
            title=pl["title"],
            body=pl["body"],
            extra_data=pl["extra_data"],
            animation_in="fade" if i < len(payloads) - 1 else "zoom",
            animation_out="fade",
        ))
    p.updated_at = datetime.utcnow()
    session.add(p)
    session.commit()
    return RedirectResponse(f"/presentations/{pid}/edit?imported=1", status_code=303)


@app.post("/api/slides/{sid}/enhance")
async def enhance_slide(
    sid: int,
    request: Request,
    user: User = Depends(require_user),
    session: Session = Depends(get_session),
):
    """Apply enhancement presets from side panel or Eleon voice."""
    try:
        data = await request.json()
    except Exception:
        data = {}
    s = session.get(Slide, sid)
    if not s:
        raise HTTPException(404)
    p = session.get(Presentation, s.presentation_id)
    if not p or p.owner_id != user.id:
        raise HTTPException(403)
    action = (data.get("action") or "").lower()
    if action == "accent_teal":
        s.accent = "#14b8a6"
    elif action == "accent_gold":
        s.accent = "#f59e0b"
    elif action == "accent_violet":
        s.accent = "#8b5cf6"
    elif action == "bg_dark":
        s.bg_color = "#0f172a"
    elif action == "bg_indigo":
        s.bg_color = "#1e1b4b"
    elif action == "bg_emerald":
        s.bg_color = "#064e3b"
    elif action == "anim_fade":
        s.animation_in, s.animation_out = "fade", "fade"
    elif action == "anim_zoom":
        s.animation_in, s.animation_out = "zoom", "fade"
    elif action == "anim_slide":
        s.animation_in, s.animation_out = "slideLeft", "slideUp"
    elif action == "anim_flip":
        s.animation_in, s.animation_out = "flip", "fade"
    elif action == "set_anim_in" and data.get("value"):
        s.animation_in = str(data["value"])
    elif action == "set_anim_out" and data.get("value"):
        s.animation_out = str(data["value"])
    elif action == "append_body" and data.get("text"):
        s.body = (s.body or "") + "\n" + str(data["text"])[:500]
    elif action == "append_extra" and data.get("text"):
        s.extra_data = (s.extra_data or "") + "\n" + str(data["text"])[:1000]
    else:
        return JSONResponse({"ok": False, "error": "unknown action"})
    p.updated_at = datetime.utcnow()
    session.add(s)
    session.add(p)
    session.commit()
    return JSONResponse({
        "ok": True,
        "slide": {
            "id": s.id, "title": s.title, "body": s.body, "extra_data": s.extra_data,
            "animation_in": s.animation_in, "animation_out": s.animation_out,
            "bg_color": s.bg_color, "accent": s.accent, "image_path": s.image_path,
        }
    })


@app.post("/presentations/{pid}/share")
async def enable_share(pid: int, user: User = Depends(require_user), session: Session = Depends(get_session)):
    p = session.get(Presentation, pid)
    if not p or p.owner_id != user.id:
        raise HTTPException(404)
    if not p.share_token:
        p.share_token = secrets.token_urlsafe(12)
    session.add(p)
    session.commit()
    return JSONResponse({"ok": True, "token": p.share_token, "url": f"/share/{p.share_token}"})


@app.get("/share/{token}", response_class=HTMLResponse)
async def shared_present(token: str, request: Request, session: Session = Depends(get_session)):
    p = session.exec(select(Presentation).where(Presentation.share_token == token)).first()
    if not p:
        raise HTTPException(404, "Link not found")
    slides = session.exec(select(Slide).where(Slide.presentation_id == p.id).order_by(Slide.position)).all()
    # guest present — limited eleon (read-only Q&A)
    return templates.TemplateResponse("presenter/present.html", {
        "request": request, "user": None, "presentation": p, "slides": slides, "shared": True,
    })


@app.get("/presentations/{pid}/export.pdf")
async def export_pdf(pid: int, user: User = Depends(require_user), session: Session = Depends(get_session)):
    p = session.get(Presentation, pid)
    if not p or p.owner_id != user.id:
        raise HTTPException(404)
    slides = session.exec(select(Slide).where(Slide.presentation_id == pid).order_by(Slide.position)).all()
    from reportlab.lib.pagesizes import landscape, A4
    from reportlab.pdfgen import canvas
    from reportlab.lib.units import mm
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=landscape(A4))
    w, h = landscape(A4)
    for i, s in enumerate(slides):
        c.setFillColorRGB(0.06, 0.09, 0.16)
        c.rect(0, 0, w, h, fill=1, stroke=0)
        c.setFillColorRGB(0.2, 0.9, 0.75)
        c.setFont("Helvetica-Bold", 11)
        c.drawString(30, h - 40, f"Eleon · {p.title} · Slide {i+1}")
        c.setFillColorRGB(1, 1, 1)
        c.setFont("Helvetica-Bold", 28)
        c.drawString(30, h - 90, (s.title or "Slide")[:80])
        c.setFont("Helvetica", 14)
        y = h - 130
        for line in (s.body or "").splitlines()[:18]:
            c.drawString(30, y, line[:100])
            y -= 20
        c.showPage()
    c.save()
    buf.seek(0)
    return StreamingResponse(buf, media_type="application/pdf", headers={
        "Content-Disposition": f'attachment; filename="eleon_{pid}.pdf"'
    })




@app.post("/presentations/{pid}/translate")
async def translate_presentation(
    pid: int,
    request: Request,
    user: User = Depends(require_user),
    session: Session = Depends(get_session),
):
    """Translate all slide text into target language (MyMemory free API)."""
    try:
        data = await request.json()
    except Exception:
        data = {}
    lang = (data.get("lang") or "es").strip().lower()[:5]
    p = session.get(Presentation, pid)
    if not p or p.owner_id != user.id:
        raise HTTPException(404)
    slides = session.exec(select(Slide).where(Slide.presentation_id == pid).order_by(Slide.position)).all()

    def tr(text: str) -> str:
        text = (text or "").strip()
        if not text:
            return text
        try:
            import urllib.parse, urllib.request, json as _json
            # chunk long text
            out = []
            for i in range(0, len(text), 400):
                chunk = text[i:i+400]
                q = urllib.parse.quote(chunk)
                url = f"https://api.mymemory.translated.net/get?q={q}&langpair=en|{lang}"
                with urllib.request.urlopen(url, timeout=12) as resp:
                    j = _json.loads(resp.read().decode())
                out.append(j.get("responseData", {}).get("translatedText") or chunk)
            return " ".join(out)
        except Exception:
            return text

    for s in slides:
        s.title = tr(s.title)[:200]
        s.body = tr(s.body)
        s.extra_data = tr(s.extra_data)
        s.notes = tr(s.notes)
        session.add(s)
    p.title = tr(p.title)[:200]
    p.updated_at = datetime.utcnow()
    session.add(p)
    session.commit()
    return JSONResponse({"ok": True, "lang": lang, "slides": len(slides)})



@app.get("/presentations/{pid}/export.pptx")
async def export_pptx(pid: int, user: User = Depends(require_user), session: Session = Depends(get_session)):
    p = session.get(Presentation, pid)
    if not p or p.owner_id != user.id:
        raise HTTPException(404)
    slides = session.exec(select(Slide).where(Slide.presentation_id == pid).order_by(Slide.position)).all()
    from app.pptx_export import build_pptx_bytes
    data = build_pptx_bytes(p.title or "Eleon", slides)
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={"Content-Disposition": f'attachment; filename="eleon_{pid}.pptx"'},
    )






def get_setting(session: Session, key: str, default: str = "") -> str:
    row = session.exec(select(AppSetting).where(AppSetting.key == key)).first()
    return row.value if row else default

def set_setting(session: Session, key: str, value: str) -> None:
    row = session.exec(select(AppSetting).where(AppSetting.key == key)).first()
    if row:
        row.value = value
        session.add(row)
    else:
        session.add(AppSetting(key=key, value=value))
    session.commit()


# ---------- Real-time live rooms (WebSocket) ----------
class LiveHub:
    def __init__(self):
        self.rooms: dict = {}  # token -> {"host": WebSocket|None, "viewers": {vid: ws}, "names": {vid: name}}

    def room(self, token: str) -> dict:
        if token not in self.rooms:
            self.rooms[token] = {"host": None, "viewers": {}, "names": {}}
        return self.rooms[token]

    async def broadcast(self, token: str, message: dict, skip: WebSocket = None):
        import json as _json
        data = _json.dumps(message)
        room = self.rooms.get(token) or {}
        targets = []
        if room.get("host"):
            targets.append(room["host"])
        targets.extend(room.get("viewers", {}).values())
        for ws in targets:
            if ws is skip:
                continue
            try:
                await ws.send_text(data)
            except Exception:
                pass

    def online_list(self, token: str) -> list:
        room = self.rooms.get(token) or {}
        out = []
        if room.get("host"):
            out.append({"role": "host", "name": "Presenter", "id": "host"})
        for vid, name in room.get("names", {}).items():
            if vid in room.get("viewers", {}):
                out.append({"role": "viewer", "name": name, "id": str(vid)})
        return out

live_hub = LiveHub()


@app.websocket("/ws/live/{token}")
async def ws_live(websocket: WebSocket, token: str):
    await websocket.accept()
    role = websocket.query_params.get("role") or "viewer"
    vid = websocket.query_params.get("vid") or ""
    name = websocket.query_params.get("name") or "Guest"
    room = live_hub.room(token)
    from sqlmodel import Session as S
    try:
        if role == "host":
            room["host"] = websocket
        else:
            room["viewers"][vid] = websocket
            room["names"][vid] = name
        await live_hub.broadcast(token, {"type": "online", "list": live_hub.online_list(token)})
        with S(engine) as sess:
            ls = sess.exec(select(LiveSession).where(LiveSession.token == token)).first()
            if ls:
                await websocket.send_json({"type": "slide", "index": ls.current_index})
        while True:
            raw = await websocket.receive_text()
            try:
                msg = __import__("json").loads(raw)
            except Exception:
                continue
            mtype = msg.get("type")
            if mtype == "slide" and role == "host":
                idx = int(msg.get("index") or 0)
                with S(engine) as sess:
                    ls = sess.exec(select(LiveSession).where(LiveSession.token == token)).first()
                    if ls:
                        ls.current_index = idx
                        sess.add(ls)
                        sess.commit()
                await live_hub.broadcast(token, {"type": "slide", "index": idx})  # all viewers
            elif mtype == "speak":
                # host Eleon speech text → all viewers TTS
                await live_hub.broadcast(token, {
                    "type": "speak",
                    "text": (msg.get("text") or "")[:4000],
                }, skip=None)
            elif mtype == "question" and role != "host":
                text = (msg.get("text") or "").strip()[:500]
                if not text:
                    continue
                with S(engine) as sess:
                    ls = sess.exec(select(LiveSession).where(LiveSession.token == token)).first()
                    if not ls:
                        continue
                    q = LiveQuestion(session_id=ls.id, viewer_name=name, text=text)
                    sess.add(q)
                    sess.commit()
                    sess.refresh(q)
                    qid = q.id
                await live_hub.broadcast(token, {
                    "type": "question",
                    "id": qid,
                    "name": name,
                    "text": text,
                })
            elif mtype == "ping":
                await websocket.send_json({"type": "pong"})

            elif mtype == "reaction":
                await live_hub.broadcast(token, {
                    "type": "reaction",
                    "emoji": msg.get("emoji") or "👏",
                    "name": name if role != "host" else (msg.get("name") or "Presenter"),
                })
            elif mtype == "voice_chunk":
                # real-time voice: host and attendees (presenter language only — no translate)
                await live_hub.broadcast(token, {
                    "type": "voice_chunk",
                    "audio": msg.get("audio") or "",
                    "mime": msg.get("mime") or "audio/webm",
                    "from": name if role != "host" else "Presenter",
                    "role": role,
                }, skip=websocket)
            elif mtype == "end" and role == "host":
                with S(engine) as sess:
                    ls = sess.exec(select(LiveSession).where(LiveSession.token == token)).first()
                    if ls:
                        ls.is_active = False
                        sess.add(ls)
                        sess.commit()
                await live_hub.broadcast(token, {"type": "ended", "message": "The presenter has ended the session."})

            elif mtype == "admit" and role == "host":
                await live_hub.broadcast(token, msg)
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        room = live_hub.rooms.get(token)
        if room:
            if role == "host" and room.get("host") is websocket:
                room["host"] = None
            if vid in room.get("viewers", {}):
                room["viewers"].pop(vid, None)
                room["names"].pop(vid, None)
            try:
                await live_hub.broadcast(token, {"type": "online", "list": live_hub.online_list(token)})
            except Exception:
                pass



# ---------- Live join / audience ----------
@app.post("/presentations/{pid}/live/start")
async def live_start(pid: int, user: User = Depends(require_user), session: Session = Depends(get_session)):
    p = session.get(Presentation, pid)
    if not p or p.owner_id != user.id:
        raise HTTPException(404)
    # reuse active or create
    existing = session.exec(
        select(LiveSession).where(LiveSession.presentation_id == pid, LiveSession.is_active == True)
    ).first()
    if existing:
        return JSONResponse({"ok": True, "token": existing.token, "url": f"/join/{existing.token}"})
    token = secrets.token_urlsafe(10)
    ls = LiveSession(presentation_id=pid, owner_id=user.id, token=token, current_index=0)
    session.add(ls)
    session.commit()
    return JSONResponse({"ok": True, "token": token, "url": f"/join/{token}"})


@app.post("/presentations/{pid}/live/stop")
async def live_stop(pid: int, user: User = Depends(require_user), session: Session = Depends(get_session)):
    rows = session.exec(select(LiveSession).where(LiveSession.presentation_id == pid, LiveSession.owner_id == user.id)).all()
    for ls in rows:
        ls.is_active = False
        session.add(ls)
        try:
            await live_hub.broadcast(ls.token, {"type": "ended", "message": "The presenter has ended the session."})
        except Exception:
            pass
    session.commit()
    return JSONResponse({"ok": True})


@app.post("/api/live/{token}/sync")
async def live_sync(token: str, request: Request, session: Session = Depends(get_session)):
    """Host pushes current slide index — also notifies WebSocket viewers."""
    user = user_from_request(request, session)
    ls = session.exec(select(LiveSession).where(LiveSession.token == token, LiveSession.is_active == True)).first()
    if not ls:
        raise HTTPException(404)
    if not user or ls.owner_id != user.id:
        raise HTTPException(403)
    try:
        data = await request.json()
    except Exception:
        data = {}
    idx = int(data.get("index") or 0)
    ls.current_index = idx
    session.add(ls)
    session.commit()
    try:
        await live_hub.broadcast(token, {"type": "slide", "index": idx})
    except Exception:
        pass
    return JSONResponse({"ok": True, "index": idx})


@app.get("/api/live/{token}/state")
async def live_state(token: str, session: Session = Depends(get_session)):
    ls = session.exec(select(LiveSession).where(LiveSession.token == token)).first()
    if not ls:
        raise HTTPException(404)
    p = session.get(Presentation, ls.presentation_id)
    slides = session.exec(select(Slide).where(Slide.presentation_id == ls.presentation_id).order_by(Slide.position)).all()
    pending = session.exec(select(LiveViewer).where(LiveViewer.session_id == ls.id, LiveViewer.status == "pending")).all()
    questions = session.exec(
        select(LiveQuestion).where(LiveQuestion.session_id == ls.id, LiveQuestion.answered == False).order_by(LiveQuestion.created_at)
    ).all()
    return JSONResponse({
        "ok": True,
        "active": ls.is_active,
        "index": ls.current_index,
        "title": p.title if p else "",
        "pending": [{"id": v.id, "name": v.name} for v in pending],
        "questions": [{"id": q.id, "name": q.viewer_name, "text": q.text} for q in questions],
        "slides": [
            {
                "title": s.title, "body": s.body, "extra": s.extra_data, "notes": s.notes,
                "image": s.image_path, "onlineImage": s.online_image_url,
                "animIn": s.animation_in, "bg": s.bg_color, "accent": s.accent,
                "layout": s.layout_style, "icon": s.icon_name, "chartType": s.chart_type,
                "chartData": s.chart_data, "pattern": getattr(s, "pattern", None) or "gradient_teal",
                "imageStyle": getattr(s, "image_style", None) or "frame",
            }
            for s in slides
        ],
    })


@app.get("/join/{token}", response_class=HTMLResponse)
async def join_page(token: str, request: Request, session: Session = Depends(get_session)):
    ls = session.exec(select(LiveSession).where(LiveSession.token == token)).first()
    dl = get_setting(session, "eleon_download_url", "https://knowsoftconsult.com")
    android = get_setting(session, "eleon_android_url", "") or dl
    windows = get_setting(session, "eleon_windows_url", "") or dl
    if not ls or not ls.is_active:
        return templates.TemplateResponse("presenter/join_expired.html", {
            "request": request, "token": token,
            "download_url": dl, "android_url": android, "windows_url": windows,
        })
    p = session.get(Presentation, ls.presentation_id)
    return templates.TemplateResponse("presenter/join.html", {
        "request": request, "token": token, "presentation": p, "live": ls,
        "download_url": dl, "android_url": android, "windows_url": windows,
    })


@app.post("/join/{token}")
async def join_request(token: str, name: str = Form(...), session: Session = Depends(get_session)):
    ls = session.exec(select(LiveSession).where(LiveSession.token == token, LiveSession.is_active == True)).first()
    if not ls:
        raise HTTPException(404)
    v = LiveViewer(session_id=ls.id, name=(name or "Guest").strip()[:80], status="pending")
    session.add(v)
    session.commit()
    session.refresh(v)
    # notify host rooms immediately (best-effort)
    try:
        import asyncio
        asyncio.get_event_loop().create_task(hub.broadcast(token, {
            "type": "join_request", "vid": v.id, "name": v.name
        }))
    except Exception:
        pass
    return RedirectResponse(f"/join/{token}/wait?vid={v.id}", status_code=303)


@app.get("/join/{token}/wait", response_class=HTMLResponse)
async def join_wait(token: str, request: Request, session: Session = Depends(get_session)):
    vid = request.query_params.get("vid")
    return templates.TemplateResponse("presenter/join_wait.html", {
        "request": request, "token": token, "vid": vid,
    })


@app.get("/api/join/{token}/viewer/{vid}")
async def join_viewer_status(token: str, vid: int, session: Session = Depends(get_session)):
    ls = session.exec(select(LiveSession).where(LiveSession.token == token)).first()
    if not ls:
        raise HTTPException(404)
    v = session.get(LiveViewer, vid)
    if not v or v.session_id != ls.id:
        raise HTTPException(404)
    return JSONResponse({"ok": True, "status": v.status, "name": v.name, "index": ls.current_index, "active": ls.is_active})


@app.post("/api/live/{token}/admit/{vid}")
async def live_admit(token: str, vid: int, request: Request, session: Session = Depends(get_session)):
    user = user_from_request(request, session)
    ls = session.exec(select(LiveSession).where(LiveSession.token == token)).first()
    if not ls or not user or ls.owner_id != user.id:
        raise HTTPException(403)
    v = session.get(LiveViewer, vid)
    if not v or v.session_id != ls.id:
        raise HTTPException(404)
    try:
        data = await request.json()
    except Exception:
        data = {}
    v.status = "admitted" if data.get("admit", True) else "denied"
    session.add(v)
    session.commit()
    return JSONResponse({"ok": True, "status": v.status})


@app.get("/join/{token}/watch", response_class=HTMLResponse)
async def join_watch(token: str, request: Request, session: Session = Depends(get_session)):
    vid = request.query_params.get("vid")
    ls = session.exec(select(LiveSession).where(LiveSession.token == token, LiveSession.is_active == True)).first()
    if not ls:
        raise HTTPException(404)
    v = session.get(LiveViewer, int(vid)) if vid else None
    if not v or v.session_id != ls.id or v.status != "admitted":
        return RedirectResponse(f"/join/{token}/wait?vid={vid}", status_code=303)
    p = session.get(Presentation, ls.presentation_id)
    return templates.TemplateResponse("presenter/join_watch.html", {
        "request": request, "token": token, "vid": vid, "viewer": v, "presentation": p,
    })


@app.post("/api/join/{token}/ask")
async def join_ask(token: str, request: Request, session: Session = Depends(get_session)):
    ls = session.exec(select(LiveSession).where(LiveSession.token == token, LiveSession.is_active == True)).first()
    if not ls:
        raise HTTPException(404)
    try:
        data = await request.json()
    except Exception:
        data = {}
    text = (data.get("text") or "").strip()[:500]
    name = (data.get("name") or "Guest").strip()[:80]
    if not text:
        raise HTTPException(400, "Empty question")
    q = LiveQuestion(session_id=ls.id, viewer_name=name, text=text)
    session.add(q)
    session.commit()
    session.refresh(q)
    return JSONResponse({"ok": True, "id": q.id})


@app.post("/api/live/{token}/answer/{qid}")
async def live_answer_question(token: str, qid: int, request: Request, session: Session = Depends(get_session)):
    user = user_from_request(request, session)
    ls = session.exec(select(LiveSession).where(LiveSession.token == token)).first()
    if not ls or not user or ls.owner_id != user.id:
        raise HTTPException(403)
    q = session.get(LiveQuestion, qid)
    if not q or q.session_id != ls.id:
        raise HTTPException(404)
    try:
        data = await request.json()
    except Exception:
        data = {}
    answer = (data.get("answer") or "").strip()[:2000]
    q.answered = True
    q.answer = answer
    session.add(q)
    session.commit()
    # also store as QA note
    session.add(PresentationQANote(presentation_id=ls.presentation_id, question=f"{q.viewer_name}: {q.text}", answer=answer))
    session.commit()
    return JSONResponse({"ok": True})


# ---------- Evaluation & Q&A notes ----------
@app.post("/api/presentations/{pid}/qa-note")
async def save_qa_note(pid: int, request: Request, session: Session = Depends(get_session)):
    try:
        data = await request.json()
    except Exception:
        data = {}
    user = user_from_request(request, session)
    p = session.get(Presentation, pid)
    if not p:
        raise HTTPException(404)
    if user and p.owner_id != user.id and not p.share_token:
        raise HTTPException(403)
    note = PresentationQANote(
        presentation_id=pid,
        question=(data.get("question") or "")[:2000],
        answer=(data.get("answer") or "")[:4000],
    )
    session.add(note)
    session.commit()
    return JSONResponse({"ok": True, "id": note.id})


@app.get("/presentations/{pid}/qa-notes", response_class=HTMLResponse)
async def list_qa_notes(pid: int, request: Request, user: User = Depends(require_user), session: Session = Depends(get_session)):
    p = session.get(Presentation, pid)
    if not p or p.owner_id != user.id:
        raise HTTPException(404)
    notes = session.exec(
        select(PresentationQANote).where(PresentationQANote.presentation_id == pid).order_by(PresentationQANote.created_at.desc())
    ).all()
    return templates.TemplateResponse("presenter/qa_notes.html", {
        "request": request, "user": user, "presentation": p, "notes": notes,
    })


@app.post("/presentations/{pid}/evaluation/create")
async def create_evaluation(pid: int, user: User = Depends(require_user), session: Session = Depends(get_session)):
    p = session.get(Presentation, pid)
    if not p or p.owner_id != user.id:
        raise HTTPException(404)
    token = secrets.token_urlsafe(10)
    ev = EvalSession(presentation_id=pid, owner_id=user.id, title=f"Eval — {p.title}", token=token)
    session.add(ev)
    session.commit()
    session.refresh(ev)
    # Auto questions from slides
    slides = session.exec(select(Slide).where(Slide.presentation_id == pid).order_by(Slide.position)).all()
    pos = 0
    for s in slides[:8]:
        if not (s.title or s.body):
            continue
        prompt = f"What is a key point from: {(s.title or '')[:80]}?"
        session.add(EvalQuestion(session_id=ev.id, position=pos, prompt=prompt, options="", correct_answer=""))
        pos += 1
    if pos == 0:
        session.add(EvalQuestion(session_id=ev.id, position=0, prompt="How useful was this training? (1-5)", options="1\n2\n3\n4\n5", correct_answer=""))
        session.add(EvalQuestion(session_id=ev.id, position=1, prompt="Would you recommend this session?", options="Yes\nNo\nMaybe", correct_answer=""))
    session.commit()
    return RedirectResponse(f"/presentations/{pid}/evaluation/{ev.id}", status_code=303)


@app.post("/presentations/{pid}/evaluation/{eid}/questions")
async def add_eval_question(
    pid: int, eid: int,
    prompt: str = Form(...),
    options: str = Form(""),
    correct_answer: str = Form(""),
    user: User = Depends(require_user),
    session: Session = Depends(get_session),
):
    ev = session.get(EvalSession, eid)
    p = session.get(Presentation, pid)
    if not ev or not p or p.owner_id != user.id or ev.presentation_id != pid:
        raise HTTPException(404)
    n = len(session.exec(select(EvalQuestion).where(EvalQuestion.session_id == eid)).all())
    session.add(EvalQuestion(session_id=eid, position=n, prompt=prompt, options=options, correct_answer=correct_answer.strip()))
    session.commit()
    return RedirectResponse(f"/presentations/{pid}/evaluation/{eid}", status_code=303)


@app.get("/presentations/{pid}/evaluation/{eid}", response_class=HTMLResponse)
async def evaluation_admin(pid: int, eid: int, request: Request, user: User = Depends(require_user), session: Session = Depends(get_session)):
    ev = session.get(EvalSession, eid)
    p = session.get(Presentation, pid)
    if not ev or not p or p.owner_id != user.id or ev.presentation_id != pid:
        raise HTTPException(404)
    qs = session.exec(select(EvalQuestion).where(EvalQuestion.session_id == eid).order_by(EvalQuestion.position)).all()
    resps = session.exec(select(EvalResponse).where(EvalResponse.session_id == eid).order_by(EvalResponse.submitted_at.desc())).all()
    return templates.TemplateResponse("presenter/evaluation.html", {
        "request": request, "user": user, "presentation": p, "eval": ev, "questions": qs, "responses": resps,
    })


@app.get("/presentations/{pid}/evaluation/{eid}/live", response_class=HTMLResponse)
async def evaluation_live(pid: int, eid: int, request: Request, user: User = Depends(require_user), session: Session = Depends(get_session)):
    ev = session.get(EvalSession, eid)
    p = session.get(Presentation, pid)
    if not ev or not p or p.owner_id != user.id:
        raise HTTPException(404)
    return templates.TemplateResponse("presenter/evaluation_live.html", {
        "request": request, "user": user, "presentation": p, "eval": ev,
    })


@app.get("/api/evaluation/{token}/responses")
async def eval_responses_public(token: str, session: Session = Depends(get_session)):
    ev = session.exec(select(EvalSession).where(EvalSession.token == token)).first()
    if not ev:
        raise HTTPException(404)
    resps = session.exec(select(EvalResponse).where(EvalResponse.session_id == ev.id).order_by(EvalResponse.submitted_at.desc())).all()
    return JSONResponse({
        "ok": True,
        "items": [{"name": r.participant_name, "email": r.participant_email, "score": r.score_pct, "at": r.submitted_at.isoformat()} for r in resps],
    })


@app.get("/api/evaluation/{eid}/results")
async def eval_results(eid: int, user: User = Depends(require_user), session: Session = Depends(get_session)):
    ev = session.get(EvalSession, eid)
    if not ev or ev.owner_id != user.id:
        raise HTTPException(404)
    resps = session.exec(select(EvalResponse).where(EvalResponse.session_id == eid)).all()
    bands = {"90-100": 0, "60-89": 0, "30-59": 0, "0-29": 0}
    for r in resps:
        s = r.score_pct
        if s >= 90: bands["90-100"] += 1
        elif s >= 60: bands["60-89"] += 1
        elif s >= 30: bands["30-59"] += 1
        else: bands["0-29"] += 1
    return JSONResponse({
        "ok": True,
        "bands": bands,
        "participants": [{"name": r.participant_name, "email": r.participant_email, "score": r.score_pct} for r in resps],
    })


@app.get("/evaluate/{token}", response_class=HTMLResponse)
async def evaluate_form(token: str, request: Request, session: Session = Depends(get_session)):
    ev = session.exec(select(EvalSession).where(EvalSession.token == token, EvalSession.is_active == True)).first()
    if not ev:
        raise HTTPException(404, "Evaluation not found or closed")
    qs = session.exec(select(EvalQuestion).where(EvalQuestion.session_id == ev.id).order_by(EvalQuestion.position)).all()
    p = session.get(Presentation, ev.presentation_id)
    return templates.TemplateResponse("presenter/evaluate_take.html", {
        "request": request, "eval": ev, "questions": qs, "presentation": p,
    })


@app.post("/evaluate/{token}")
async def evaluate_submit(token: str, request: Request, session: Session = Depends(get_session)):
    ev = session.exec(select(EvalSession).where(EvalSession.token == token, EvalSession.is_active == True)).first()
    if not ev:
        raise HTTPException(404)
    form = await request.form()
    name = (form.get("participant_name") or "Guest").strip()[:120]
    email = (form.get("participant_email") or "").strip()[:200]
    qs = session.exec(select(EvalQuestion).where(EvalQuestion.session_id == ev.id).order_by(EvalQuestion.position)).all()
    answers = {}
    scored = 0
    correct = 0
    for q in qs:
        ans = (form.get(f"q_{q.id}") or "").strip()
        answers[str(q.id)] = ans
        if q.correct_answer:
            scored += 1
            if ans.lower() == q.correct_answer.lower():
                correct += 1
    pct = (100.0 * correct / scored) if scored else 100.0
    session.add(EvalResponse(session_id=ev.id, participant_name=name, participant_email=email,
                             answers_json=__import__("json").dumps(answers), score_pct=round(pct, 1)))
    session.commit()
    return templates.TemplateResponse("presenter/evaluate_done.html", {
        "request": request, "eval": ev, "name": name, "score": round(pct, 1), "token": token,
        "allow_certificates": getattr(ev, "allow_certificates", True),
    })



@app.post("/presentations/{pid}/evaluation/{eid}/cert-policy")
async def eval_cert_policy(
    pid: int, eid: int,
    allow_certificates: str = Form("on"),
    user: User = Depends(require_user),
    session: Session = Depends(get_session),
):
    ev = session.get(EvalSession, eid)
    p = session.get(Presentation, pid)
    if not ev or not p or p.owner_id != user.id or ev.presentation_id != pid:
        raise HTTPException(404)
    ev.allow_certificates = allow_certificates in ("on", "true", "1", "yes")
    session.add(ev)
    session.commit()
    return RedirectResponse(f"/presentations/{pid}/evaluation/{eid}", status_code=303)


@app.get("/evaluate/{token}/certificate")
async def evaluate_certificate(token: str, request: Request, session: Session = Depends(get_session)):
    name = (request.query_params.get("name") or "Participant").strip()[:120]
    ev = session.exec(select(EvalSession).where(EvalSession.token == token)).first()
    if not ev:
        raise HTTPException(404)
    # Link users need presenter permission; presenter (owner) always can open with ?host=1
    host_dl = request.query_params.get("host") == "1"
    if not host_dl and not getattr(ev, "allow_certificates", True):
        raise HTTPException(403, "Certificates are disabled for this evaluation")
    p = session.get(Presentation, ev.presentation_id)
    return templates.TemplateResponse("presenter/certificate.html", {
        "request": request, "name": name, "eval": ev, "presentation": p,
    })




@app.websocket("/ws/live/{token}")
async def ws_live(websocket: WebSocket, token: str):
    """Real-time channel: host + admitted viewers."""
    role = websocket.query_params.get("role") or "viewer"
    vid = websocket.query_params.get("vid")
    await hub.connect(token, websocket, role=role)
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = __import__("json").loads(raw)
            except Exception:
                continue
            mtype = msg.get("type")
            # Host slide / speech
            if mtype in ("slide", "speak", "speak_end", "phase"):
                if role != "host":
                    continue
                await hub.broadcast(token, msg, exclude=None)
            elif mtype == "question":
                # viewer question — persist + fan out immediately
                from sqlmodel import Session as S
                from app.database import engine
                text = (msg.get("text") or "")[:500]
                name = (msg.get("name") or "Guest")[:80]
                qid = None
                with S(engine) as session:
                    ls = session.exec(select(LiveSession).where(LiveSession.token == token)).first()
                    if ls and text:
                        q = LiveQuestion(session_id=ls.id, viewer_name=name, text=text)
                        session.add(q)
                        session.commit()
                        session.refresh(q)
                        qid = q.id
                await hub.broadcast(token, {
                    "type": "question",
                    "id": qid,
                    "name": name,
                    "text": text,
                })
            elif mtype == "admit":
                if role != "host":
                    continue
                from sqlmodel import Session as S
                from app.database import engine
                with S(engine) as session:
                    v = session.get(LiveViewer, int(msg.get("vid") or 0))
                    if v:
                        v.status = "admitted" if msg.get("admit", True) else "denied"
                        session.add(v)
                        session.commit()
                await hub.broadcast(token, {
                    "type": "admit_result",
                    "vid": msg.get("vid"),
                    "status": "admitted" if msg.get("admit", True) else "denied",
                    "name": msg.get("name") or "",
                })
            elif mtype == "answer_done":
                if role != "host":
                    continue
                await hub.broadcast(token, msg)
            elif mtype == "join_request":
                # optional notify host of new pending (DB already has viewer)
                await hub.broadcast(token, {
                    "type": "join_request",
                    "vid": msg.get("vid"),
                    "name": msg.get("name") or "Guest",
                })
            elif mtype == "ping":
                await websocket.send_text('{"type":"pong"}')
    except WebSocketDisconnect:
        await hub.disconnect(token, websocket)
    except Exception:
        await hub.disconnect(token, websocket)




@app.get("/admin/settings", response_class=HTMLResponse)
async def admin_settings_page(request: Request, user: User = Depends(require_admin), session: Session = Depends(get_session)):
    dl = get_setting(session, "eleon_download_url", "https://knowsoftconsult.com")
    android = get_setting(session, "eleon_android_url", "")
    ios = get_setting(session, "eleon_ios_url", "")
    windows = get_setting(session, "eleon_windows_url", "")
    return templates.TemplateResponse("admin/settings.html", {
        "request": request, "user": user,
        "download_url": dl, "android_url": android, "ios_url": ios, "windows_url": windows,
    })


@app.post("/admin/settings")
async def admin_settings_save(
    request: Request,
    user: User = Depends(require_admin),
    session: Session = Depends(get_session),
    download_url: str = Form(""),
    android_url: str = Form(""),
    ios_url: str = Form(""),
    windows_url: str = Form(""),
):
    set_setting(session, "eleon_download_url", download_url.strip())
    set_setting(session, "eleon_android_url", android_url.strip())
    set_setting(session, "eleon_ios_url", ios_url.strip())
    set_setting(session, "eleon_windows_url", windows_url.strip())
    return RedirectResponse("/admin/settings", status_code=303)


@app.get("/api/download-links")
async def api_download_links(session: Session = Depends(get_session)):
    return JSONResponse({
        "download_url": get_setting(session, "eleon_download_url", "https://knowsoftconsult.com"),
        "android_url": get_setting(session, "eleon_android_url", ""),
        "ios_url": get_setting(session, "eleon_ios_url", ""),
        "windows_url": get_setting(session, "eleon_windows_url", ""),
        "app_scheme": "eleon://join/",
    })


@app.post("/api/translate-text")
async def api_translate_text(request: Request):
    try:
        data = await request.json()
    except Exception:
        data = {}
    text = (data.get("text") or "")[:2500]
    lang = (data.get("lang") or "es")[:5]
    if not text:
        return JSONResponse({"ok": True, "text": ""})
    try:
        import urllib.parse, urllib.request, json as _json
        out = []
        for i in range(0, len(text), 400):
            chunk = text[i:i+400]
            q = urllib.parse.quote(chunk)
            url = f"https://api.mymemory.translated.net/get?q={q}&langpair=en|{lang}"
            with urllib.request.urlopen(url, timeout=12) as resp:
                j = _json.loads(resp.read().decode())
            out.append(j.get("responseData", {}).get("translatedText") or chunk)
        return JSONResponse({"ok": True, "text": " ".join(out)})
    except Exception as e:
        return JSONResponse({"ok": False, "text": text, "error": str(e)})


# ---------- Admin ----------
@app.get("/admin", response_class=HTMLResponse)
async def admin_home(request: Request, user: User = Depends(require_admin), session: Session = Depends(get_session)):
    pending = session.exec(select(User).where(User.status == UserStatus.pending)).all()
    users = session.exec(select(User).order_by(User.created_at.desc())).all()
    codes = session.exec(select(LoginCode).order_by(LoginCode.created_at.desc()).limit(40)).all()
    return templates.TemplateResponse("admin/dashboard.html", {
        "request": request, "user": user, "pending": pending, "users": users, "codes": codes,
    })


@app.post("/admin/approve/{uid}")
async def admin_approve(uid: int, duration: str = Form("month"), user: User = Depends(require_admin), session: Session = Depends(get_session)):
    target = session.get(User, uid)
    if not target:
        raise HTTPException(404)
    target.status = UserStatus.approved
    if not target.login_number:
        target.login_number = gen_login_number()
    days = DURATION_DAYS.get(duration, 30)
    target.access_expires_at = datetime.utcnow() + timedelta(days=days)
    session.add(target)
    session.commit()
    return RedirectResponse("/admin", status_code=303)


@app.post("/admin/suspend/{uid}")
async def admin_suspend(uid: int, user: User = Depends(require_admin), session: Session = Depends(get_session)):
    target = session.get(User, uid)
    if target and target.role != UserRole.general_admin:
        target.status = UserStatus.suspended
        session.add(target)
        session.commit()
    return RedirectResponse("/admin", status_code=303)


@app.post("/admin/codes/issue")
async def issue_code(
    duration: str = Form("month"),
    notes: str = Form(""),
    email: str = Form(""),
    user: User = Depends(require_admin),
    session: Session = Depends(get_session),
):
    if duration not in DURATION_DAYS:
        duration = "month"
    code = LoginCode(
        code=gen_code(),
        duration=duration,
        notes=notes,
        issued_to_email=email.strip().lower() or None,
        created_by=user.id,
    )
    session.add(code)
    session.commit()
    return RedirectResponse("/admin?code=" + code.code, status_code=303)


@app.post("/admin/extend/{uid}")
async def extend_access(
    uid: int,
    duration: str = Form("month"),
    user: User = Depends(require_admin),
    session: Session = Depends(get_session),
):
    target = session.get(User, uid)
    if not target:
        raise HTTPException(404)
    days = DURATION_DAYS.get(duration, 30)
    base = target.access_expires_at if target.access_expires_at and target.access_expires_at > datetime.utcnow() else datetime.utcnow()
    target.access_expires_at = base + timedelta(days=days)
    target.status = UserStatus.approved
    session.add(target)
    session.commit()
    return RedirectResponse("/admin", status_code=303)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
