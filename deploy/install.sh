#!/bin/sh
# One command to a running instance on a fresh server with Docker:
#
#   sh deploy/install.sh https://shelf.example.org
#
# It writes deploy/.env (with a generated session secret) if there is none, then starts the stack. Open the address:
# the first visit registers the GitHub App in one click and shows what to paste into deploy/.env. Run it again after.
set -eu

here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
env_file="$here/.env"

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

docker compose -f "$here/compose.yml" --env-file "$env_file" up -d --build
echo
echo "Started. Open $(sed -n 's/^PUBLIC_URL=//p' "$env_file") : if the GitHub App is not registered yet, you will be guided."
echo "Logs: docker compose -f $here/compose.yml logs -f"
