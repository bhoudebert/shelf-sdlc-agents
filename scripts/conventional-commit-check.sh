#!/bin/sh
# Checks that a commit message file follows Conventional Commits. Used by the commit-msg hook and by
# scripts/check-commit-messages.sh in CI, so the rule is written once. POSIX sh and grep only: no runtime to install.
#
#   <type>(<scope>): <subject>      types: feat fix perf refactor docs test build ci chore style revert
#   header at most 100 characters, body lines at most 120 (URLs excepted), kebab-case scope, optional "!"
#   no attribution trailers or generated-by footers

file="$1"
[ -f "$file" ] || { echo "usage: conventional-commit-check.sh <message-file>" >&2; exit 2; }

header=$(sed -n '1p' "$file")

# Messages git writes itself are not authored: a merge, a revert, a fixup or squash for autosquash.
case "$header" in
  "Merge "*|'Revert "'*|"fixup! "*|"squash! "*|"amend! "*) exit 0 ;;
esac

types='feat|fix|perf|refactor|docs|test|build|ci|chore|style|revert'
fail() {
  echo "Commit message rejected: $1" >&2
  echo "  header: $header" >&2
  echo "  expected: <type>(<scope>): <subject>   with type one of: $(echo "$types" | tr '|' ' ')" >&2
  echo "  example:  feat(api): accept a time zone on every request" >&2
  exit 1
}

echo "$header" | grep -Eq "^($types)(\([a-z0-9]+(-[a-z0-9]+)*\))?!?: [^ ].*" ||
  fail "the header is not '<type>(<scope>): <subject>' (kebab-case scope, a space after the colon)"
[ "${#header}" -le 100 ] || fail "the header is ${#header} characters, at most 100"
echo "$header" | grep -Eq '\.$' && fail "the subject ends with a period"

# AGENTS.md: no attribution trailers or generated-by footers, whoever or whatever wrote the commit.
if grep -Eiq '^(co-authored-by|generated-by|claude-session):|generated with \[?(claude|codex|gemini|copilot|chatgpt)' "$file"; then
  echo "Commit message rejected: attribution trailers and generated-by footers are not allowed in this repository (AGENTS.md)." >&2
  exit 1
fi
line_no=0
sed '1d' "$file" | grep -v '^#' | while IFS= read -r line; do
  line_no=$((line_no + 1))
  case "$line" in *http://*|*https://*) continue ;; esac
  if [ "${#line}" -gt 120 ]; then
    echo "Commit message rejected: a body line is ${#line} characters, at most 120" >&2
    echo "  line: $line" >&2
    exit 1
  fi
done || exit 1
exit 0
