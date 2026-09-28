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
# Writes .env from Parameter Store, gets a certificate from Let's Encrypt if
# the server has none yet, builds and starts the stack with compose.aws.yaml
# laid over compose.yaml, loads sample_data/seed.sql into a database that has
# no products yet, and installs the timers that renew the certificate and back
# the database up to S3. Safe to run again: .env is rewritten, an existing
# certificate is kept, the stack is brought up to date, and a database with
# records in it is left alone.
#
# A new server runs it from first-boot.sh. PSELLS_ACME_STAGING=1 asks Let's
# Encrypt's staging service for the certificate instead, which no browser
# trusts and which has no weekly limit: for trying a rebuild.
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
if [ -z "$user" ] || [ -z "$password" ] || [ -z "$database" ]; then
    fail "expected user, password and db under $PARAMETERS"
fi

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

echo "== certificate"
# The one name the server answers to, read from the file nginx reads it from.
NAME=$(sed -n 's/^server_name \([^;]*\);$/\1/p' nginx/sites/aws/https.conf)
[ -n "$NAME" ] || fail "no server_name in nginx/sites/aws/https.conf"

# certbot and nginx both run as user 101, which owns these folders, so the
# key is readable by its owner only and its owner is nginx.
install -d -o 101 -g 101 -m 700 data/letsencrypt
install -d -o 101 -g 101 -m 755 data/acme

new_certificate=no
if [ -e "data/letsencrypt/live/$NAME/fullchain.pem" ]; then
    echo "kept the certificate for $NAME"
else
    # nginx cannot start without a certificate, so the first one is fetched
    # before the stack starts, by certbot answering Let's Encrypt on port 80
    # itself. Renewals go through nginx instead; see below.
    staging=()
    [ "${PSELLS_ACME_STAGING:-0}" = 1 ] && staging=(--staging)
    compose run --rm -p 80:80 certbot certonly --standalone "${staging[@]}" \
        --non-interactive --agree-tos --register-unsafely-without-email -d "$NAME"
    new_certificate=yes
fi

echo "== stack"
compose up -d --build --wait

if [ "$new_certificate" = yes ]; then
    # Now nginx holds port 80, renewals must come through its webroot. This
    # records that, after a trial renewal to prove it works.
    compose run --rm certbot reconfigure --non-interactive --cert-name "$NAME" \
        --webroot --webroot-path /var/www/acme
fi

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

echo "== timers: certificate renewal and the daily backup to S3"
install -m 644 deploy/aws/psells-certbot-renew.service deploy/aws/psells-certbot-renew.timer \
    deploy/aws/psells-backup.service deploy/aws/psells-backup.timer \
    /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now psells-certbot-renew.timer psells-backup.timer
systemctl list-timers psells-certbot-renew.timer psells-backup.timer --no-pager

echo "== deployed $(git log --oneline -1)"
