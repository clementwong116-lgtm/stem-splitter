# Deploy Stem Splitter PWA

HTTPS is required for PWA install on phones. Keep `STEMSPLIT_API_KEY` server-side only (env/secrets).

## Runtime defaults (no API key)

Without `STEMSPLIT_API_KEY`, the app uses **ffmpeg mid/side** fallback (`STEM_PROVIDER=ffmpeg` or `auto`). Quality is lower than StemSplit/Demucs but works offline on free hosts.

Optional later: set `STEMSPLIT_API_KEY` in the host’s secret/env UI (never commit it).

## Option A — Render (free web service, sleeps ~15 min idle)

1. Push this folder to a GitHub repo.
2. https://dashboard.render.com → New → Web Service → connect the repo.
3. Runtime: **Docker** (uses `Dockerfile`) or Python with:
   - Build: `apt-get update && apt-get install -y ffmpeg` (or use Docker)
   - Start: `STEM_PROVIDER=ffmpeg python app.py`
4. Add env (optional): `STEMSPLIT_API_KEY`
5. URL: `https://<name>.onrender.com`

Or: `render.yaml` Blueprint → New Blueprint Instance.

## Option B — Railway (trial credits)

1. Install CLI / sign in: `npm i -g @railway/cli && railway login`
2. From this directory: `railway init && railway up`
3. Settings → Networking → Generate Domain
4. Variables: optional `STEMSPLIT_API_KEY`; default `STEM_PROVIDER=ffmpeg`

Uses `Dockerfile` + `railway.toml`.

## Option C — Fly.io

```bash
fly launch --dockerfile Dockerfile --name stem-splitter
fly secrets set STEMSPLIT_API_KEY=...   # optional
fly deploy
```

## Local / box preview with HTTPS (Cloudflare Quick Tunnel)

No account needed; URL changes each run; stops when tunnel process exits:

```bash
STEM_PROVIDER=ffmpeg PORT=8765 python app.py &
cloudflared tunnel --url http://127.0.0.1:8765
```

## Health check

`GET /api/health` → JSON with `provider` / `stemsplit_configured`.
