#!/bin/sh
# Prepares this host so that each agent step can have its own Docker daemon (decision 0020).
#
#   sh deploy/host-runtime.sh --check             # read-only: which steps are done and which are missing
#   sudo sh deploy/host-runtime.sh                # does the missing ones, after saying what it will change
#   sudo sh deploy/host-runtime.sh --yes          # the same, without asking (needed without a terminal)
#   sudo sh deploy/host-runtime.sh --restart-docker   # allows a Docker restart when a reload is not enough
#   sh deploy/host-runtime.sh --probe             # changes nothing: finds the profile a step needs here, prints profile=<name>
#
# What it installs is the Kata Containers runtime: every step runs in a small virtual machine with its own kernel, so a
# Docker daemon inside it cannot reach this host's Docker. It is safe to run again: each step checks whether it is done.
# It works on Ubuntu and Debian, on x86_64 and arm64, on a host with /dev/kvm (a cloud VM needs nested virtualisation).
# Exit status: 0 ready, 1 error or not possible here, 2 steps missing (--check or --probe), 3 Docker did not register the runtime.
set -eu

# The release, pinned with its checksum, because this script runs as root. The digests are the ones GitHub shows for
# the release assets of https://github.com/kata-containers/kata-containers/releases/tag/4.4.0.
KATA_VERSION="4.4.0"
KATA_SHA256_amd64="ccbc0cbc591089d0c57012b78da64b23ef43e0bac0f869dc7bfebe8588c33986"
KATA_SHA256_arm64="9dd4407d4b756858fe9ce33322a605f5a932743839a8ec47108e8513dcc3aaa3"
KATA_URL="https://github.com/kata-containers/kata-containers/releases/download"

# SHELF_HOST_ROOT puts every path of the host under another folder: the tests use it, nobody else needs to.
root="${SHELF_HOST_ROOT:-}"
runtime="${SHELF_STEP_RUNTIME:-kata}"
kata_dir="/opt/kata"
shim="$kata_dir/runtime-rs/bin/containerd-shim-kata-v2"
shim_config="$kata_dir/share/defaults/kata-containers/runtime-rs/configuration-qemu-runtime-rs.toml"
daemon_json="$root/etc/docker/daemon.json"
modules_conf="$root/etc/modules-load.d/shelf-kata.conf"
modules="vhost_vsock vhost_net"
smoke_image="${SHELF_SMOKE_IMAGE:-alpine:3}"
smoke_dind_image="${SHELF_SMOKE_DIND_IMAGE:-docker:28-dind}"
guide="https://github.com/bhoudebert/shelf-sdlc-agents/blob/main/docs/design/isolated-step-environments.md"

mode=run
yes=no
restart=no
for arg in "$@"; do
  case "$arg" in
    --check) mode=check ;;
    --yes) yes=yes ;;
    --restart-docker) restart=yes ;;
    --probe) mode=probe ;;
    -h | --help) sed -n '2,13p' "$0"; exit 0 ;;
    *) echo "unknown option: $arg (see --help)" >&2; exit 1 ;;
  esac
done

say() { printf '%s\n' "$*"; }
fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
refuse() {
  printf 'This host cannot be prepared by this script: %s\n' "$1" >&2
  printf 'Other options for Docker in steps are in %s\n' "$guide" >&2
  exit 1
}

# ---- the platform: nothing is changed until this passes ------------------------------------------------------------

