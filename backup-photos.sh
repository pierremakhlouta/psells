#!/bin/bash
#
# The photos' part of the daily backup. Run by backup.sh after the database's
# part, with the same stamp; safe to run by hand: ./backup-photos.sh STAMP
#
# Archives the photos volume, as the app container sees it, into
# ~/PSells-Backups/photos/photos-STAMP.tar, proves every photo the database
# records is in it, and sends an encrypted copy into iCloud Drive with
# offsite-backup.sh --photos. A photo is never changed once stored (each is a
# new file with a new name), so when the archive holds exactly the files the
# newest one does, it is not kept: that one still holds them. Old archives go
# after KEEP_DAYS, except the newest, which is kept however old it is.
#
# Prints one line saying what it did; exits 1 with the reason otherwise.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PHOTO_BACKUP_DIR="${PSELLS_PHOTO_BACKUP_DIR:-$HOME/PSells-Backups/photos}"
KEEP_DAYS=30

# backup.sh hands its PATH down, docker included; these are for a run by
# hand. Appended, so a test's stand-in, found first, is the one used.
PATH="$PATH:/usr/local/bin:$HOME/.docker/bin:/opt/homebrew/bin:/usr/bin:/bin"
export PATH

die() {
    echo "$1" >&2
    exit 1
}

[ $# -eq 1 ] || die "usage: backup-photos.sh STAMP"
STAMP=$1

compose() {
    docker compose --project-directory "$SCRIPT_DIR" "$@"
}

mkdir -p "$PHOTO_BACKUP_DIR"
TARGET="$PHOTO_BACKUP_DIR/photos-$STAMP.tar"
PARTIAL="$TARGET.partial"
trap 'rm -f "$PARTIAL"' EXIT

# The photos are read through the app, the one container that mounts them.
# Started if it is not running, never recreated: a backup must not change
# which build is serving.
compose up -d --wait --no-recreate app > /dev/null 2>&1 \
    || die "could not start the app container, which holds the photos"

compose exec -T app tar -cf - -C /photos . > "$PARTIAL" \
    || die "could not archive the photos"

# The photos in an archive, one name a line, sorted. tar -t reads the whole
# archive, so one cut short fails here.
names() {
    tar -tf "$1" | sed -n 's|^\./||; /\.jpg$/p' | sort
}

ARCHIVED="$(names "$PARTIAL")" || die "the new archive does not read back"

# Every photo the database records must be in the archive. A file with no
# row is only space left by a delete that failed after its row went, so it
# is counted, not refused.
# shellcheck disable=SC2016
RECORDED="$(compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "SELECT file_name FROM photos ORDER BY 1"' | sort)" \
    || die "could not list the photos in the database"

MISSING="$(comm -23 <(printf '%s\n' "$RECORDED" | sed '/^$/d') <(printf '%s\n' "$ARCHIVED" | sed '/^$/d'))"
[ -z "$MISSING" ] \
    || die "$(printf '%s\n' "$MISSING" | wc -l | tr -d ' ') photos the database records are not in the volume, first $(printf '%s\n' "$MISSING" | head -1)"

COUNT="$(printf '%s\n' "$ARCHIVED" | sed '/^$/d' | wc -l | tr -d ' ')"
SPARE="$(comm -13 <(printf '%s\n' "$RECORDED" | sed '/^$/d') <(printf '%s\n' "$ARCHIVED" | sed '/^$/d') | wc -l | tr -d ' ')"

# The newest archive kept so far, if any. Stamps sort as times do.
NEWEST="$(find "$PHOTO_BACKUP_DIR" -maxdepth 1 -name 'photos-*.tar' -print | sort | tail -1)"

if [ -n "$NEWEST" ] && [ "$(names "$NEWEST")" = "$ARCHIVED" ]; then
    echo "unchanged  $COUNT photos, still in $(basename "$NEWEST"), $SPARE without a row"
    exit 0
fi

mv "$PARTIAL" "$TARGET"

# Without its iCloud copy the archive is not kept either: the next run would
# find it unchanged and never send it. Removed, the next run makes it again.
OFFSITE="$("$SCRIPT_DIR/offsite-backup.sh" --photos "photos-$STAMP.tar" 2>&1)" \
    || { rm -f "$TARGET"; die "the off-Mac copy: $OFFSITE"; }

find "$PHOTO_BACKUP_DIR" -maxdepth 1 -name 'photos-*.tar' -mtime +"$KEEP_DAYS" \
    ! -name "photos-$STAMP.tar" -delete

echo "photos-$STAMP.tar  $COUNT photos, $SPARE without a row; offsite $OFFSITE"
