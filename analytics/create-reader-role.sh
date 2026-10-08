#!/bin/bash
#
# Creates psells_reader, the read-only role the app reads the warehouse's
# views as, or brings it up to date, in the running warehouse:
#
#     analytics/create-reader-role.sh
#
# Runs analytics/reader_role.sql as the warehouse's owner, then lets the role
# log in with the password PSELLS_READER_PASSWORD: from the environment if it
# is set there, as for the sample stack's invented one, or else from .env. It
# reaches psql through the environment of the one command that needs it, read
# inside the container with \getenv, so it is never on a command line or
# printed. The views are granted to it by the next ETL run, which makes them.
# Safe to run again; a changed password in .env replaces the old one.
#
# For another project, such as the sample stack, set COMPOSE_PROJECT_NAME.

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

password="${PSELLS_READER_PASSWORD:-}"
if [ -z "$password" ] && [ -f "$PROJECT_DIR/.env" ]; then
    password=$(sed -n 's/^PSELLS_READER_PASSWORD=//p' "$PROJECT_DIR/.env")
fi
if [ -z "$password" ]; then
    cat >&2 <<'MESSAGE'
No PSELLS_READER_PASSWORD in .env. Add one:
    printf 'PSELLS_READER_PASSWORD=%s\n' "$(openssl rand -hex 24)" >> .env
MESSAGE
    exit 1
fi

{
    cat "$PROJECT_DIR/analytics/reader_role.sql"
    echo '\getenv reader_password PSELLS_READER_PASSWORD'
    echo "ALTER ROLE psells_reader LOGIN PASSWORD :'reader_password';"
} | PSELLS_READER_PASSWORD="$password" docker compose --project-directory "$PROJECT_DIR" \
    -f "$PROJECT_DIR/compose.yaml" -f "$PROJECT_DIR/compose.analytics.yaml" \
    exec -T -e PSELLS_READER_PASSWORD warehouse \
    psql -q -v ON_ERROR_STOP=1 -U psells_warehouse -d psells_warehouse

echo "psells_reader can read the warehouse's five views, and nothing else, from the next ETL run"
