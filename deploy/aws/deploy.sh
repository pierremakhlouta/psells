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
# Finds the image CI published for the checked-out commit, writes .env from
# Parameter Store with that image's digest, gets a certificate from Let's
# Encrypt if the server has none yet, starts the stack with compose.aws.yaml
# laid over compose.yaml, loads sample_data/seed.sql into a database that has
# no products yet, and installs the timers that renew the certificate and back
# the database up to S3. Safe to run again: .env is rewritten, an existing
# certificate is kept, the stack is brought up to date, and a database with
# records in it is left alone.
#
# PSELLS_IMAGE_DIGEST, when set, must be the digest CI published for the
# checked-out commit, or nothing is deployed: the Deploy workflow sends both,
# and a commit is never run with another commit's image.
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

echo "== image"
# CI publishes every commit on main under its own tag, for amd64 and arm64.
# The tag is resolved once to the digest of what was scanned, and the stack
# runs that digest, which cannot change afterwards.
REGISTRY_IMAGE=ghcr.io/pierremakhlouta/psells
commit=$(git rev-parse HEAD)
published=$(docker buildx imagetools inspect "$REGISTRY_IMAGE:$commit" --format '{{.Manifest.Digest}}') ||
    fail "no image is published for $commit; CI publishes one after a push to main passes"
[[ "$published" =~ ^sha256:[0-9a-f]{64}$ ]] || fail "unexpected digest for $commit: $published"
if [ -n "${PSELLS_IMAGE_DIGEST:-}" ] && [ "$PSELLS_IMAGE_DIGEST" != "$published" ]; then
    fail "asked to deploy $PSELLS_IMAGE_DIGEST, but $commit's image is $published"
fi
image="$REGISTRY_IMAGE@$published"
echo "$image"
# PSells' nginx image for the same commit, published beside the app's under
# nginx-<commit>, and run by its digest likewise.
nginx_published=$(docker buildx imagetools inspect "$REGISTRY_IMAGE:nginx-$commit" --format '{{.Manifest.Digest}}') ||
    fail "no nginx image is published for $commit"
[[ "$nginx_published" =~ ^sha256:[0-9a-f]{64}$ ]] || fail "unexpected nginx digest for $commit: $nginx_published"
nginx_image="$REGISTRY_IMAGE@$nginx_published"
echo "$nginx_image"

echo "== .env from Parameter Store ($PARAMETERS)"
# name<TAB>value, one per line. The password never reaches the terminal.
values=$(aws ssm get-parameters-by-path --region "$REGION" --path "$PARAMETERS" \
    --with-decryption --query 'Parameters[].[Name,Value]' --output text)

user="" password="" database="" host=""
while IFS=$'\t' read -r name value; do
    # Letters, digits, _ and - only, and dots in a host name, so nothing in a
    # value can break .env or the database address the app builds from it.
    case "$name" in
        "$PARAMETERS/host") [[ "$value" =~ ^[A-Za-z0-9.-]+$ ]] ;;
        *) [[ "$value" =~ ^[A-Za-z0-9_-]+$ ]] ;;
    esac || fail "$name holds characters .env cannot take"
    case "$name" in
        "$PARAMETERS/user") user="$value" ;;
        "$PARAMETERS/password") password="$value" ;;
        "$PARAMETERS/db") database="$value" ;;
        # Only while infra/aws's managed_services switch is on: RDS's address.
        "$PARAMETERS/host") host="$value" ;;
    esac
done <<< "$values"
if [ -z "$user" ] || [ -z "$password" ] || [ -z "$database" ]; then
    fail "expected user, password and db under $PARAMETERS"
fi

# AWS's certificate authorities for RDS in this region, which the app and
# live() check RDS's certificate against. Fetched on every deploy, whether or
# not RDS is on, so the file the app mounts always exists, and refused unless
# it is a certificate.
curl -fsS https://truststore.pki.rds.amazonaws.com/ca-central-1/ca-central-1-bundle.pem \
    -o data/rds-ca.pem.new
openssl x509 -noout -in data/rds-ca.pem.new || fail "the RDS certificate bundle is not a certificate"
mv data/rds-ca.pem.new data/rds-ca.pem
chmod 644 data/rds-ca.pem

# With RDS switched on, the app reaches it by its address, over TLS with its
# certificate verified; otherwise, the database container, as before.
rds_settings=""
if [ -n "$host" ]; then
    rds_settings="POSTGRES_HOST=$host
