#!/bin/bash
#
# Starts the real stack when the Mac logs in, if it is not already running.
#
# Run by launchd at login; launchd/local.psells.start.plist is the job, and the
# README shows how to install it. Also safe to run by hand.
#
# Why it exists: on 7 October 2026 the Mac booted at 08:44, Docker Desktop
# started and quit within seconds, and when it came back about fifteen minutes
# later it restarted none of the three containers, restart: unless-stopped
# notwithstanding. Only the 09:00 backup, which starts the database itself,
# brought anything back. On a Linux server Docker's restart policy is enough;
# behind Docker Desktop on a Mac it is not something to rely on.
#
# It waits for Docker Desktop, then runs docker compose up -d --wait
# --no-recreate: it starts whatever is not running and leaves every running
# container exactly as it is. It builds nothing and changes no configuration,
# so a git pull that changed compose.yaml is not applied behind anyone's back.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="$HOME/Library/Logs/psells-start.log"

# launchd starts a job with a minimal PATH that does not include the docker
# command; see backup.sh. Added after whatever PATH there is, so a docker
# found first, as a test's stand-in is, is the one used.
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

# The real stack is the one folder that holds data/config.json. Anywhere else,
# a copy or a checkout, this starts nothing.
[ -e "$SCRIPT_DIR/data/config.json" ] ||
    fail "no data/config.json in $SCRIPT_DIR, so this is not the real stack's folder"

command -v docker > /dev/null || fail "docker not found on PATH ($PATH)"

# Docker Desktop can take a long time after a login, and on 7 October it quit
# and started again; twenty minutes covers what was seen.
for _ in $(seq 1 240); do
    docker info > /dev/null 2>&1 && break
    sleep 5
done
docker info > /dev/null 2>&1 || fail "Docker Desktop did not start within twenty minutes"

docker compose --project-directory "$SCRIPT_DIR" up -d --wait --no-recreate > /dev/null 2>&1 \
    || fail "docker compose up did not bring the stack up healthy"

log "ok  stack up: $(docker compose --project-directory "$SCRIPT_DIR" ps --format '{{.Service}}' | sort | tr '\n' ' ')"
