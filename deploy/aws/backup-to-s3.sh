#!/bin/bash
#
# Daily backup of the demo database on the AWS server, to S3.
#
# Run by psells-backup.timer; deploy/aws/deploy.sh installs it. Also safe to
# run by hand, as root on the server.
#
# Takes a pg_dump of the database in the stack, proves the dump restores by
# restoring it into a throwaway database and counting its products against
# the live one, and only then copies it to the bucket named in Parameter
# Store, under daily/. Nothing is kept on the server. The bucket deletes each
# copy after 30 days, as backup.sh does on the Mac, and the server's role may
# add files there and do nothing else: it cannot read, list or delete them.
#
# The same steps as backup.sh, which backs up the real database on the Mac
# and stays there; this one never runs where the real data is.

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$PROJECT_DIR"

REGION="${PSELLS_AWS_REGION:-ca-central-1}"

# The throwaway database each dump is restored into to prove it restores.
CHECK_DB=backup_check

fail() {
    echo "backup-to-s3.sh: FAILED: $*" >&2
    exit 1
}

# The real records are on the Mac, the only place data/config.json exists.
# They never go to S3.
[ ! -e data/config.json ] ||
    fail "data/config.json exists, so this is not the AWS server; the real data never leaves the Mac"

compose() {
    docker compose -f compose.yaml -f compose.aws.yaml "$@"
}

# Runs a command inside the database container, where pg_dump, pg_restore and
# psql are, and where POSTGRES_USER and POSTGRES_DB are already set. The
# single quotes below are deliberate: those variables are expanded by the
# container's shell, not by this one. Every dump is proved here, in a
# throwaway database in this container, whichever database it came from.
in_db() {
    compose exec -T db sh -c "$1"
}

# The settings deploy.sh wrote, readable by root only, which name the live
# database: the container, or RDS while infra/aws's switch is on. live()
# reaches whichever it is.
set -a
# shellcheck source=/dev/null
. ./.env
set +a
# shellcheck source=deploy/aws/live-database.sh
. deploy/aws/live-database.sh

bucket=$(aws ssm get-parameters-by-path --region "$REGION" --path /psells/backup \
    --query "Parameters[?Name=='/psells/backup/bucket'].Value" --output text)
if [ -z "$bucket" ] || [ "$bucket" = "None" ]; then
    fail "no bucket named in /psells/backup/bucket"
fi

STAMP="$(date -u '+%Y-%m-%d_%H%M%SZ')"
NAME="psells-$STAMP.dump"

# Readable by root only, and gone when the script ends, whatever happens.
umask 077
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
DUMP="$WORK/$NAME"

# From the live database, wherever it is.
live pg_dump --format=custom > "$DUMP" || fail "pg_dump failed"
[ -s "$DUMP" ] || fail "pg_dump wrote nothing"

# A dump nobody has restored is not a backup.
in_db "dropdb -U \"\$POSTGRES_USER\" --if-exists $CHECK_DB 2> /dev/null; createdb -U \"\$POSTGRES_USER\" $CHECK_DB" \
    || fail "could not create the $CHECK_DB database"
in_db "pg_restore -U \"\$POSTGRES_USER\" -d $CHECK_DB --no-owner --exit-on-error" \
    < "$DUMP" || fail "the new dump does not restore"
RESTORED="$(in_db "psql -U \"\$POSTGRES_USER\" -d $CHECK_DB -tAc 'SELECT count(*) FROM products'")" \
    || fail "could not count products in the restored copy"
LIVE="$(live psql -tAc "SELECT count(*) FROM products")" \
    || fail "could not count products in the live database"
in_db "dropdb -U \"\$POSTGRES_USER\" $CHECK_DB" \
    || fail "could not drop the $CHECK_DB database"

# Valid and empty is worse than no backup, because it looks fine in a listing.
[ "$RESTORED" -gt 0 ] || fail "the restored copy contains no products"
[ "$RESTORED" = "$LIVE" ] \
    || fail "the restored copy has $RESTORED products and the database has $LIVE"

aws s3 cp --region "$REGION" --only-show-errors "$DUMP" "s3://$bucket/daily/$NAME" \
    || fail "could not copy $NAME to the bucket"

echo "ok  $NAME  $(wc -c < "$DUMP" | tr -d ' ') bytes  $RESTORED products, restored and counted, in s3://$bucket/daily/"
