#!/bin/bash
#
# Deploys PSells on the AWS server, with the invented sample data.
#
# Run as root on the server, through SSM, after checking out the commit to
# deploy. The checkout comes first and outside this script, because a running
# bash script that git rewrites under it can go on to run lines of the new
# version:
#
#     git -C /opt/psells fetch --quiet origin
#     git -C /opt/psells checkout --quiet --detach <commit>
#     /opt/psells/deploy/aws/deploy.sh
#
# Writes .env from Parameter Store, builds and starts the stack with
# compose.aws.yaml laid over compose.yaml, loads sample_data/seed.sql into a
# database that has no products yet, and installs the timer that renews the
# certificate. Safe to run again: .env is rewritten, the stack is brought up
# to date, and a database with records in it is left alone.
#
# The server never sees the real records or the real partner percentage:
# .env points the app at sample_data/config.json.

set -euo pipefail

# The project folder, two levels up from this script, rather than a path
# written in here.
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$PROJECT_DIR"

REGION="${PSELLS_AWS_REGION:-ca-central-1}"
PARAMETERS=/psells/postgres

fail() {
    echo "deploy.sh: $*" >&2
    exit 1
}

# The real configuration exists on the Mac only. Its .env holds the real
# database's password, which this script would overwrite.
[ ! -e data/config.json ] ||
    fail "data/config.json exists, so this is not the AWS server; refusing to touch .env here"

# The renewal timer's unit runs in /opt/psells, so the project must be there.
[ "$PROJECT_DIR" = /opt/psells ] ||
    fail "the project is at $PROJECT_DIR; the server keeps it at /opt/psells"

compose() {
    docker compose -f compose.yaml -f compose.aws.yaml "$@"
}

echo "== .env from Parameter Store ($PARAMETERS)"
# name<TAB>value, one per line. The password never reaches the terminal.
values=$(aws ssm get-parameters-by-path --region "$REGION" --path "$PARAMETERS" \
    --with-decryption --query 'Parameters[].[Name,Value]' --output text)

user="" password="" database=""
while IFS=$'\t' read -r name value; do
    # Letters, digits, _ and - only, so nothing in a value can break .env or
    # the database address the app builds from it.
    [[ "$value" =~ ^[A-Za-z0-9_-]+$ ]] || fail "$name holds characters .env cannot take"
    case "$name" in
        "$PARAMETERS/user") user="$value" ;;
        "$PARAMETERS/password") password="$value" ;;
        "$PARAMETERS/db") database="$value" ;;
    esac
done <<< "$values"
[ -n "$user" ] && [ -n "$password" ] && [ -n "$database" ] ||
    fail "expected user, password and db under $PARAMETERS"

# Readable by root only, written whole and then moved into place, so a
# failure halfway never leaves a .env without its password.
umask 077
cat > .env.new <<EOF
# Written by deploy/aws/deploy.sh from Parameter Store. Rewritten on every
# deploy; change the parameters, not this file.
POSTGRES_USER=$user
POSTGRES_PASSWORD=$password
POSTGRES_DB=$database
PSELLS_CONFIG_FILE=./sample_data/config.json
EOF
mv .env.new .env
umask 022

echo "== stack"
compose up -d --build --wait

echo "== sample data"
# The single quotes are deliberate: $POSTGRES_USER and $POSTGRES_DB are
# expanded by the shell inside the database container, from its environment.
# shellcheck disable=SC2016
products=$(compose exec -T db sh -c \
    'psql -tA -U "$POSTGRES_USER" "$POSTGRES_DB" -c "SELECT count(*) FROM products"')
if [ "$products" = "0" ]; then
    # shellcheck disable=SC2016
    compose exec -T db sh -c \
        'psql -q -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" "$POSTGRES_DB"' < sample_data/seed.sql
    echo "loaded sample_data/seed.sql"
else
    echo "the database has $products products; left as it is"
fi

echo "== certificate renewal"
install -m 644 deploy/aws/psells-certbot-renew.service deploy/aws/psells-certbot-renew.timer \
    /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now psells-certbot-renew.timer
systemctl list-timers psells-certbot-renew.timer --no-pager

echo "== deployed $(git log --oneline -1)"