platform() {
  [ -r "$root/etc/os-release" ] || refuse "cannot read /etc/os-release"
  # shellcheck disable=SC1091
  . "$root/etc/os-release"
  case " ${ID:-} ${ID_LIKE:-} " in
    *" ubuntu "* | *" debian "*) ;;
    *) refuse "only Ubuntu and Debian are supported (this is ${PRETTY_NAME:-unknown})" ;;
  esac
  case "$(uname -m)" in
    x86_64) arch=amd64 ;;
    aarch64) arch=arm64 ;;
    *) refuse "only x86_64 and arm64 are supported (this is $(uname -m))" ;;
  esac
  [ -e "$root/dev/kvm" ] || refuse "there is no /dev/kvm: the host has no virtualisation, or it is a virtual machine without nested virtualisation"
  command -v docker >/dev/null 2>&1 || refuse "Docker is not installed"
  engine=$(docker version --format '{{.Server.Version}}' 2>/dev/null) || refuse "the Docker engine does not answer (is this user allowed to use it?)"
  [ "${engine%%.*}" -ge 26 ] 2>/dev/null || refuse "Docker $engine is too old: version 26 or later is needed"
}

# ---- the steps: <name>_done says whether it is done, <name>_do does it ---------------------------------------------

modules_done() {
  for m in $modules; do [ -d "$root/sys/module/$m" ] || return 1; done
  [ -f "$modules_conf" ]
}
modules_do() {
  for m in $modules; do modprobe "$m"; done
  mkdir -p "$(dirname "$modules_conf")"
  # shellcheck disable=SC2086
  printf '%s\n' $modules > "$modules_conf"
}

release_done() {
  [ -x "$root$shim" ] && [ "$(cat "$root$kata_dir/.shelf-release" 2>/dev/null)" = "$KATA_VERSION" ]
}
release_do() {
  eval "want=\$KATA_SHA256_$arch"
  tmp=$(mktemp -d "${TMPDIR:-/var/tmp}/shelf-kata.XXXXXX")
  stage="$root/opt/.shelf-kata-stage"
  trap 'rm -rf "$tmp" "$stage"' EXIT
  say "       downloading Kata $KATA_VERSION (about 1 GB) to $tmp"
  curl -fL --retry 3 -o "$tmp/kata.tar.zst" "$KATA_URL/$KATA_VERSION/kata-static-$KATA_VERSION-$arch.tar.zst"
  got=$(sha256sum "$tmp/kata.tar.zst" | cut -d' ' -f1)
  [ "$got" = "$want" ] || fail "the download does not match the checksum this script holds (got $got): nothing was extracted"
  # Unpacked aside and moved into place whole, so that an interrupted run leaves the old folder as it was.
  rm -rf "$stage"
  mkdir -p "$stage"
  zstd -dc "$tmp/kata.tar.zst" | tar -x -C "$stage"
  [ -d "$stage$kata_dir" ] || fail "the release does not hold $kata_dir"
  printf '%s\n' "$KATA_VERSION" > "$stage$kata_dir/.shelf-release"
  rm -rf "$root$kata_dir.old"
  [ ! -d "$root$kata_dir" ] || mv "$root$kata_dir" "$root$kata_dir.old"
  mv "$stage$kata_dir" "$root$kata_dir"
  rm -rf "$root$kata_dir.old" "$stage" "$tmp"
  trap - EXIT
}

daemon_done() {
  command -v jq >/dev/null 2>&1 && [ -f "$daemon_json" ] \
    && jq -e --arg n "$runtime" --arg s "$shim" '.runtimes[$n].runtimeType == $s' "$daemon_json" >/dev/null 2>&1
}
daemon_do() {
  mkdir -p "$(dirname "$daemon_json")"
  if [ -f "$daemon_json" ]; then
    jq -e . "$daemon_json" >/dev/null 2>&1 || fail "$daemon_json is not valid JSON: it was left as it is"
    cp -p "$daemon_json" "$daemon_json.shelf-$(date +%Y%m%d%H%M%S)"
  else
    printf '{}\n' > "$daemon_json"
  fi
  jq --arg n "$runtime" --arg s "$shim" --arg c "$shim_config" \
    '.runtimes[$n] = {runtimeType: $s, options: {ConfigPath: $c}}' "$daemon_json" > "$daemon_json.shelf-new"
  cat "$daemon_json.shelf-new" > "$daemon_json"
  rm -f "$daemon_json.shelf-new"
}

