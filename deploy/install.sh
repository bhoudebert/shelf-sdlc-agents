#!/bin/sh
# One command to a running instance on a server with Docker, and the same command to update it:
#
#   sh deploy/install.sh https://shelf.example.org     # first time: writes deploy/.env
#   git pull && sh deploy/install.sh                   # later: rebuilds and replaces the running containers
#   sh deploy/install.sh --install-runtime             # with SHELF_STEP_DOCKER=on: also installs what the host lacks (sudo)
#
# Open the address: if the GitHub App is not registered yet, the first visit registers it in one click and shows what
# to paste into deploy/.env. Run the script again after that.
set -eu

here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
env_file="$here/.env"
compose="docker compose -f $here/compose.yml --env-file $env_file"

install_runtime=""
url=""
for arg in "$@"; do
  case "$arg" in
    --install-runtime) install_runtime=yes ;;
    *) [ -n "$url" ] || url="$arg" ;;
  esac
done

command -v docker >/dev/null 2>&1 || { echo "Docker is required: https://docs.docker.com/engine/install/" >&2; exit 1; }
docker compose version >/dev/null 2>&1 || { echo "Docker Compose v2 is required (docker compose)." >&2; exit 1; }

if [ ! -f "$env_file" ]; then
  [ -n "$url" ] || { echo "usage: sh deploy/install.sh https://your-address" >&2; exit 1; }
  secret=$(openssl rand -hex 32 2>/dev/null || head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n')
  sed -e "s|^PUBLIC_URL=.*|PUBLIC_URL=${url%/}|" -e "s|^SESSION_SECRET=.*|SESSION_SECRET=${secret}|" \
    "$here/.env.example" > "$env_file"
  chmod 600 "$env_file"
  echo "Wrote $env_file. Add your model credentials (ANTHROPIC_API_KEY or CLAUDE_CODE_OAUTH_TOKEN) before the first run."
fi

# Preflight: the usual mistakes, caught before anything is built.
value() { sed -n "s/^$1=//p" "$env_file" | tail -n 1 | sed -e 's/^"//' -e 's/"$//'; }
if [ -f "$here/../.env" ]; then
  echo "WARNING: there is a .env at the repository root. Docker Compose reads only $env_file: move what you need there." >&2
fi
# SHELF_NIX=on adds a persistent Nix store and its daemon (compose.nix.yml): see the operate page of the guide.
if [ "$(value SHELF_NIX)" = "on" ]; then compose="$compose -f $here/compose.nix.yml"; fi
# SHELF_ISOLATION=container runs each agent step in a container of its own (compose.container.yml, decision 0019).
container=""
if [ "$(value SHELF_ISOLATION)" = "container" ]; then
  container=yes
  compose="$compose -f $here/compose.container.yml"
  if [ -z "$(value SHELF_RUNNER_TOKEN)" ]; then
    token=$(openssl rand -hex 32 2>/dev/null || head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n')
    printf 'SHELF_RUNNER_TOKEN=%s\n' "$token" >> "$env_file"
    echo "Wrote SHELF_RUNNER_TOKEN to $env_file: the worker's key to the runner."
  fi
fi
# SHELF_STEP_DOCKER=on gives each step that runs repository code a Docker daemon of its own, in a virtual machine of its own
# (decision 0020). That needs a runtime on the host: host-runtime.sh checks it, and installs it when you let it.
docker_steps=""
if [ "$(value SHELF_STEP_DOCKER)" = "on" ]; then
  [ -n "$container" ] || { echo "ERROR: SHELF_STEP_DOCKER=on needs SHELF_ISOLATION=container in $env_file." >&2; exit 1; }
  runtime=$(value SHELF_STEP_RUNTIME)
  [ -n "$runtime" ] || {
    echo "ERROR: SHELF_STEP_DOCKER=on needs SHELF_STEP_RUNTIME in $env_file: the runtime that makes a Docker daemon in a step" >&2
    echo "       safe. kata is the one $here/host-runtime.sh installs." >&2
    exit 1
  }
  host_script="$here/host-runtime.sh"
  as_root() { if [ "$(id -u)" = 0 ]; then "$@"; else sudo "$@"; fi; }
  check=0
  SHELF_STEP_RUNTIME="$runtime" sh "$host_script" --check || check=$?
  case "$check" in
    0) ;;
    2)
      if [ -n "$install_runtime" ]; then
        answer=y
      elif [ -t 0 ]; then
        printf 'Install it now (the script says what it changes first, and asks for sudo)? [y/N] '
        read -r answer
      else
        answer=n
      fi
      case "$answer" in
        y | Y | yes)
          as_root env SHELF_STEP_RUNTIME="$runtime" sh "$host_script" --yes || exit 1
          SHELF_STEP_RUNTIME="$runtime" sh "$host_script" --check || {
            echo "ERROR: the host is still not ready for Docker in steps (see above)." >&2
            exit 1
          }
          ;;
        *)
          echo "ERROR: the host is not ready for Docker in steps. Install what is missing:" >&2
          echo "         sudo sh $host_script" >&2
          echo "       or run this script again with --install-runtime." >&2
          exit 1
          ;;
      esac
      ;;
    *) exit 1 ;;
  esac
  # What a host allows differs: the guest's seccomp and cgroup filesystem (the profile), and the resolvers a step can reach (a
  # virtual machine cannot use Docker's embedded one). Each is found once, here, by the host script, and written down. A value
  # you set yourself is proved but never replaced.
  if [ -z "$(value SHELF_STEP_DOCKER_PROFILE)" ] || [ -z "$(value SHELF_STEP_DNS)" ]; then
    echo "Finding what a step with Docker needs on this host (a few containers start; this takes a minute or two)..."
    probed=$(SHELF_STEP_RUNTIME="$runtime" SHELF_STEP_DNS="$(value SHELF_STEP_DNS)" sh "$host_script" --probe) || {
      echo "ERROR: Docker in steps cannot be used on this host (see above). Set SHELF_STEP_DOCKER=off to go on without it." >&2
      exit 1
    }
    profile=$(printf '%s\n' "$probed" | sed -n 's/^profile=//p' | tail -n 1)
    resolvers=$(printf '%s\n' "$probed" | sed -n 's/^dns=//p' | tail -n 1)
    [ -n "$profile" ] || { echo "ERROR: the host script named no profile." >&2; exit 1; }
    [ -n "$resolvers" ] || { echo "ERROR: the host script named no resolvers: set SHELF_STEP_DNS in $env_file." >&2; exit 1; }
    if [ -z "$(value SHELF_STEP_DOCKER_PROFILE)" ]; then
      printf 'SHELF_STEP_DOCKER_PROFILE=%s\n' "$profile" >> "$env_file"
      echo "Wrote SHELF_STEP_DOCKER_PROFILE=$profile to $env_file."
    fi
    if [ -z "$(value SHELF_STEP_DNS)" ]; then
      printf 'SHELF_STEP_DNS=%s\n' "$resolvers" >> "$env_file"
      echo "Wrote SHELF_STEP_DNS=$resolvers to $env_file."
    fi
  fi
  docker_steps=yes
