# Eleon — Your presentation partner

Knowsoft / Churchgate-family branding.

## Highlights

- Splash: *Welcome to Eleon… your presentation partner*
- Register + admin **week / month / year** access codes + login numbers
- **Import PDF/TXT/MD** → auto-analysed into slides (+ thank-you slide)
- Side **Enhance** buttons (editor + present mode)
- **Eleon** voice/text: navigate, enhance, Q&A from all loaded content
- Closing: *Thank you for your attention. Any questions?* → wait **60s** → off
- Outside knowledge: *Sorry I can't help with that, however, my partner can respond to that* → off
- Export **PDF**, **share link**

## Run

```bash
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000
```

Admin: `admin@eleon.knowsoft` / `Eleon#Admin2026!`


## Render.com settings (important)

Do **not** use `gunicorn app:app` (that looks for a WSGI `app` inside the `app` package).

**Build command:**
```
pip install -r requirements.txt
```

**Start command:**
```
uvicorn main:app --host 0.0.0.0 --port $PORT
```

Or:
```
uvicorn asgi:app --host 0.0.0.0 --port $PORT
```

Prefer Python **3.12** if 3.14 causes wheel issues.
