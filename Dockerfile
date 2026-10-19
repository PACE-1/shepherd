# Server image: Python core + compiled React UI (served at /v2). Roadmap #12, #13.
# Access control: the image runs in server mode, so it refuses to start without
# a token (see docs/SERVER.md):
#   docker run -p 127.0.0.1:22400:22400 -v shepherd-data:/data \
#     -e SHEPHERD_ACCESS_TOKEN=<long random secret> <image>
# Publish on loopback and put TLS in front of it for remote access.
# Single worker is required: per-process caches and one sync owner.

FROM node:26-slim AS web
WORKDIR /web
RUN corepack enable && corepack prepare pnpm@12.11.2 --activate
COPY web/package.json web/pnpm-lock.yaml web/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile
COPY web/ ./
RUN pnpm build

FROM python:3.14-slim
WORKDIR /app
COPY requirements-server.txt requirements-linux-py312.lock ./
RUN pip install --no-cache-dir -r requirements-server.txt -c requirements-linux-py312.lock
COPY VERSION ./VERSION
COPY src ./src
COPY --from=web /web/dist ./web/dist
# Unprivileged runtime user with a fixed UID/GID (#153). /data is created and
# owned by it, so a fresh named volume inherits that ownership. A volume written
# by an earlier (root) image needs the one-time chown in docs/SERVER.md.
RUN groupadd --gid 10001 shepherd && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin shepherd \
    && mkdir /data && chown shepherd:shepherd /data
ENV SHEPHERD_HOME=/data PYTHONPATH=/app/src PYTHONUNBUFFERED=1 SHEPHERD_SERVER_MODE=1
VOLUME /data
USER 10001:10001
EXPOSE 22400
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s CMD python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:22400/healthz', timeout=4)"
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "22400", "--workers", "1"]
