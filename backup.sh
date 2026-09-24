#!/bin/bash
#
# Daily backup of the PSells database.
#
# Run by launchd; launchd/local.psells.backup.plist is the job, and the README
# shows how to install it. Also safe to run by hand.
#
# Takes a pg_dump of the database in the Compose stack into
# ~/PSells-Backups/daily/, proves the dump restores, appends a line to
# ~/PSells-Backups/backup.log, and removes copies older than KEEP_DAYS.

# -e  stop at the first command that fails, rather than carrying on and
#     reporting success at the end.
# -u  stop if an unset variable is used, so a typo in a path fails loudly
#     instead of expanding to nothing.
# -o pipefail  make a pipeline fail if any stage fails, not just the last.
set -euo pipefail

# Where the project is, worked out from where this script is, rather than
# hardcoded. The project folder has already moved once, and an absolute path
# written in here would have broken silently the moment it did. compose.yaml
# and .env are read from here.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

CONFIG_FILE="$SCRIPT_DIR/data/config.json"

BACKUP_DIR="$HOME/PSells-Backups/daily"
LOG_FILE="$HOME/PSells-Backups/backup.log"
KEEP_DAYS=30

# The throwaway database each dump is restored into to prove it restores.
CHECK_DB=backup_check

# launchd, like cron, starts a job with a minimal PATH that does not include
# the docker command. Docker Desktop links it into /usr/local/bin, and older
# installs keep it in ~/.docker/bin.
PATH="/usr/local/bin:$HOME/.docker/bin:/opt/homebrew/bin:/usr/bin:/bin"
export PATH

log() {
    printf '%s  %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$1" >> "$LOG_FILE"
}

fail() {
    log "FAILED: $1"
    exit 1
}

compose() {
    docker compose --project-directory "$SCRIPT_DIR" "$@"
}

# Runs a command inside the database container, where psql, pg_dump and
# pg_restore are, and where POSTGRES_USER and POSTGRES_DB are already set. The
# single quotes around each command below are deliberate: the variables are
# expanded by the container's shell, not by this one.
in_db() {
    compose exec -T db sh -c "$1"
}

mkdir -p "$BACKUP_DIR"

STAMP="$(date '+%Y-%m-%d_%H%M%S')"
TARGET="$BACKUP_DIR/psells-$STAMP.dump"
PARTIAL="$TARGET.partial"

# Whatever happens below, never leave a half-written dump behind looking like
# a backup. The finished file only gets its real name once it has been proved.
trap 'rm -f "$PARTIAL"' EXIT

command -v docker > /dev/null || fail "docker not found on PATH ($PATH)"

# launchd runs a missed job as soon as the Mac wakes, which can be before
# Docker Desktop has finished starting. Give it two minutes.
for _ in $(seq 1 24); do
    docker info > /dev/null 2>&1 && break
    sleep 5
done
docker info > /dev/null 2>&1 \
    || fail "Docker Desktop is not running, so the database cannot be reached"

# Starting the database changes no records and publishes nothing. The
# application is left as it is.
compose up -d --wait db > /dev/null 2>&1 \
    || fail "could not start the database container"

# pg_dump takes a consistent snapshot while the database stays in use. The
# custom format is compressed and is what pg_restore reads.
# shellcheck disable=SC2016
in_db 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom' \
    > "$PARTIAL" || fail "pg_dump failed"

[ -s "$PARTIAL" ] || fail "pg_dump wrote nothing"

# A dump nobody has restored is not a backup. Restore it into a throwaway
# database on the same server, count its products, compare that with the live
# database, and drop the throwaway, before old copies are deleted on the
# strength of it. A throwaway left by a run that failed is dropped first.
# shellcheck disable=SC2016
# --if-exists still prints a notice when there is nothing to drop; it is not
# worth a line in the log every morning.
in_db "dropdb -U \"\$POSTGRES_USER\" --if-exists $CHECK_DB 2> /dev/null; createdb -U \"\$POSTGRES_USER\" $CHECK_DB" \
    || fail "could not create the $CHECK_DB database"

in_db "pg_restore -U \"\$POSTGRES_USER\" -d $CHECK_DB --no-owner --exit-on-error" \
    < "$PARTIAL" || fail "the new dump does not restore"

RESTORED="$(in_db "psql -U \"\$POSTGRES_USER\" -d $CHECK_DB -tAc 'SELECT count(*) FROM products'")" \
    || fail "could not count products in the restored copy"

# shellcheck disable=SC2016
LIVE="$(in_db 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "SELECT count(*) FROM products"')" \
    || fail "could not count products in the live database"

in_db "dropdb -U \"\$POSTGRES_USER\" $CHECK_DB" \
    || fail "could not drop the $CHECK_DB database"

# A backup that is valid and empty is worse than no backup, because it looks
# fine in a listing.
[ "$RESTORED" -gt 0 ] || fail "the restored copy contains no products"

# A product added in the seconds between the dump and the count would also
# land here; the next run settles it.
[ "$RESTORED" = "$LIVE" ] \
    || fail "the restored copy has $RESTORED products and the database has $LIVE"

mv "$PARTIAL" "$TARGET"

# The partner rate lives here and is in no git repository, so losing it means
# the application will not start. It is 42 bytes; carry it along.
cp "$CONFIG_FILE" "$BACKUP_DIR/config-$STAMP.json" \
    || fail "could not copy the config file"

BYTES="$(wc -c < "$TARGET" | tr -d ' ')"

log "ok  psells-$STAMP.dump  ${BYTES} bytes  ${RESTORED} products, restored and counted"

# Remove old copies. The -name filters matter: a -delete with a loose pattern
# is how people remove things they meant to keep. The .db pattern retires the
# SQLite copies from before PostgreSQL as they age; the verified archive of the
# last SQLite database is in its own folder and is not touched.
OLD_DUMPS="$(find "$BACKUP_DIR" -name 'psells-*.dump' -mtime +"$KEEP_DAYS" -print -delete | wc -l | tr -d ' ')"
OLD_DBS="$(find "$BACKUP_DIR" -name 'psells-*.db' -mtime +"$KEEP_DAYS" -print -delete | wc -l | tr -d ' ')"
OLD_CONFIGS="$(find "$BACKUP_DIR" -name 'config-*.json' -mtime +"$KEEP_DAYS" -print -delete | wc -l | tr -d ' ')"

if [ "$OLD_DUMPS" -gt 0 ] || [ "$OLD_DBS" -gt 0 ] || [ "$OLD_CONFIGS" -gt 0 ]; then
    log "cleanup: removed files older than $KEEP_DAYS days, $OLD_DUMPS dump, $OLD_DBS old SQLite, $OLD_CONFIGS config"
fi
