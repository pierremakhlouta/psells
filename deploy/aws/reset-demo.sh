#!/bin/bash
#
# Puts the demo's invented records back, every night, so a public login can
# be shared: visitors may add, edit and delete anything, and by morning the
# demo is as sample_data/seed.sql describes it again.
#
# Run by psells-reset.timer; deploy/aws/deploy.sh installs it. Also safe to
# run by hand, as root on the server.
#
# In one transaction it empties the products, sales, returns, payments and
# the corrections log, with their ids started again, and loads the seed, so
# a failure halfway leaves the demo as it was. The corrections go too: they
# describe records that no longer exist, by ids the seed hands out again.
# The login is kept. Then the warehouse is rebuilt, so the analytics page
# shows the same records.
#
# Never where the real data is: it refuses to run beside data/config.json,
# which exists only on the Mac.

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

fail() {
    echo "reset-demo.sh: FAILED: $*" >&2
    exit 1
}

# The statements, one transaction, written to standard output: the tables
# emptied, then the seed without its own BEGIN and COMMIT.
reset_sql() {
    echo "BEGIN;"
    echo "TRUNCATE corrections, sales, returns, payments, products RESTART IDENTITY;"
    grep -v -x -e 'BEGIN;' -e 'COMMIT;' "$PROJECT_DIR/sample_data/seed.sql"
    echo "COMMIT;"
}

compose() {
    docker compose -f compose.yaml -f compose.aws.yaml \
        -f compose.analytics.yaml -f compose.aws-analytics.yaml "$@"
}

main() {
    cd "$PROJECT_DIR"
    [ ! -e data/config.json ] ||
        fail "data/config.json exists, so this is not the AWS server; the real records are never reset"

    # The settings deploy.sh wrote, which name the live database: the
    # container, or RDS while infra/aws's switch is on.
    set -a
    # shellcheck source=/dev/null
    . ./.env
    set +a
    # shellcheck source=deploy/aws/live-database.sh
    . deploy/aws/live-database.sh

    reset_sql | live psql -q -v ON_ERROR_STOP=1 > /dev/null ||
        fail "the records could not be put back; the demo is as it was"
    echo "reset: $(live psql -tA -c "SELECT count(*) FROM products") products, $(live psql -tA -c "SELECT count(*) FROM sales") sales"

    compose run --rm --no-deps etl || fail "the analytics ETL did not complete"
}

# Sourced by the tests for reset_sql alone.
if [ "${BASH_SOURCE[0]}" = "$0" ]; then
    main "$@"
fi
