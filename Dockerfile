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
 && apt-get install -y --no-install-recommends git ca-certificates bubblewrap socat ripgrep \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --create-home --uid 1000 shelf
COPY --from=build --chown=shelf:shelf /app /app
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
USER shelf
WORKDIR /app
EXPOSE 8080
CMD ["shelf-web"]
