# Deploy on a DigitalOcean Droplet

One VM with Docker runs everything: the FastAPI app, and (per run) the customer
image + mitmproxy + twin servers. The app runs **on the host**, not in a
container — it drives the host Docker daemon.

## 1. Create the droplet
- **Marketplace → Docker** image (Docker pre-installed), Ubuntu base.
- Size: **≥2 GB RAM** (4 GB if repos are heavy — a run builds a container *and*
  spawns mitmproxy + twins).
- Add your SSH key.
- **Networking → Firewall:** allow inbound **80** and **443** (webhook TLS) and
  **22** (SSH). Everything else stays closed; all run egress is proxied.

Point an A record for your domain (free via the Student Pack / Namecheap) at the
droplet IP.

## 2. Install the app (on the droplet)
```bash
adduser --system --group gauntlet
git clone <repo> /opt/gauntlet && cd /opt/gauntlet
python3 -m venv .venv && .venv/bin/pip install -e .
usermod -aG docker gauntlet          # let the service talk to Docker
```

## 3. Configure
```bash
cp .env.example .env && $EDITOR .env
```
Set: `GITHUB_APP_ID`, `GITHUB_APP_PRIVATE_KEY`, `GITHUB_WEBHOOK_SECRET`,
`DATABASE_URL` (Supabase pooled string). Leave `MICROVM_S3_BUCKET` blank so the
runner auto-picks the **docker** backend.

Apply the schema once:
```bash
psql "$DATABASE_URL" -f migrations/0001_backend.sql
```

## 4. Run it
```bash
cp deploy/gauntlet.service /etc/systemd/system/
systemctl enable --now gauntlet
```

## 5. TLS + public URL
```bash
apt install -y caddy
cp deploy/Caddyfile /etc/caddy/Caddyfile   # edit the domain first
systemctl reload caddy
```
Set the GitHub App webhook to `https://<your-domain>/webhook/github`.

## 6. Keep disk clean
The runner deletes each run's container + image on teardown. This nightly prune
just sweeps build cache and anything left by a crash:
```bash
echo '0 4 * * * root docker system prune -af --filter "until=24h" >/dev/null 2>&1' \
  > /etc/cron.d/gauntlet-prune
```

## Scaling note
Single process only — the run dedup (`runner._inflight`) is in-memory. Scale the
droplet up, not out, until you move the queue to something shared.
