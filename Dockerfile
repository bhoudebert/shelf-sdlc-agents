# One image for both services: `shelf-web` (the product) and `shelf-worker` (workflows, agents, git, GitHub).
FROM python:3.15-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.13 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
RUN uv sync --frozen --no-dev

# Warden, the guard around every agent (decision 0014), built from the same commit as the rest of the image.
FROM rust:1.99-slim-bookworm AS warden
WORKDIR /w
COPY warden ./warden
RUN --mount=type=cache,target=/usr/local/cargo/registry --mount=type=cache,target=/w/warden/target \
    cargo build --release --locked --manifest-path warden/Cargo.toml \
 && install -m 0755 warden/target/release/warden /usr/local/bin/warden

FROM python:3.15-slim AS app
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
# gh lets an agent read the CI runs of its pull request (with the token it is given, which can read runs, not change
# them). Pinned, and checked against the release's published checksum.
ARG GH_VERSION=2.103.3
RUN case "$TARGETARCH" in \
      amd64) arch=amd64; sha=4c806978ffce1cec70853302a56d70ac6da4f19bae7adca4e1a8ab00633dd91d ;; \
      arm64) arch=arm64; sha=ee32df2323c8847f5fac6cb6b4b69ca75828e9329a8f22f677021f7b3306ce63 ;; \
      *) echo "unsupported architecture $TARGETARCH" >&2; exit 1 ;; \
    esac \
 && curl -fsSL "https://github.com/cli/cli/releases/download/v${GH_VERSION}/gh_${GH_VERSION}_linux_${arch}.tar.gz" -o /tmp/gh.tgz \
 && echo "${sha}  /tmp/gh.tgz" | sha256sum -c - \
 && tar -xzf /tmp/gh.tgz -C /tmp "gh_${GH_VERSION}_linux_${arch}/bin/gh" \
 && install -m 0755 "/tmp/gh_${GH_VERSION}_linux_${arch}/bin/gh" /usr/local/bin/gh \
 && rm -rf /tmp/gh.tgz "/tmp/gh_${GH_VERSION}_linux_${arch}"
# Node runs the hooks of corporate plugins (caveman, ponytail...). Pinned, and checked against the release's published checksum.
ARG NODE_VERSION=22.23.5
RUN case "$TARGETARCH" in \
      amd64) arch=x64; sha=cdeb8670a0c81f51b4dc4ac61919f9b1ad917b304bf8221eb939570663d240f8 ;; \
      arm64) arch=arm64; sha=2babb9eb5264860d540849f4b064a6fbdebcdc323657d9d382ce23d313fd5e09 ;; \
      *) echo "unsupported architecture $TARGETARCH" >&2; exit 1 ;; \
    esac \
 && curl -fsSL "https://nodejs.org/dist/v${NODE_VERSION}/node-v${NODE_VERSION}-linux-${arch}.tar.xz" -o /tmp/node.txz \
 && echo "${sha}  /tmp/node.txz" | sha256sum -c - \
 && tar -xJf /tmp/node.txz -C /usr/local --strip-components=1 --exclude=CHANGELOG.md --exclude=LICENSE --exclude=README.md \
 && rm -f /tmp/node.txz
# rtk (the open-source edition, Apache-2.0) shortens the output of shell commands before an agent reads it. It is used only
# when catalog.toml declares its hook (`rtk hook claude`). Pinned, and checked against the release's published checksum.
ARG RTK_VERSION=v1.2.0
RUN case "$TARGETARCH" in \
      amd64) arch=x86_64; sha=a28407dc13038bdc9c2a1f5a047b0c636e0c1d495b15523576e2adb992a06a17 ;; \
      arm64) arch=aarch64; sha=9786c61dbbea704e1468ee7060930d3b45b67f79ba2babfb73463e85340628d9 ;; \
      *) echo "unsupported architecture $TARGETARCH" >&2; exit 1 ;; \
    esac \
 && curl -fsSL "https://github.com/rtk-ai/rtk/releases/download/${RTK_VERSION}/rtk-oss-${arch}-unknown-linux-musl.tar.gz" -o /tmp/rtk.tgz \
 && echo "${sha}  /tmp/rtk.tgz" | sha256sum -c - \
 && tar -xzf /tmp/rtk.tgz -C /tmp rtk \
 && install -m 0755 /tmp/rtk /usr/local/bin/rtk \
 && rm -f /tmp/rtk.tgz /tmp/rtk
COPY --from=warden /usr/local/bin/warden /usr/local/bin/warden
# Warden keeps its audit log and its session tokens here; a volume mounted on it inherits the agent user's ownership.
RUN mkdir -p /var/lib/warden && chown shelf:shelf /var/lib/warden
# The rules an administrator adds to the guard from the admin page: the web service writes here, the worker reads.
RUN mkdir -p /var/lib/shelf-guard && chown shelf:shelf /var/lib/shelf-guard
# What each agent run did, for diagnosing a work: the worker writes it, the web service reads it.
RUN mkdir -p /var/lib/shelf-runs && chown shelf:shelf /var/lib/shelf-runs
# In container mode the worker shares these with the step containers (a volume each, decision 0019). Created here, owned by the
# agent user, so that a new volume mounted on them is writable by the worker, as the folders above are.
RUN mkdir -p /var/lib/shelf/steps /var/lib/shelf/sessions && chown shelf:shelf /var/lib/shelf /var/lib/shelf/steps /var/lib/shelf/sessions
# Where the synced catalog and the managed policy are mounted: owned by the agent user, so a new volume is writable by the sync.
RUN mkdir -p /opt/shelf/catalog /etc/claude-code && chown shelf:shelf /opt/shelf/catalog /etc/claude-code
COPY --from=build --chown=shelf:shelf /app /app
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
# The git revision this image was built from, shown by /healthz. Declared last so it never invalidates the layers above.
ARG SHELF_REVISION=unknown
ENV SHELF_REVISION=$SHELF_REVISION
USER shelf
WORKDIR /app
EXPOSE 8080
CMD ["shelf-web"]

# --- The container of one agent step (decision 0019). The same tools as the worker, run by `shelf-step`, with nothing
# that the worker's own sandbox needs: the container is the boundary, so no bubblewrap and no socat. The runner starts it
# read-only and unprivileged, with the clone, the tools and the sessions as volumes; HOME is a folder of its own.
FROM app AS step
USER root
RUN apt-get purge -y --auto-remove bubblewrap socat \
 && rm -rf /var/lib/apt/lists/* \
 && mkdir -p /home/step && chown 1000:1000 /home/step \
 && usermod --home /home/step shelf
# The user's home in /etc/passwd is the one HOME names: the JVM reads user.home from the user database, and would otherwise
# look for ~/.m2 on the read-only root instead of in the tools volume.
# The tools the worker's set-up installed into the repository's home are found through mise's shims, as in the worker.
ENV HOME=/home/step PATH="/home/step/.local/share/mise/shims:$PATH"
USER 1000
WORKDIR /work
# The runner sets the command itself; this one is what a person gets with `docker run`.
CMD ["shelf-step", "/run/shelf/task.json"]

# --- The runner (decision 0019): the only service that holds the container engine's socket. Python and its own code, and
# nothing else: no git, no agent, no tools, no credential of the product.
FROM python:3.15-slim AS runner
RUN useradd --create-home --uid 1000 runner
COPY --from=build --chown=runner:runner /app /app
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
ARG SHELF_REVISION=unknown
ENV SHELF_REVISION=$SHELF_REVISION
USER runner
WORKDIR /app
CMD ["shelf-runner"]

# --- The default target stays the product's image: `docker build .` and the compose file build it, as before.
FROM app
