#!/bin/sh
# Let the agents' sandbox start on an Ubuntu 23.10+ host (24.04 included).
#
# Why: the agents run commands inside Claude Code's sandbox (bubblewrap), which needs unprivileged user namespaces.
# Ubuntu restricts them in two places, and both block the sandbox even inside a container:
#   1. the sysctl kernel.apparmor_restrict_unprivileged_userns
#   2. the AppArmor profile bwrap-userns-restrict, which attaches to any "bwrap" binary, containers included
# This script shows what it finds, asks, then changes only those two things. It is safe to run again.
#
#   sh deploy/fix-ubuntu.sh           look, explain, ask, then fix
#   sh deploy/fix-ubuntu.sh --yes     fix without asking
#   sh deploy/fix-ubuntu.sh --undo    put both back as Ubuntu ships them
#
# What it costs: unprivileged programs on this host may create user namespaces again (the default on most Linux
# distributions) and bubblewrap is no longer confined by Ubuntu's profile. Do this on a host dedicated to this stack.
set -eu

SYSCTL=kernel.apparmor_restrict_unprivileged_userns
SYSCTL_FILE=/etc/sysctl.d/60-shelf-userns.conf
PROFILE=/etc/apparmor.d/bwrap-userns-restrict
DISABLED=/etc/apparmor.d/disable/bwrap-userns-restrict
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

mode=fix
assume_yes=no
for arg in "$@"; do
  case "$arg" in
    --yes) assume_yes=yes ;;
    --undo) mode=undo ;;
    -h|--help) sed -n '2,16p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Unknown option: $arg (try --help)" >&2; exit 2 ;;
  esac
done

if [ "$(uname -s)" != "Linux" ] || [ ! -r /etc/os-release ] || ! grep -qi '^ID=ubuntu' /etc/os-release; then
  echo "This host is not Ubuntu: nothing to fix here. If the sandbox still cannot start, run the doctor and read its advice."
  exit 0
fi

sudo_cmd=""
if [ "$(id -u)" -ne 0 ]; then
  command -v sudo >/dev/null 2>&1 || { echo "ERROR: run this as root or install sudo." >&2; exit 1; }
  sudo_cmd="sudo"
fi

restricted=no
[ "$(sysctl -n "$SYSCTL" 2>/dev/null || echo 0)" = "1" ] && restricted=yes
profile_loaded=no
if [ -e "$PROFILE" ] && [ ! -e "$DISABLED" ]; then profile_loaded=yes; fi

echo "What I found on this host:"
echo "  $SYSCTL: $( [ "$restricted" = yes ] && echo 'restricted (blocks the sandbox)' || echo 'open' )"
echo "  AppArmor profile bwrap-userns-restrict: $( [ -e "$PROFILE" ] && { [ "$profile_loaded" = yes ] && echo 'active (blocks the sandbox in containers)' || echo 'disabled'; } || echo 'not installed' )"
echo

if [ "$mode" = undo ]; then
  echo "I will restore Ubuntu's defaults: restrict user namespaces and re-enable the bubblewrap profile."
else
  if [ "$restricted" = no ] && [ "$profile_loaded" = no ]; then
    echo "Nothing to change: this host already lets the sandbox start."
    echo "If agents still cannot run commands, run: docker compose -f $here/compose.yml exec worker shelf-doctor"
    exit 0
  fi
  echo "I will:"
  [ "$restricted" = yes ] && echo "  1. set $SYSCTL=0 now and keep it in $SYSCTL_FILE"
  [ "$profile_loaded" = yes ] && echo "  2. unload the AppArmor profile bwrap-userns-restrict and keep it disabled ($DISABLED)"
  echo
  echo "Cost: any program on this host may create user namespaces again, and bubblewrap is no longer confined by Ubuntu's"
  echo "profile. Do it on a host dedicated to this stack, not on a shared one."
fi

if [ "$assume_yes" != yes ]; then
  printf "Go ahead? [y/N] "
  read -r answer || answer=n
  case "$answer" in y|Y|yes|YES) ;; *) echo "Nothing changed."; exit 0 ;; esac
fi

if [ "$mode" = undo ]; then
  $sudo_cmd rm -f "$SYSCTL_FILE" "$DISABLED"
  $sudo_cmd sysctl -w "$SYSCTL=1" >/dev/null
  [ -e "$PROFILE" ] && $sudo_cmd apparmor_parser -r "$PROFILE"
  echo "Restored. The agents' sandbox will not start on this host until you run this script again."
  exit 0
fi

if [ "$restricted" = yes ]; then
  echo "$SYSCTL=0" | $sudo_cmd tee "$SYSCTL_FILE" >/dev/null
  $sudo_cmd sysctl -w "$SYSCTL=0" >/dev/null
fi
if [ "$profile_loaded" = yes ]; then
  $sudo_cmd mkdir -p /etc/apparmor.d/disable
  $sudo_cmd ln -sf "$PROFILE" "$DISABLED"
  $sudo_cmd apparmor_parser -R "$PROFILE" 2>/dev/null || true
fi
echo "Done."

compose="docker compose -f $here/compose.yml"
if command -v docker >/dev/null 2>&1 && $compose ps --status running worker >/dev/null 2>&1; then
  echo "Restarting the worker and running the doctor..."
  $compose restart worker >/dev/null
  $compose exec worker shelf-doctor || true
else
  echo "Now restart the worker and check the agents:"
  echo "  $compose restart worker && $compose exec worker shelf-doctor"
fi
