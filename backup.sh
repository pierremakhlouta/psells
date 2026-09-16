#!/bin/bash
#
# Daily backup of the PSells database.
#
# Run by cron. See README for the crontab line.
#
# Takes a verified copy of data/psells.db into ~/PSells-Backups/daily/,
# appends a line to ~/PSells-Backups/backup.log, and removes copies older
# than KEEP_DAYS.

# -e  stop at the first command that fails, rather than carrying on and
#     reporting success at the end.
# -u  stop if an unset variable is used, so a typo in a path fails loudly
#     instead of expanding to nothing.
# -o pipefail  make a pipeline fail if any stage fails, not just the last.
set -euo pipefail

# Where the project is, worked out from where this script is, rather than
# hardcoded. The project folder has already moved once, and an absolute path
# written in here would have broken silently the moment it did.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

DB_FILE="$SCRIPT_DIR/data/psells.db"
CONFIG_FILE="$SCRIPT_DIR/data/config.json"

BACKUP_DIR="$HOME/PSells-Backups/daily"
LOG_FILE="$HOME/PSells-Backups/backup.log"
KEEP_DAYS=30

# Full path, because cron runs with a minimal environment and a PATH that
# cannot be assumed to match an interactive shell's.
SQLITE=/usr/bin/sqlite3

log() {
    printf '%s  %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$1" >> "$LOG_FILE"
}

fail() {
    log "FAILED: $1"
    exit 1
}

mkdir -p "$BACKUP_DIR"

[ -x "$SQLITE" ] || fail "sqlite3 not found at $SQLITE"
[ -f "$DB_FILE" ] || fail "database not found at $DB_FILE"

STAMP="$(date '+%Y-%m-%d_%H%M%S')"
TARGET="$BACKUP_DIR/psells-$STAMP.db"

# SQLite's own backup command, never cp. It takes the right locks and copies
# the database whatever journal mode it is in. A plain cp of the .db file can
# miss changes that are still sitting in a journal beside it, and in WAL mode
# it can produce a file with no data in it at all.
"$SQLITE" "$DB_FILE" ".backup '$TARGET'" || fail "backup command failed"

[ -f "$TARGET" ] || fail "backup file was not created"

# A copy nobody has checked is not a backup. Ask the new file whether it is a
# valid database before the old ones get cleaned up on the strength of it.
CHECK="$("$SQLITE" "$TARGET" 'PRAGMA integrity_check;')" \
    || fail "could not read the new backup"

[ "$CHECK" = "ok" ] || fail "integrity check on the new backup said: $CHECK"

PRODUCTS="$("$SQLITE" "$TARGET" 'SELECT COUNT(*) FROM products;')" \
    || fail "could not count products in the new backup"

[ "$PRODUCTS" -gt 0 ] || fail "the new backup contains no products"

# The partner rate lives here and is in no git repository, so losing it means
# the application will not start. It is 42 bytes; carry it along.
cp "$CONFIG_FILE" "$BACKUP_DIR/config-$STAMP.json" \
    || fail "could not copy the config file"

BYTES="$(wc -c < "$TARGET" | tr -d ' ')"

log "ok  psells-$STAMP.db  ${BYTES} bytes  ${PRODUCTS} products"

# Remove old copies. The -name filter matters: a -delete with a loose pattern
# is how people remove things they meant to keep.
OLD_DBS="$(find "$BACKUP_DIR" -name 'psells-*.db' -mtime +"$KEEP_DAYS" -print -delete | wc -l | tr -d ' ')"
OLD_CONFIGS="$(find "$BACKUP_DIR" -name 'config-*.json' -mtime +"$KEEP_DAYS" -print -delete | wc -l | tr -d ' ')"

if [ "$OLD_DBS" -gt 0 ] || [ "$OLD_CONFIGS" -gt 0 ]; then
    log "removed $OLD_DBS database and $OLD_CONFIGS config copies older than $KEEP_DAYS days"
fi
