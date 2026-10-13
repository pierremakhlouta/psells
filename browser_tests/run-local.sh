#!/bin/bash
#
# Runs browser_tests/ on the Mac against the working tree, before anything is
# committed or deployed:
#
#     browser_tests/run-local.sh
#
# The app runs from this folder with uvicorn, on the test database (start it
# with docker compose --profile test up -d --wait db-test), which holds no
# records, and with the sample configuration. In front of it, a throwaway
# nginx from the pinned image, with the repository's configuration and
# static/, and the Mac's own certificate for psells.localhost, which the
# Mac's browsers trust, on https://psells.localhost:18443. Nothing of the
# real stack is touched, and both are stopped at the end, pass or fail.

set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$DIR"

PORT=18443
NAME=psells-browser-nginx
IMAGE=$(grep -o 'nginx:[^ ]*@sha256:[0-9a-f]*' nginx/Dockerfile)

[ -f data/tls/psells.localhost.crt ] ||
    { echo "run-local.sh: no certificate; run ./make-certificate.sh" >&2; exit 1; }

cleanup() {
    docker rm -f "$NAME" > /dev/null 2>&1 || true
    if [ -n "${APP_PID:-}" ]; then
        kill "$APP_PID" 2> /dev/null || true
    fi
}
trap cleanup EXIT

PSELLS_DATABASE_URL="${PSELLS_TEST_DATABASE_URL:-postgresql://psells_test:psells_test@127.0.0.1:5433/psells_test}" \
PSELLS_CONFIG="$DIR/sample_data/config.json" \
    venv/bin/uvicorn api:app --host 127.0.0.1 --port 8000 --log-level warning &
APP_PID=$!

# The Mac as containers reach it, by its IPv4 address: Docker's host-gateway
# name also resolves to an IPv6 address, which nginx tries alone, and the app
# listens on IPv4. The certificate is mounted, never read here; nginx reads
# it as in the stack.
HOST=$(docker run --rm --entrypoint sh "$IMAGE" -c 'getent ahostsv4 host.docker.internal' | awk 'NR == 1 {print $1}')
docker run -d --name "$NAME" --user 101:101 \
    --add-host "app:$HOST" -p "127.0.0.1:$PORT:8443" \
    -v "$DIR/nginx/nginx.conf:/etc/nginx/nginx.conf:ro" \
    -v "$DIR/nginx/snippets:/etc/nginx/snippets:ro" \
    -v "$DIR/nginx/sites/localhost:/etc/nginx/site:ro" \
    -v "$DIR/static:/srv/psells/static:ro" \
    -v "$DIR/data/tls:/etc/nginx/tls:ro" \
    "$IMAGE" > /dev/null

for _ in $(seq 30); do
    code=$(curl -s -o /dev/null -w '%{http_code}' --cacert ~/PSells-CA/ca.crt \
        "https://psells.localhost:$PORT/login" || true)
    [ "$code" = 200 ] && break
    sleep 1
done
[ "$code" = 200 ] || { echo "run-local.sh: the site did not answer ($code)" >&2; exit 1; }

PSELLS_BROWSER_URL="https://psells.localhost:$PORT" venv/bin/pytest -q -p no:cacheprovider browser_tests "$@"
