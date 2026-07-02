#!/usr/bin/env bash
# One-shot, idempotent deploy on a fresh DigitalOcean Docker droplet (run as root).
#
#   REPO_URL=https://github.com/you/Gauntlet_agent.git DOMAIN=gauntlet.example.com \
#     bash bootstrap.sh
#
# First run: installs everything, scaffolds /opt/gauntlet/.env, then stops so you
# can fill in secrets. Fill .env (see below), then run this again to go live.
set -euo pipefail

APP_DIR=/opt/gauntlet
REPO_URL="${REPO_URL:?set REPO_URL=https://github.com/you/Gauntlet_agent.git}"
DOMAIN="${DOMAIN:?set DOMAIN=your.domain.com}"

echo "==> packages (python venv, psql, caddy prerequisites)"
apt-get update -y
apt-get install -y python3-venv python3-dev build-essential postgresql-client \
  debian-keyring debian-archive-keyring apt-transport-https curl

echo "==> docker (skipped if the droplet already has it)"
if ! command -v docker >/dev/null; then
  curl -fsSL https://get.docker.com | sh
fi
if ! command -v caddy >/dev/null; then
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
    | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
    > /etc/apt/sources.list.d/caddy-stable.list
  apt-get update -y && apt-get install -y caddy
fi

echo "==> app user + code at $APP_DIR"
id gauntlet >/dev/null 2>&1 || adduser --system --group gauntlet
usermod -aG docker gauntlet
# We run git as root but the tree is chowned to gauntlet -> git's ownership guard.
git config --global --add safe.directory "$APP_DIR"
if [ -d "$APP_DIR/.git" ]; then
  git -C "$APP_DIR" pull --ff-only
else
  git clone "$REPO_URL" "$APP_DIR"
fi

echo "==> python venv"
python3 -m venv "$APP_DIR/.venv"
# Shared libs first (gauntlet-agent depends on gauntlet-core), then the app itself.
"$APP_DIR/.venv/bin/pip" install -q -e "$APP_DIR/core"
"$APP_DIR/.venv/bin/pip" install -q -e "$APP_DIR"

echo "==> .env"
if [ ! -f "$APP_DIR/.env" ]; then
  cp "$APP_DIR/.env.example" "$APP_DIR/.env"
  chown gauntlet:gauntlet "$APP_DIR/.env"; chmod 600 "$APP_DIR/.env"
  cat <<EOF

  Scaffolded $APP_DIR/.env — fill these before re-running:
    GITHUB_APP_ID=...
    GITHUB_APP_PRIVATE_KEY_FILE=$APP_DIR/private-key.pem   # scp your .pem here
    GITHUB_WEBHOOK_SECRET=...
    DATABASE_URL=...            # Supabase pooled connection string
    (leave MICROVM_S3_BUCKET blank -> uses the local Docker backend)

  Then re-run:  REPO_URL=$REPO_URL DOMAIN=$DOMAIN bash bootstrap.sh
EOF
  exit 0
fi

DB_URL="$(grep -E '^DATABASE_URL=' "$APP_DIR/.env" | cut -d= -f2- || true)"
if [ -n "$DB_URL" ]; then
  echo "==> apply migrations (idempotent, in order)"
  for m in "$APP_DIR"/migrations/[0-9]*.sql; do
    echo "    $m"; psql "$DB_URL" -f "$m"
  done
else
  echo "!! DATABASE_URL empty in .env — skipping migrations (persistence disabled)"
fi
chown -R gauntlet:gauntlet "$APP_DIR"

echo "==> systemd service"
cp "$APP_DIR/deploy/gauntlet.service" /etc/systemd/system/gauntlet.service
systemctl daemon-reload
systemctl enable --now gauntlet
systemctl restart gauntlet

echo "==> caddy (auto-TLS) for $DOMAIN"
sed "s/gauntlet.example.com/$DOMAIN/" "$APP_DIR/deploy/Caddyfile" > /etc/caddy/Caddyfile
systemctl reload caddy || systemctl restart caddy

echo "==> nightly image/cache prune"
echo '0 4 * * * root docker system prune -af --filter "until=24h" >/dev/null 2>&1' \
  > /etc/cron.d/gauntlet-prune

echo
echo "Done. Point the GitHub App webhook at: https://$DOMAIN/webhook/github"
echo "Check health:  curl -s https://$DOMAIN/health"
echo "Logs:          journalctl -u gauntlet -f"
