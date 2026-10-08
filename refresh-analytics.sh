#!/bin/bash
#
# Rebuilds the analytics warehouse from the real records, so the analytics
# page is never more than an hour behind them.
#
# Run by launchd on the hour and once at login;
# launchd/local.psells.analytics.plist is the job, and the README shows how to
# install it. Also safe to run by hand.
#
# It waits for Docker Desktop and for the business database to be healthy, but
# never starts, stops or recreates the database, the app or the proxy: that is
# start-stack.sh's job, which runs at the same login. It brings up only the
# warehouse, then runs the ETL with --no-deps. It builds nothing, so it runs the
# analytics image as it was last built, never an edit nobody has rebuilt.
#
# Each run appends one line to ~/Library/Logs/psells-etl.log: ok with the ETL's
# counts, or FAILED with the reason. Never a figure: the ETL prints none. The
# analytics page shows a warning when the warehouse is more than two hours old,
# so two failed runs in a row are seen where the figures are read.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="$HOME/Library/Logs/psells-etl.log"

# launchd's PATH lacks docker; see start-stack.sh. Appended, so a test's
# stand-in, found first, is the one used.
PATH="$PATH:/usr/local/bin:$HOME/.docker/bin:/opt/homebrew/bin:/usr/bin:/bin"
export PATH

log() {
    mkdir -p "$(dirname "$LOG_FILE")"
    printf '%s  %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$1" >> "$LOG_FILE"
}

fail() {
    log "FAILED: $1"
    exit 1
}

compose() {
    docker compose --project-directory "$SCRIPT_DIR" \
        -f "$SCRIPT_DIR/compose.yaml" -f "$SCRIPT_DIR/compose.analytics.yaml" "$@"
}

# Only in the real stack's folder, the one with data/config.json.
[ -e "$SCRIPT_DIR/data/config.json" ] ||
    fail "no data/config.json in $SCRIPT_DIR, so this is not the real stack's folder"

command -v docker > /dev/null || fail "docker not found on PATH ($PATH)"

# At login Docker Desktop can take minutes; twenty, as start-stack.sh waits.
for _ in $(seq 1 240); do
    docker info > /dev/null 2>&1 && break
    sleep 5
done
docker info > /dev/null 2>&1 || fail "Docker Desktop did not start within twenty minutes"

# The database is start-stack.sh's to start; this waits up to ten minutes for
# it to be healthy and otherwise leaves this hour out.
for _ in $(seq 1 120); do
    [ "$(docker inspect --format '{{.State.Health.Status}}' psells-db-1 2> /dev/null)" = healthy ] && break
    sleep 5
done
[ "$(docker inspect --format '{{.State.Health.Status}}' psells-db-1 2> /dev/null)" = healthy ] ||
    fail "the business database was not healthy within ten minutes"

compose up -d --wait warehouse > /dev/null 2>&1 || fail "the warehouse did not come up healthy"

if output=$(compose run --rm --no-deps etl 2>&1); then
    log "ok  $(printf '%s\n' "$output" | tail -n 1)"
else
    fail "the ETL did not complete: $(printf '%s\n' "$output" | tail -n 1)"
fi
