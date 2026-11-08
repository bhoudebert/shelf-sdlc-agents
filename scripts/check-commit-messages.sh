#!/bin/sh
# Checks every commit message of a range, for CI: sh scripts/check-commit-messages.sh <base-sha> <head-sha>
# Merge commits are skipped. Needs the history of the range (fetch-depth: 0 in the workflow).

base="$1"
head="$2"
[ -n "$base" ] && [ -n "$head" ] || { echo "usage: check-commit-messages.sh <base> <head>" >&2; exit 2; }

here=$(dirname "$0")
tmp=$(mktemp)
trap 'rm -f "$tmp"' EXIT
status=0
for commit in $(git rev-list --no-merges "$base..$head"); do
  git log -1 --format=%B "$commit" > "$tmp"
  if ! sh "$here/conventional-commit-check.sh" "$tmp"; then
    echo "  in commit $commit" >&2
    status=1
  fi
done
[ "$status" -eq 0 ] && echo "All commit messages follow Conventional Commits."
exit "$status"