listed() {
  docker info --format '{{range $k, $v := .Runtimes}}{{$k}} {{end}}' 2>/dev/null | tr ' ' '\n' | grep -qx "$runtime"
}
wait_listed() {
  n=0
  while [ "$n" -lt "$1" ]; do
    listed && return 0
    n=$((n + 1))
    sleep 1
  done
  listed
}
reload_done() { listed; }
reload_do() {
  before=$(docker ps -q)
  if ! systemctl reload docker 2>/dev/null; then
    kill -HUP "$(pidof dockerd)" || fail "could not ask Docker to reload its configuration"
  fi
  if ! wait_listed 15; then
    say "       Docker did not pick the runtime up on a reload."
    if [ "$(docker info --format '{{.LiveRestoreEnabled}}' 2>/dev/null)" = "true" ]; then
      say "       Live restore is on: a restart does not stop the running containers."
    else
      say "       Live restore is off: a restart stops every running container. These would stop:"
      docker ps --format '         {{.Names}}'
    fi
    [ "$restart" = yes ] || { say "       Run again with --restart-docker to restart Docker now."; exit 3; }
    systemctl restart docker
    wait_listed 60 || { say "       Docker still does not list the runtime '$runtime'."; exit 3; }
    return 0
  fi
  after=$(docker ps -q)
  lost=""
  for id in $before; do printf '%s\n' "$after" | grep -qx "$id" || lost="$lost $id"; done
  [ -z "$lost" ] || say "       WARNING: these containers stopped during the reload:$lost"
}

# What the runner gives a step that has a Docker daemon (DOCKER_CAPS and the profiles of src/shelf/domain/stepspec.py; a test keeps
# them equal), never privileged mode: under the runtime it would hand the host's devices to the virtual machine.
step_flags="--cap-add SYS_ADMIN --cap-add NET_ADMIN --cap-add SYS_RESOURCE --cap-add MKNOD --tmpfs /run:rw,nosuid,size=64m --tmpfs /var/lib/docker:rw,size=2048m"
profiles="standard unconfined systempaths full"
profile_flags() {
  case "$1" in
    standard) printf '%s' "" ;;
    unconfined) printf '%s' "--security-opt seccomp=unconfined --security-opt apparmor=unconfined" ;;
    systempaths) printf '%s' "--security-opt seccomp=unconfined --security-opt apparmor=unconfined --security-opt systempaths=unconfined" ;;
    full) printf '%s' "--security-opt seccomp=unconfined --security-opt apparmor=unconfined --security-opt systempaths=unconfined --cgroupns=host --cap-add ALL" ;;
  esac
}
# What the step's own command does before the daemon: make the cgroup filesystem and /proc/sys writable. Then a daemon, and a container in it.
probe_body='mount -o remount,rw /sys/fs/cgroup && echo cgroup-rw
mount -o remount,bind,rw /proc/sys || mount -o remount,rw /proc/sys && echo procsys-rw
dockerd -H unix:///var/run/docker.sock > /tmp/dockerd.log 2>&1 &
i=0
until docker info > /dev/null 2>&1; do
  i=$((i + 1))
  [ "$i" -lt 40 ] || { echo "the daemon did not start in 40 s:"; tail -n 6 /tmp/dockerd.log; exit 1; }
  sleep 1
done
docker run --rm hello-world > /dev/null 2>&1 && echo inner-ok'

# Starts a step-like container under the runtime with one profile and says whether a daemon in it ran a container.
# probe_out holds what it printed.
probe_profile() {
  probe_out=""
  docker image inspect "$smoke_dind_image" > /dev/null 2>&1 || docker pull -q "$smoke_dind_image" > /dev/null 2>&1 || true
  # shellcheck disable=SC2046,SC2086
  probe_out=$(timeout "${SHELF_PROBE_TIMEOUT:-240}" docker run --rm --name "shelf-probe-$$" --runtime "$runtime" $step_flags \
    $(profile_flags "$1") --entrypoint sh "$smoke_dind_image" -c "$probe_body" 2>&1) || true
  docker rm -f "shelf-probe-$$" > /dev/null 2>&1 || true
  case "$probe_out" in *inner-ok*) return 0 ;; esac
  return 1
}

