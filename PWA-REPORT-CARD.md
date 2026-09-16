# Eleon PWA Report Card — PWABuilder package notes

**App URL:** https://eleon-2ufh.onrender.com  
**Brand:** Knowsoft · Eleon — Your Presentation Partner  

## 1. PWABuilder steps

1. Open [https://www.pwabuilder.com](https://www.pwabuilder.com)
2. Enter: `https://eleon-2ufh.onrender.com`
3. Wait for the score / report card
4. Package:
   - **Android** → Trusted Web Activity / Play package
   - **Windows** → Microsoft Store / desktop
   - **Other** as offered

## 2. Manifest (served at)

- `https://eleon-2ufh.onrender.com/manifest.webmanifest`
- Also: `/manifest.json`

### Required fields present

| Field | Value |
|-------|--------|
| name | Eleon — Knowsoft Presentation Partner |
| short_name | Eleon |
| start_url | /?source=pwa |
| display | standalone |
| theme_color | #0f172a |
| background_color | #0f172a |
| icons | 48–512 + maskable 192/512 |
| screenshots | included for store listing |
| categories | productivity, education, business |

## 3. Icons (all from your attached Eleon app icon)

| File | Size | Use |
|------|------|-----|
| /static/icons/icon-48.png | 48 | Taskbar / favicon |
| /static/icons/icon-72.png | 72 | Android |
| /static/icons/icon-96.png | 96 | Android |
| /static/icons/icon-128.png | 128 | Desktop |
| /static/icons/icon-144.png | 144 | Windows |
| /static/icons/icon-152.png | 152 | iOS |
| /static/icons/apple-touch-icon.png | 180 | iOS home |
| /static/icons/icon-192.png | 192 | PWA any |
| /static/icons/icon-256.png | 256 | Desktop |
| /static/icons/icon-384.png | 384 | Splash |
| /static/icons/icon-512.png | 512 | PWA / store |
| /static/icons/icon-maskable-192.png | 192 | Android adaptive |
| /static/icons/icon-maskable-512.png | 512 | Android adaptive |
| /static/icons/splash-512.png | 512 | Screenshot placeholder |

**Logo (headers):** `/static/img/knowsoft-logo.png` (your Knowsoft wordmark)

## 4. Service worker

- URL: `https://eleon-2ufh.onrender.com/static/sw.js` (or `/sw.js` if routed)
- Caches shell + `/static/` assets for offline tolerance

## 5. HTTPS / installability

- Host is Render → **HTTPS** ✓
- Manifest linked in present/editor templates
- `apple-mobile-web-app-capable` meta on present page

## 6. Original PPT through the installed app

| Capability | In browser / PWA app |
|------------|----------------------|
| Upload / Store original `.pptx` | Yes |
| PPT studio (structure + Eleon speak scripts) | Yes |
| Present with Eleon probe, autoplay voice, transitions | Yes — **Eleon PPT live** |
| Download original file to open in PowerPoint | Yes |
| Pixel-perfect native PowerPoint engine inside the app | No (OS PowerPoint/LibreOffice after download) |
| Offline HTML pack of converted deck | Yes — **Offline pack** |

**Recommended flow inside the PWA:**

1. Open Eleon (installed app or site)  
2. **Store PPT** or Import  
3. **Present original PPT** → studio → scripts  
4. **Present →** Eleon PPT live (probe + voice + transitions)  

Or download the original file and open in PowerPoint on the device for true native slides; use Eleon for voice scripts and converted/structured present.

## 7. Store listing text (suggested)

**Name:** Eleon  
**Subtitle:** Your Presentation Partner by Knowsoft  
**Description:**  
Eleon helps you design and present slides with live charts, images, and a voice-enabled probe. Import documents and PowerPoint files, prepare speak-scripts per slide, present online, or download an offline pack. Built by Knowsoft.

## 8. After deploy checklist

- [ ] Open `/manifest.webmanifest` in browser — JSON loads  
- [ ] Open `/static/icons/icon-512.png` — Eleon icon shows  
- [ ] Chrome → Application → Manifest — no errors  
- [ ] PWABuilder score re-run on production URL  
- [ ] Test **Present original PPT** on phone after “Add to Home Screen”

---
Generated for Knowsoft Eleon · https://eleon-2ufh.onrender.com
