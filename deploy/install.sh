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

# Your access file is yours: created once from the example, then never touched or committed.
if [ ! -f "$here/shelf.toml" ]; then
  cp "$here/shelf.toml.example" "$here/shelf.toml"
  echo "Created $here/shelf.toml from the example. Edit it to say who may sign in (it ships open to any GitHub account)."
fi

# If the GitHub App is configured, its private key must be there: a file in deploy/secrets (or inline in the env file).
if grep -q '^GITHUB_APP_ID=.\+' "$env_file" && ! grep -q '^GITHUB_APP_PRIVATE_KEY=.\+' "$env_file" && [ ! -s "$here/secrets/github-app.pem" ]; then
  echo "WARNING: GITHUB_APP_ID is set but there is no private key. Put the .pem you downloaded at $here/secrets/github-app.pem" >&2
fi

# The agents need a model credential in the worker's environment: the host's own `claude` login is not visible there.
if ! grep -Eq '^(ANTHROPIC_API_KEY|CLAUDE_CODE_OAUTH_TOKEN|ANTHROPIC_AUTH_TOKEN)=.+' "$env_file"; then
  echo "WARNING: no model credential in $env_file. Agents will fail with 'Not logged in'. Run 'claude setup-token' and add CLAUDE_CODE_OAUTH_TOKEN=..., or set ANTHROPIC_API_KEY." >&2
fi

# The access file must be valid TOML: say so now, not after a build and a crash loop.
if command -v python3 >/dev/null 2>&1 && python3 -c 'import tomllib' 2>/dev/null; then
  if ! python3 -c 'import sys, tomllib; tomllib.load(open(sys.argv[1], "rb"))' "$here/shelf.toml" 2>/tmp/shelf-toml-error; then
    echo "ERROR: $here/shelf.toml is not valid TOML: $(tail -n 1 /tmp/shelf-toml-error)" >&2
    echo "       Names go in quotes, for example: users = [\"alice\", \"bob\"]" >&2
    exit 1
  fi
fi

# Say loudly when nobody is restricted: an open instance spends the operator's model quota.
if ! grep -Eq '^[[:space:]]*(orgs|users|admins)[[:space:]]*=[[:space:]]*\[[[:space:]]*"' "$here/shelf.toml"; then
  echo "WARNING: $here/shelf.toml lists no organisation, user or admin: anyone with a GitHub account may sign in and use your model quota." >&2
fi

# The revision this checkout is at. It is built into the image and reported by /healthz, so you can see what really runs.
SHELF_REVISION=$(git -C "$here" rev-parse --short HEAD 2>/dev/null || echo unknown)
if [ -n "$(git -C "$here" status --porcelain 2>/dev/null)" ]; then SHELF_REVISION="$SHELF_REVISION-dirty"; fi
export SHELF_REVISION
echo "Building revision $SHELF_REVISION"

# Always replace the web and worker containers, so a rebuilt image is the one that serves.
$compose up -d --build --force-recreate

port=$(sed -n 's/^WEB_PORT=//p' "$env_file")
port=${port:-8080}
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