# The first profile, from the least permissive, under which a daemon in a step runs a container. Sets found_profile; on no
# luck prints what each attempt said and returns 1.
find_profile() {
  found_profile=""
  attempts=""
  for profile in $profiles; do
    started=$(date +%s)
    if probe_profile "$profile"; then
      found_profile="$profile"
      probe_seconds=$(($(date +%s) - started))
      return 0
    fi
    attempts="$attempts
--- profile $profile:
$(printf '%s\n' "$probe_out" | tail -n 8)"
  done
  printf '%s\n' "A Docker daemon in a step did not run a container under any profile:$attempts" >&2
  printf '%s\n' "Docker in steps cannot be used on this host." >&2
  return 1
}

# The resolvers a step with Docker is given (SHELF_STEP_DNS): on a user-defined network Docker names its embedded resolver, which
# a virtual machine cannot reach, so a step cannot resolve anything. The operator's own value is proved if set; else the host's
# upstream resolvers (those Docker copies on its default network, without the loopback ones). Sets found_dns.
probe_host="${SHELF_PROBE_HOST:-api.anthropic.com}"
find_dns() {
  found_dns=""
  upstream="${SHELF_STEP_DNS:-}"
  if [ -z "$upstream" ]; then
    upstream=$(docker run --rm --network bridge "$smoke_image" sh -c "grep '^nameserver' /etc/resolv.conf" 2> /dev/null \
      | awk '$1 == "nameserver" {print $2}' | grep -v -e '^127\.' -e '^::1$' | paste -sd, -) || upstream=""
  fi
  if [ -z "$upstream" ]; then
    echo "No upstream resolver of this host a step can use was found (a loopback one, such as systemd-resolved's, is out of a" >&2
    echo "virtual machine's reach). Set SHELF_STEP_DNS in deploy/.env to the addresses of resolvers it can reach." >&2
    return 1
  fi
  net="shelf-probe-$$"
  docker network create "$net" > /dev/null 2>&1 || true
  # shellcheck disable=SC2016
  probe_out=$(timeout "${SHELF_PROBE_TIMEOUT:-240}" docker run --rm --runtime "$runtime" --network "$net" "$smoke_image" sh -c \
    "for n in $(printf '%s' "$upstream" | tr ',' ' '); do echo nameserver \$n; done > /etc/resolv.conf; nslookup $probe_host 2>&1" 2>&1) || true
  docker network rm "$net" > /dev/null 2>&1 || true
  case "$probe_out" in
    *"Name:"*) found_dns="$upstream"; return 0 ;;
  esac
  echo "A step under '$runtime' on a user-defined network could not resolve $probe_host with $upstream:" >&2
  printf '%s\n' "$probe_out" | tail -n 6 >&2
  echo "Set SHELF_STEP_DNS in deploy/.env to the addresses of resolvers a virtual machine can reach." >&2
  return 1
}

smoke() {
  started=$(date +%s)
  host_kernel=$(uname -r)
  guest_kernel=$(docker run --rm --runtime "$runtime" "$smoke_image" uname -r) || fail "a container under '$runtime' did not start"
  [ "$guest_kernel" != "$host_kernel" ] || fail "the container reports the host's kernel ($host_kernel): it is not in a virtual machine"
  say "[ok]   a step container has its own kernel ($guest_kernel; the host runs $host_kernel), $(($(date +%s) - started)) s"
  find_dns || exit 1
  say "[ok]   a step resolves names with $found_dns (a user-defined network, under $runtime)"
  find_profile || exit 1
  if [ "$found_profile" = standard ]; then
    say "[ok]   a Docker daemon inside a step runs a container (profile standard), $probe_seconds s"
  else
    say "[ok]   a Docker daemon inside a step runs a container, but only with the profile $found_profile, $probe_seconds s"
    say "       The standard profile does not work on this host. Set SHELF_STEP_DOCKER_PROFILE=$found_profile in deploy/.env"
    say "       (install.sh --install-runtime does it for you)."
  fi
}