fi
for name in PUBLIC_URL SESSION_SECRET; do
  [ -n "$(value $name)" ] || { echo "ERROR: $name is empty in $env_file." >&2; exit 1; }
done
# A Compose file that does not parse must not look like a busy port: `compose ps` below hides its errors.
if ! config_error=$($compose config -q 2>&1); then
  echo "ERROR: Docker Compose cannot read the deployment files:" >&2
  echo "$config_error" >&2
  exit 1
fi
web_port=$(value WEB_PORT); web_port=${web_port:-8080}
if [ -z "$($compose ps -q web 2>/dev/null)" ] && command -v ss >/dev/null 2>&1 \
  && ss -ltnH "sport = :$web_port" 2>/dev/null | grep -q .; then
  echo "ERROR: port $web_port is already in use on this host by something that is not this service. WEB_PORT is the private" >&2
  echo "       port your proxy forwards to (not your site's public port 80 or 443): set another in $env_file, such as 8081," >&2
  echo "       and point your proxy at it." >&2
  exit 1
fi
if [ -z "$(value WEB_BIND)" ]; then
  echo "NOTE: the web port is published on every network interface. If your reverse proxy runs on this server, set" >&2
  echo "      WEB_BIND=127.0.0.1 in $env_file so that the proxy is the only way in."
