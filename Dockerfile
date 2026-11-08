# One image for both services: `shelf-web` (the product) and `shelf-worker` (workflows, agents, git, GitHub).
FROM python:3.13-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.13 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
RUN uv sync --frozen --no-dev

FROM python:3.13-slim
# git clones and pushes as the App; bubblewrap, socat and ripgrep are what Claude Code's sandbox needs.
RUN apt-get update \
 && apt-get install -y --no-install-recommends git ca-certificates bubblewrap socat ripgrep curl unzip xz-utils \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --create-home --uid 1000 shelf
# mise installs the tools a repository declares (a JDK, Maven, Node, Python...) when an agent asks, so the image carries
# no toolchain. Pinned, and checked against the release's published checksum.
ARG TARGETARCH=amd64
ARG MISE_VERSION=v2026.11.4
RUN case "$TARGETARCH" in \
      amd64) arch=x64; sha=0296d9cba9324106d4e0962bb94a2072902f3658813aeb3b09504947bb8ddc2b ;; \
      arm64) arch=arm64; sha=219d1daa41d110ed004b6a9c4029000046b23b3498f45d17c7897a166177e80b ;; \
      *) echo "unsupported architecture $TARGETARCH" >&2; exit 1 ;; \
    esac \
 && curl -fsSL "https://github.com/jdx/mise/releases/download/${MISE_VERSION}/mise-${MISE_VERSION}-linux-${arch}" -o /usr/local/bin/mise \
 && echo "${sha}  /usr/local/bin/mise" | sha256sum -c - \
 && chmod 0755 /usr/local/bin/mise \
 && mkdir -p /cache && chown shelf:shelf /cache
COPY --from=build --chown=shelf:shelf /app /app
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
# The git revision this image was built from, shown by /healthz. Declared last so it never invalidates the layers above.
ARG SHELF_REVISION=unknown
ENV SHELF_REVISION=$SHELF_REVISION
USER shelf
WORKDIR /app
EXPOSE 8080
CMD ["shelf-web"]
