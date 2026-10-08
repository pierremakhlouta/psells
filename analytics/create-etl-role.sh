#!/bin/bash
#
# Creates psells_etl, the read-only role the analytics ETL reads the business
# database as, or brings it up to date, in the running stack:
#
#     analytics/create-etl-role.sh
#
# Runs analytics/etl_role.sql as the database's owner, then lets the role log
# in with the password PSELLS_ETL_PASSWORD: from the environment if it is set
# there, as for the sample stack's invented one, or else from .env. It reaches psql
# through the environment of the one command that needs it, read inside the
# container with \getenv, so it is never on a command line, in a file the
# container can read afterwards, or printed. Safe to run again; a changed
# password in .env replaces the old one.
#
# For another project, such as the sample stack, set COMPOSE_PROJECT_NAME:
#
#     COMPOSE_PROJECT_NAME=psells-sample analytics/create-etl-role.sh

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

password="${PSELLS_ETL_PASSWORD:-}"
if [ -z "$password" ] && [ -f "$PROJECT_DIR/.env" ]; then
    password=$(sed -n 's/^PSELLS_ETL_PASSWORD=//p' "$PROJECT_DIR/.env")
fi
if [ -z "$password" ]; then
    cat >&2 <<'MESSAGE'
No PSELLS_ETL_PASSWORD in .env. Add one:
    printf 'PSELLS_ETL_PASSWORD=%s\n' "$(openssl rand -hex 24)" >> .env
MESSAGE
    exit 1
fi

{
    cat "$PROJECT_DIR/analytics/etl_role.sql"
    echo '\getenv etl_password PSELLS_ETL_PASSWORD'
    echo "ALTER ROLE psells_etl LOGIN PASSWORD :'etl_password';"
} | PSELLS_ETL_PASSWORD="$password" docker compose --project-directory "$PROJECT_DIR" \
    exec -T -e PSELLS_ETL_PASSWORD db \
    sh -c 'psql -q -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"'

echo "psells_etl can read products, sales, returns, payments and products_view, and nothing else"
