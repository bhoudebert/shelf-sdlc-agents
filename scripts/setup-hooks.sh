#!/bin/sh
# Installs the git hooks of this repository (once per clone): they live in .githooks/, versioned with the code.
# Works for every language and every coding agent, because it is plain git.
set -e
cd "$(git rev-parse --show-toplevel)"
git config core.hooksPath .githooks
chmod +x .githooks/* scripts/*.sh 2>/dev/null || true
echo "git hooks installed (core.hooksPath = .githooks)"
