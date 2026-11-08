#!/bin/sh
# One command to a running instance on a server with Docker, and the same command to update it:
#
#   sh deploy/install.sh https://shelf.example.org     # first time: writes deploy/.env
#   git pull && sh deploy/install.sh                   # later: rebuilds and replaces the running containers
#
# Open the address: if the GitHub App is not registered yet, the first visit registers it in one click and shows what
# to paste into deploy/.env. Run the script again after that.
set -eu

here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
env_file="$here/.env"
compose="docker compose -f $here/compose.yml --env-file $env_file"

command -v docker >/dev/null 2>&1 || { echo "Docker is required: https://docs.docker.com/engine/install/" >&2; exit 1; }
docker compose version >/dev/null 2>&1 || { echo "Docker Compose v2 is required (docker compose)." >&2; exit 1; }

if [ ! -f "$env_file" ]; then
  url="${1:-}"
  [ -n "$url" ] || { echo "usage: sh deploy/install.sh https://your-address" >&2; exit 1; }
  secret=$(openssl rand -hex 32 2>/dev/null || head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n')
  sed -e "s|^PUBLIC_URL=.*|PUBLIC_URL=${url%/}|" -e "s|^SESSION_SECRET=.*|SESSION_SECRET=${secret}|" \
    "$here/.env.example" > "$env_file"
  chmod 600 "$env_file"
  echo "Wrote $env_file. Add your model credentials (ANTHROPIC_API_KEY or CLAUDE_CODE_OAUTH_TOKEN) before the first run."
fi

# Preflight: catch the usual mistakes before anything is built.
root_env="$here/../.env"
if [ -f "$root_env" ]; then
  echo "WARNING: there is a .env at the repository root ($root_env). Docker Compose reads only deploy/.env: move what you need there." >&2
fi
value() { sed -n "s/^$1=//p" "$env_file" | tail -n 1 | sed -e 's/^"//' -e 's/"$//'; }
for name in PUBLIC_URL SESSION_SECRET; do
  [ -n "$(value $name)" ] || { echo "ERROR: $name is empty in $env_file." >&2; exit 1; }
done
app_id=$(value GITHUB_APP_ID)
if [ -n "$app_id" ]; then
  for name in GITHUB_APP_SLUG GITHUB_APP_CLIENT_ID GITHUB_APP_CLIENT_SECRET GITHUB_WEBHOOK_SECRET GITHUB_APP_PRIVATE_KEY; do
    [ -n "$(value $name)" ] || echo "WARNING: GITHUB_APP_ID is set but $name is empty in $env_file: the service will not start. See the setup page for where to find it." >&2
  done
fi
port=$(value WEB_PORT); port=${port:-8080}
bind=$(value WEB_BIND); bind=${bind:-127.0.0.1}
if [ -z "$($compose ps -q web 2>/dev/null)" ] && command -v ss >/dev/null 2>&1 && ss -ltnH "sport = :$port" 2>/dev/null | grep -q .; then
  echo "ERROR: port $port is already in use on this host. WEB_PORT is the private port your proxy forwards to (not your site's public port 80/443): set it in $env_file to a free one, such as 8081, and point proxy_pass at it." >&2
  exit 1
fi

# The revision this checkout is at. It is built into the image and reported by /healthz, so you can see what really runs.
SHELF_REVISION=$(git -C "$here" rev-parse --short HEAD 2>/dev/null || echo unknown)
if [ -n "$(git -C "$here" status --porcelain 2>/dev/null)" ]; then SHELF_REVISION="$SHELF_REVISION-dirty"; fi
export SHELF_REVISION
echo "Building revision $SHELF_REVISION"

# Always replace the web and worker containers, so a rebuilt image is the one that serves.
$compose up -d --build --force-recreate

echo "Waiting for the web service..."
running=""
for _ in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15; do
  running=$(curl -fsS "http://127.0.0.1:$port/healthz" 2>/dev/null | sed -n 's/.*"revision": *"\([^"]*\)".*/\1/p') || running=""
  [ -n "$running" ] && break
  sleep 2
done

echo
if [ "$running" = "$SHELF_REVISION" ]; then
  echo "Running revision $running."
elif [ -n "$running" ]; then
  echo "WARNING: the service reports revision $running, but this checkout is $SHELF_REVISION." >&2
  echo "Something answers on port $port that is not the container just built. Check: $compose ps" >&2
else
  echo "The web service did not answer on port $port yet. Check: $compose logs web" >&2
fi
echo "Open $(sed -n 's/^PUBLIC_URL=//p' "$env_file"): if the GitHub App is not registered yet, you will be guided."
echo "Logs: $compose logs -f"