# ---- the run -------------------------------------------------------------------------------------------------------

if [ "$runtime" != "kata" ]; then
  # Only Kata is installed here. Another runtime is the operator's own: this says whether Docker knows it.
  if listed; then say "[ok]   Docker lists the runtime '$runtime'"; exit 0; fi
  say "[todo] Docker does not list the runtime '$runtime'. This script installs Kata only: install '$runtime' yourself."
  exit 2
fi

platform
if [ "$mode" = probe ]; then
  listed || { say "The runtime '$runtime' is not installed here yet: run deploy/host-runtime.sh first." >&2; exit 2; }
  find_dns || exit 1
  dns_found="$found_dns"
  find_profile || exit 1
  say "dns=$dns_found"
  say "profile=$found_profile"
  exit 0
fi
say "[ok]   platform: ${PRETTY_NAME:-${ID:-linux}}, $(uname -m), Docker $engine, /dev/kvm"

todo=""
for step in modules release daemon reload; do
  case "$step" in
    modules) label="kernel modules $modules, loaded now and at every boot" ;;
    release) label="Kata Containers $KATA_VERSION in $kata_dir" ;;
    daemon) label="the runtime '$runtime' in $daemon_json" ;;
    reload) label="Docker lists the runtime '$runtime'" ;;
  esac
  if "${step}_done"; then say "[ok]   $label"; else say "[todo] $label"; todo="$todo $step"; fi
done

if [ -z "$todo" ]; then
  if [ "$mode" = check ]; then say "Ready."; exit 0; fi
  smoke
  say "Ready."
  exit 0
fi
[ "$mode" != check ] || { say "Not ready: run this script without --check (as root) to do the missing steps."; exit 2; }

[ "$(id -u)" -eq 0 ] || fail "this changes the system: run it with sudo"

packages=""
case "$todo" in *release*) for p in curl zstd; do command -v "$p" >/dev/null 2>&1 || packages="$packages $p"; done ;; esac
case "$todo" in *daemon*) command -v jq >/dev/null 2>&1 || packages="$packages jq" ;; esac
say ""
say "This will:"
case "$todo" in *modules*) say "  - load the kernel modules $modules now and list them in $modules_conf" ;; esac
[ -z "$packages" ] || say "  - install with apt:$packages"
case "$todo" in *release*) say "  - download Kata $KATA_VERSION (about 1 GB), verify its checksum and unpack it into $kata_dir" ;; esac
case "$todo" in *daemon*) say "  - add the runtime '$runtime' to $daemon_json (a dated copy of the file is kept first)" ;; esac
case "$todo" in *reload*) say "  - ask Docker to reload its configuration: running containers are not stopped by a reload" ;; esac
say ""
if [ "$yes" != yes ]; then
  [ -t 0 ] || fail "nothing was changed: without a terminal to ask, run it again with --yes"
  printf 'Proceed? [y/N] '
  read -r answer
  case "$answer" in y | Y | yes) ;; *) say "Nothing was changed."; exit 1 ;; esac
fi

if [ -n "$packages" ]; then
  apt-get update -qq
  # shellcheck disable=SC2086
  apt-get install -y $packages
fi
for step in modules release daemon reload; do
  case " $todo " in *" $step "*) ;; *) continue ;; esac
  say "[do]   $step"
  "${step}_do"
  "${step}_done" || fail "$step: done, but the check still fails"
done
smoke
say "Ready."