fi

# Your access file is yours: created once from the example, then never touched or committed.
mkdir -p "$here/config"
if [ -f "$here/shelf.toml" ] && [ ! -f "$here/config/shelf.toml" ]; then
  mv "$here/shelf.toml" "$here/config/shelf.toml"
  echo "Moved $here/shelf.toml to $here/config/shelf.toml (a folder is mounted so that edits are always seen)."
fi
if [ ! -f "$here/config/shelf.toml" ]; then
  cp "$here/shelf.toml.example" "$here/config/shelf.toml"
  echo "Created $here/config/shelf.toml from the example. Edit it to say who may sign in (it ships open to any GitHub account)."
fi

# The catalog of corporate skills and plugins is yours too: created once from the example (which fetches nothing until you
# uncomment a source), then never touched or committed.
# Warden's operator policy is yours too, and optional: a locked file that every repository can only tighten.
if [ ! -f "$here/config/warden.toml" ]; then
  cp "$here/warden.toml.example" "$here/config/warden.toml"
  echo "Created $here/config/warden.toml from the example (every line is commented: the profile alone guards the agents)."
fi
if [ ! -f "$here/config/catalog.toml" ]; then
  cp "$here/catalog.toml.example" "$here/config/catalog.toml"
  echo "Created $here/config/catalog.toml from the example. Uncomment the sources you want agents to have, then run this script again."
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
  if ! python3 -c 'import sys, tomllib; tomllib.load(open(sys.argv[1], "rb"))' "$here/config/shelf.toml" 2>/tmp/shelf-toml-error; then
    echo "ERROR: $here/config/shelf.toml is not valid TOML: $(tail -n 1 /tmp/shelf-toml-error)" >&2
    echo "       Names go in quotes, for example: users = [\"alice\", \"bob\"]" >&2
    exit 1
  fi
fi

# Say loudly when nobody is listed: the instance is closed by default, so nobody could sign in.
if ! grep -Eq '^[[:space:]]*(orgs|users|admins)[[:space:]]*=[[:space:]]*\[[[:space:]]*"' "$here/config/shelf.toml"; then
  echo "WARNING: $here/config/shelf.toml lists no organisation, user or admin: NOBODY can sign in, you included. Add yourself, for example admins = [\"your-github-login\"], then run this script again." >&2
fi

# The revision this checkout is at. It is built into the image and reported by /healthz, so you can see what really runs.
SHELF_REVISION=$(git -C "$here" rev-parse --short HEAD 2>/dev/null || echo unknown)
if [ -n "$(git -C "$here" status --porcelain 2>/dev/null)" ]; then SHELF_REVISION="$SHELF_REVISION-dirty"; fi
export SHELF_REVISION
echo "Building revision $SHELF_REVISION"

# The image a step runs in, and the network the steps use, before the runner starts its first container.
if [ -n "$container" ]; then
  $compose --profile tools build step || { echo "ERROR: the step image could not be built (see above)." >&2; exit 1; }
  if [ -n "$docker_steps" ]; then
    $compose --profile tools build step-docker || { echo "ERROR: the step image with Docker could not be built (see above)." >&2; exit 1; }
  fi
  docker network inspect shelf-sdlc-step >/dev/null 2>&1 || docker network create shelf-sdlc-step >/dev/null
fi

# Always replace the web and worker containers, so a rebuilt image is the one that serves.
$compose up -d --build --force-recreate

