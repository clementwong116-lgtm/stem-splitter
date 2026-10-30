# Deploy status (2026-10-30 Asia/Hong_Kong)

## Public HTTPS URL
**Not live yet** — blocked on hosting account auth.

Local on box (not phone-reachable): `http://127.0.0.1:8765/` — OK, `provider=ffmpeg`, `pwa=true`.

## Tunnel attempts (failed)
cloudflared / localtunnel / bore / SSH reverse all fail on box egress. No trycloudflare URL usable.

## Deploy files ready (`/workspace/stem-splitter/`)
Dockerfile, Procfile, railway.toml, render.yaml, .dockerignore, requirements-deploy.txt, DEPLOY.md

## Auth — do this next

### Preferred: Railway (no GitHub needed; CLI waiting)
1. User opens: https://railway.com/activate?user_code=MBWC-HXDN
2. Code: **MBWC-HXDN** (box process `railway login --browserless` waiting)
3. After auth, parent/executor runs: `cd /workspace/stem-splitter && railway init && railway up` + Generate Domain
4. Optional env: `STEMSPLIT_API_KEY` (omit → ffmpeg mid/side)

### Alt: GitHub + Render
Cursor GitHub connector **needsAuth** — connect card already shown. Then push repo → Render Docker free service.

## Limitations
ffmpeg mid/side until STEMSPLIT_API_KEY set server-side; free Render sleeps; PWA needs HTTPS.
