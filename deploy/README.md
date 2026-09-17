# Deployment

Three ways to run this, cheapest first. All of them put **nginx in front**: it
serves the built React bundle and proxies `/api` to uvicorn, so the browser
talks to one origin and there is no CORS surface.

The `.env` file is never copied into an image. The key is passed in at runtime.

---

## 1. Docker Compose — the portable one

```bash
docker compose up --build       # http://localhost:8080
docker compose down             # add -v to also drop the data volume
```

`web` builds the frontend in a node stage and serves it from `nginx:alpine`;
`api` runs uvicorn and is never published to the host. Ingested data and the
extraction cache live on the `cbi-data` volume, so a rebuild keeps them.

Without `OPENAI_API_KEY` the stack still comes up — the app falls back to
offline mode.

## 2. Native nginx on Windows — no Docker needed

Docker Desktop is a ~600 MB install and wants WSL2. nginx for Windows is a 2 MB
zip that needs neither.

```powershell
# once
Invoke-WebRequest https://nginx.org/download/nginx-1.27.3.zip -OutFile nginx.zip
Expand-Archive nginx.zip -DestinationPath $env:USERPROFILE\nginx-cbi
# copy deploy/nginx.windows.conf over $env:USERPROFILE\nginx-cbi\nginx-1.27.3\conf\nginx.conf
# and set the `root` line to this repo's frontend/dist

# each time
.\scripts\run_backend.ps1        # terminal 1
.\scripts\run_nginx.ps1          # terminal 2 - builds the UI, starts/reloads nginx
```

App on **http://localhost:8080**. Stop with `.\scripts\run_nginx.ps1 -Stop`.

`run_nginx.ps1` runs `npm run build` first, so nginx never serves a stale
bundle — the most common way to confuse yourself with a static deploy.

## 3. A cloud VM

Any small box works; this is a SQLite app, so a single node is the right shape.

| Host | Cost | Notes |
|---|---|---|
| Oracle Cloud Always Free | $0 forever | 4 ARM cores / 24 GB. Signup friction is real. |
| Hetzner CX22 | ~€3.79/mo | Cheapest solid always-on VPS. |
| Fly.io | ~$0-3/mo | Docker-native, scales to zero. |
| DigitalOcean / Lightsail | $4-6/mo | Pay for the docs and the brand. |

Avoid free tiers that sleep when idle (Render free): a ~50 s cold start is fatal
in a live demo.

```bash
# on the box
git clone https://github.com/praneethgogi/client-briefing-intel.git
cd client-briefing-intel
printf 'OPENAI_API_KEY=sk-...\n' > .env
docker compose up -d --build
```

Then put a TLS terminator in front — Caddy, or nginx with certbot — and point a
DNS record at it.

### Before exposing this publicly

Identity is a demo header (`X-User-Id`), standing in for SSO. Anyone with the
URL can switch persona. That is fine for a walkthrough and **not** fine for
anything else: put it behind real authentication, or behind basic auth, or keep
it on localhost. See the limitations section of the main README.

## Cloudflare Tunnel — a public URL with no server

```bash
cloudflared tunnel --url http://localhost:8080
```

Free HTTPS URL pointing at the local stack. Nothing to provision, and it goes
away when the laptop sleeps. Same authentication caveat as above.