# Fetch the catalog at its pinned commits into the volumes the worker reads. It runs nothing it fetches, and a failure leaves
# the previous catalog in place. The sync service sits behind a profile, so `up --build` does not rebuild it: build it here, or
# it would run from an older image (without Warden, so the managed policy would carry no guard).
echo "Syncing the catalog ($here/config/catalog.toml)..."
$compose --profile tools build catalog || {
  echo "ERROR: the catalog image could not be built (see above)." >&2
  exit 1
}
$compose --profile tools run --rm --no-deps catalog || {
  echo "ERROR: the catalog could not be synced (see above). The worker keeps the previous catalog. Fix config/catalog.toml and run this script again." >&2
  exit 1
}

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
# Say now whether the guard is in force, rather than after a run that found nothing.
if [ "$(value SHELF_WARDEN)" != "off" ]; then
  doctor=$($compose exec -T worker warden doctor 2>&1) || true
  if printf '%s\n' "$doctor" | grep -qE '^(warn|fail|error)'; then
    echo "WARNING: the guard (Warden) is not fully in force:" >&2
    printf '%s\n' "$doctor" | grep -E '^(warn|fail|error)' | sed 's/^/  /' >&2
  elif printf '%s\n' "$doctor" | grep -q '^ok'; then
    echo "Guard: Warden is wired into the agents (docker compose exec worker warden status shows what it saw)."
  fi
  # Nix is optional: say whether the worker reaches the daemon whose store it reads.
  if [ "$(value SHELF_NIX)" = "on" ]; then
    if $compose exec -T worker sh -c 'NIX_REMOTE=daemon /nix/var/nix/profiles/default/bin/nix --extra-experimental-features nix-command store info' >/dev/null 2>&1; then
      echo "Nix: the worker reaches the Nix daemon (the store is kept between updates; docker compose exec nix nix-collect-garbage -d empties it)."
    else
      echo "WARNING: SHELF_NIX=on but the worker cannot reach the Nix daemon: flakes will not give the agents their tools. Check: $compose logs nix" >&2
    fi
  fi
  # The admin page can allow a command or block a host: the web service must be able to write its rules.
  if $compose exec -T web sh -c 'test -w /var/lib/shelf-guard' >/dev/null 2>&1; then
    echo "Guard rules: the admin page can add rules (kept in the guard-rules volume, applied from the next agent call)."
  else
    echo "WARNING: the admin page cannot write the guard's rules: /var/lib/shelf-guard is not writable in the web container." >&2
  fi
  # Each agent run leaves a record the downloaded file of a work shows: the worker must be able to write them.
  if $compose exec -T worker sh -c 'test -w /var/lib/shelf-runs' >/dev/null 2>&1; then
    echo "Run records: each agent run is kept for 30 days and shown in the file of a work (Download on its page)."
  else
    echo "WARNING: the worker cannot write the run records: /var/lib/shelf-runs is not writable in the worker container." >&2
  fi
fi
echo "Open $(sed -n 's/^PUBLIC_URL=//p' "$env_file"): if the GitHub App is not registered yet, you will be guided."
echo "Logs: $compose logs -f"

# Ubuntu 23.10+ blocks the agents' sandbox unless the host is relaxed: say so now rather than after a failed run.
if [ -r /etc/os-release ] && grep -qi '^ID=ubuntu' /etc/os-release; then
  if [ "$(sysctl -n kernel.apparmor_restrict_unprivileged_userns 2>/dev/null || echo 0)" = "1" ] \
    || { [ -e /etc/apparmor.d/bwrap-userns-restrict ] && [ ! -e /etc/apparmor.d/disable/bwrap-userns-restrict ]; }; then
    echo
    echo "NOTE: this Ubuntu host blocks the agents' sandbox, so agents could read files but not run commands."
    echo "      Fix it once: sh $here/fix-ubuntu.sh   (it explains what it changes and asks first)"
  fi
fi
