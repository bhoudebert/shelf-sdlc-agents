#!/bin/sh
# Install Warden: one static binary, checksum-verified, no sudo.
#
#   curl -fsSL https://raw.githubusercontent.com/bhoudebert/shelf-sdlc-agents/main/warden/install.sh | sh
#
# Then wire it into Claude Code:   warden init --global --profile guarded
#
# Environment:
#   WARDEN_VERSION      a release to install, such as 0.1.0 (default: the latest)
#   WARDEN_INSTALL_DIR  where to put the binary (default: ~/.local/bin)
#   WARDEN_REPO         owner/name of the repository whose releases to read (default: bhoudebert/shelf-sdlc-agents)
#   WARDEN_BASE_URL     read the files from this URL instead of a release (for a mirror, or a test)
set -eu

repo="${WARDEN_REPO:-bhoudebert/shelf-sdlc-agents}"
dir="${WARDEN_INSTALL_DIR:-$HOME/.local/bin}"

fail() { echo "install.sh: $*" >&2; exit 1; }
have() { command -v "$1" >/dev/null 2>&1; }

case "$(uname -s)" in
  Linux) os=unknown-linux-musl ;;
  Darwin) os=apple-darwin ;;
  *) fail "unsupported system $(uname -s): Warden is built for Linux and macOS" ;;
esac
case "$(uname -m)" in
  x86_64|amd64) arch=x86_64 ;;
  aarch64|arm64) arch=aarch64 ;;
  *) fail "unsupported architecture $(uname -m)" ;;
esac
target="$arch-$os"

if have curl; then
  get() { curl -fsSL "$1"; }
  save() { curl -fsSL "$1" -o "$2"; }
elif have wget; then
  get() { wget -qO- "$1"; }
  save() { wget -q "$1" -O "$2"; }
else
  fail "needs curl or wget"
fi
if have sha256sum; then
  sum() { sha256sum "$1" | cut -d' ' -f1; }
elif have shasum; then
  sum() { shasum -a 256 "$1" | cut -d' ' -f1; }
else
  fail "needs sha256sum or shasum to verify the download"
fi

version="${WARDEN_VERSION:-}"
if [ -z "$version" ] && [ -z "${WARDEN_BASE_URL:-}" ]; then
  # The latest release whose tag starts with warden-v (this repository also releases the Shelf service).
  version="$(get "https://api.github.com/repos/$repo/releases?per_page=30" \
    | tr ',' '\n' | sed -n 's/.*"tag_name": *"warden-v\([^"]*\)".*/\1/p' | head -n 1)" || true
  [ -n "$version" ] || fail "could not find a Warden release of $repo (set WARDEN_VERSION)"
fi

base="${WARDEN_BASE_URL:-https://github.com/$repo/releases/download/warden-v$version}"
asset="warden-$target.tar.gz"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT INT TERM
echo "Installing Warden ${version:-from $base} for $target..."
save "$base/$asset" "$tmp/$asset" || fail "could not download $base/$asset"
save "$base/checksums.txt" "$tmp/checksums.txt" || fail "could not download $base/checksums.txt"

expected="$(grep " $asset\$" "$tmp/checksums.txt" | cut -d' ' -f1)"
[ -n "$expected" ] || fail "checksums.txt has no entry for $asset"
actual="$(sum "$tmp/$asset")"
[ "$expected" = "$actual" ] || fail "checksum mismatch for $asset (expected $expected, got $actual): not installing"

tar -xzf "$tmp/$asset" -C "$tmp" warden || fail "the archive does not hold a warden binary"
mkdir -p "$dir"
install -m 0755 "$tmp/warden" "$dir/warden"
echo "Installed $("$dir/warden" version) to $dir/warden"

case ":$PATH:" in
  *":$dir:"*) ;;
  *) echo "Note: $dir is not on your PATH. Add it, for example:  export PATH=\"$dir:\$PATH\"" ;;
esac
echo "Next: warden init --global --profile guarded   (then: warden doctor)"
