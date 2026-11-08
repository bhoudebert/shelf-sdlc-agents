# Security

## Secrets

Keys and tokens live in environment variables or an untracked `.env`, never in the repository. `.env` is git-ignored;
commit an `.env.example` with the names and no values. If a secret is ever committed, treat it as leaked: revoke it, then
remove it from the history.

## What this project reaches

<!-- List the external services, files and ports the software touches, so a reviewer can judge the attack surface. -->

## Reporting a vulnerability

Open a private security advisory on the repository (Security tab, "Report a vulnerability"), or contact the maintainer
directly. Please do not open a public issue for a vulnerability. Expect an answer within a few days.

## Supported versions

The latest release receives fixes.
