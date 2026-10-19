#!/usr/bin/env bash
# Prove backup and restore across Docker volumes (#19): seed a profile in volume A,
# back it up, restore into a clean volume B, and read it back through the API.
# Usage: tools/verify_docker_restore.sh [image]   (builds shepherd:restore-check if omitted)
set -euo pipefail
cd "$(dirname "$0")/.."
IMG=${1:-}
if [ -z "$IMG" ]; then IMG=shepherd:restore-check; docker build -q -t "$IMG" . >/dev/null; fi
TOKEN=restore-check-token
A=de-restore-a-$$; B=de-restore-b-$$; OUT=$(mktemp -d)
cleanup() { docker rm -f "$A-srv" "$B-srv" >/dev/null 2>&1 || true; docker volume rm "$A" "$B" >/dev/null 2>&1 || true; rm -rf "$OUT"; }
trap cleanup EXIT
api() { # container port method path [json]
  curl -s -m 20 -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -X "$3" ${5:+-d "$5"} "http://127.0.0.1:$2$4"; }
wait_up() { for _ in $(seq 1 60); do curl -sf -m 2 "http://127.0.0.1:$1/healthz" >/dev/null && return 0; sleep 1; done; echo "server on $1 did not start" >&2; return 1; }

chmod a+rwx "$OUT"  # the image runs as UID 10001, not the host user
docker volume create "$A" >/dev/null; docker volume create "$B" >/dev/null
docker run -d --name "$A-srv" -p 127.0.0.1:22491:22400 -v "$A":/data -e SHEPHERD_ACCESS_TOKEN=$TOKEN "$IMG" >/dev/null
wait_up 22491
api x 22491 POST /api/profiles/create '{"name":"Restore Rider","color":"#22c55e"}' >/dev/null
ID=$(api x 22491 GET /api/profiles | python3 -c "import json,sys; print([p['id'] for p in json.load(sys.stdin)['profiles'] if p['name']=='Restore Rider'][0])")
api x 22491 POST /api/profiles/switch "{\"id\":\"$ID\"}" >/dev/null
api x 22491 POST /api/setup/save '{"ftp":287,"weight":68.5}' >/dev/null
BEFORE=$(api x 22491 GET /api/profiles | python3 -c "import json,sys; d=json.load(sys.stdin); print(sorted((p['id'],p.get('ftp')) for p in d['profiles']))")
docker stop -t 10 "$A-srv" >/dev/null

docker run --rm -v "$A":/data -v "$OUT":/out "$IMG" python -m backup create /out/backup.tar.gz --home /data
docker run --rm -v "$OUT":/out "$IMG" python -m backup verify /out/backup.tar.gz
docker run --rm -v "$B":/data -v "$OUT":/out "$IMG" python -m backup restore /out/backup.tar.gz --home /data

docker run -d --name "$B-srv" -p 127.0.0.1:22492:22400 -v "$B":/data -e SHEPHERD_ACCESS_TOKEN=$TOKEN "$IMG" >/dev/null
wait_up 22492
AFTER=$(api x 22492 GET /api/profiles | python3 -c "import json,sys; d=json.load(sys.stdin); print(sorted((p['id'],p.get('ftp')) for p in d['profiles']))")
echo "before: $BEFORE"; echo "after:  $AFTER"
[ "$BEFORE" = "$AFTER" ] && echo "RESTORE OK: the restored volume serves the same profiles" || { echo "MISMATCH" >&2; exit 1; }