POSTGRES_URL_OPTIONS='?sslmode=verify-full&sslrootcert=/config/rds-ca.pem'"
    echo "the database is RDS, at $host"
else
    echo "the database is the container"
fi

echo "== monitoring settings from Parameter Store (/psells/grafana)"
# Where the agent sends metrics and logs, and its token. Each value is checked
# for the shape it must have, so nothing in one can break .env.
monitoring=$(aws ssm get-parameters-by-path --region "$REGION" --path /psells/grafana \
    --with-decryption --query 'Parameters[].[Name,Value]' --output text)

metrics_url="" metrics_user="" logs_url="" logs_user="" grafana_token=""
while IFS=$'\t' read -r name value; do
    case "$name" in
        /psells/grafana/metrics_url|/psells/grafana/logs_url)
            [[ "$value" =~ ^https://[A-Za-z0-9.-]+\.grafana\.net/[A-Za-z0-9/._-]+$ ]] ;;
        /psells/grafana/metrics_user|/psells/grafana/logs_user)
            [[ "$value" =~ ^[0-9]+$ ]] ;;
        /psells/grafana/token)
            [[ "$value" =~ ^glc_[A-Za-z0-9+/=_-]+$ ]] ;;
        *) true ;;
    esac || fail "$name does not look as it should"
    case "$name" in
        /psells/grafana/metrics_url) metrics_url="$value" ;;
        /psells/grafana/metrics_user) metrics_user="$value" ;;
        /psells/grafana/logs_url) logs_url="$value" ;;
        /psells/grafana/logs_user) logs_user="$value" ;;
        /psells/grafana/token) grafana_token="$value" ;;
    esac
done <<< "$monitoring"
if [ -z "$metrics_url" ] || [ -z "$metrics_user" ] || [ -z "$logs_url" ] ||
    [ -z "$logs_user" ] || [ -z "$grafana_token" ]; then
    fail "expected metrics_url, metrics_user, logs_url, logs_user and token under /psells/grafana"
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
PSELLS_IMAGE=$image
PSELLS_NGINX_IMAGE=$nginx_image
GRAFANA_METRICS_URL=$metrics_url
GRAFANA_METRICS_USER=$metrics_user
GRAFANA_LOGS_URL=$logs_url
GRAFANA_LOGS_USER=$logs_user
GRAFANA_TOKEN=$grafana_token
$rds_settings
EOF
mv .env.new .env
umask 022

# For live(), which reaches whichever database the app now uses.
POSTGRES_USER=$user POSTGRES_PASSWORD=$password POSTGRES_DB=$database POSTGRES_HOST=$host
# shellcheck source=deploy/aws/live-database.sh
. deploy/aws/live-database.sh

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
# Pulls the image if the server does not have it yet; builds nothing.
compose up -d --wait

# nginx reads its configuration from files mounted from this checkout, and
# Compose recreates a container only when its own definition changes, not
# when a mounted file does. So nginx is told to read them again: checked
# first, so a configuration it would refuse leaves the running one in place
# and stops the deploy, then reloaded, which finishes the requests in hand on
# the old configuration. Harmless when nothing changed.
compose exec -T proxy nginx -t || fail "nginx refuses the new configuration; the old one is still running"
compose exec -T proxy nginx -s reload

if [ "$new_certificate" = yes ]; then
    # Now nginx holds port 80, renewals must come through its webroot. This
    # records that, after a trial renewal to prove it works.
    compose run --rm certbot reconfigure --non-interactive --cert-name "$NAME" \
        --webroot --webroot-path /var/www/acme
fi

echo "== sample data"
# The database container builds its tables from schema.sql when its volume is
# first made. RDS starts empty, so a database without them gets schema.sql
# first, in one transaction that stops at the first error.
tables=$(live psql -tA -c "SELECT to_regclass('public.products') IS NOT NULL")
if [ "$tables" != t ]; then
    live psql -q -v ON_ERROR_STOP=1 --single-transaction < schema.sql
    echo "built the tables from schema.sql"
fi
products=$(live psql -tA -c "SELECT count(*) FROM products")
if [ "$products" = "0" ]; then
    live psql -q -v ON_ERROR_STOP=1 < sample_data/seed.sql
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
# What the application's container is really running, which the Deploy
# workflow compares with the digest it sent.
echo "running $(docker inspect -f '{{.Config.Image}}' "$(compose ps -q app)")"
