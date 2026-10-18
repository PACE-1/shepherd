#!/usr/bin/env bash
# Prove the upgrade path from a root-owned volume (#153): files left by an image
# that ran as root are not writable by the unprivileged user, and the documented
# one-time chown fixes it. Also checks the container does not run as root.
# Usage: tools/verify_docker_upgrade.sh [image]   (builds shepherd:upgrade-check if omitted)
set -euo pipefail
cd "$(dirname "$0")/.."
IMG=${1:-}
if [ -z "$IMG" ]; then IMG=shepherd:upgrade-check; docker build -q -t "$IMG" . >/dev/null; fi
VOL=de-upgrade-$$; NAME=$VOL-srv; PORT=22494
cleanup() { docker rm -f "$NAME" >/dev/null 2>&1 || true; docker volume rm "$VOL" >/dev/null 2>&1 || true; }
trap cleanup EXIT
start() { docker rm -f "$NAME" >/dev/null 2>&1 || true
  docker run -d --name "$NAME" -p 127.0.0.1:$PORT:22400 -v "$VOL":/data -e SHEPHERD_ACCESS_TOKEN=upgrade-check-token "$IMG" >/dev/null; }
up() { for _ in $(seq 1 30); do curl -sf -m 2 "http://127.0.0.1:$PORT/healthz" >/dev/null && return 0; sleep 1; done; return 1; }
[ "$(docker run --rm "$IMG" id -u)" != 0 ] || { echo "image runs as root" >&2; exit 1; }
docker volume create "$VOL" >/dev/null
# Simulate a volume written by the old root image.
docker run --rm --user 0 -v "$VOL":/data "$IMG" sh -c 'mkdir -p /data/profiles && echo old > /data/profiles/legacy.txt && chown -R 0:0 /data && chmod -R go-w /data'
start
if up; then echo "control failed: server started on a root-owned volume" >&2; exit 1; fi
# The documented fix (docs/SERVER.md, Upgrading to 4.0).
docker run --rm --user 0 -v "$VOL":/data "$IMG" chown -R 10001:10001 /data
start
up || { docker logs "$NAME" >&2; echo "server did not start after the chown" >&2; exit 1; }
[ "$(docker exec "$NAME" cat /data/profiles/legacy.txt)" = old ] || { echo "legacy data lost" >&2; exit 1; }
echo "UPGRADE OK: root-owned volume fails before the chown, runs as UID 10001 after it"
