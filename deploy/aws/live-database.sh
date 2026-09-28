# shellcheck shell=bash
#
# How deploy.sh and backup-to-s3.sh reach whichever database the demo is
# using: the database container, or RDS while infra/aws's managed_services
# switch is on. Sourced, never run. The caller defines compose() and sets
# POSTGRES_USER, POSTGRES_PASSWORD and POSTGRES_DB, and POSTGRES_HOST when the
# database is RDS, as .env does.

# live TOOL ARGS...: runs psql or pg_dump, with ARGS, against the live
# database, reading standard input as the tool would.
#
# The database container: inside it, as before.
#
# RDS: in a throwaway container of the same pinned PostgreSQL image, since the
# server has no client of its own. TLS with RDS's certificate checked against
# AWS's authorities for the region (verify-full), which deploy.sh fetches, so
# it cannot be talking to anything else. The password travels in the
# environment (-e PGPASSWORD takes it from this shell's), never as an argument
# another process could read.
live() {
    local tool=$1
    shift
    if [ -z "${POSTGRES_HOST:-}" ]; then
        compose exec -T db "$tool" -U "$POSTGRES_USER" -d "$POSTGRES_DB" "$@"
    else
        local image
        image=$(compose config --images | grep '^postgres:')
        PGPASSWORD="$POSTGRES_PASSWORD" docker run --rm -i -e PGPASSWORD \
            -v "$PWD/data/rds-ca.pem:/rds-ca.pem:ro" "$image" "$tool" \
            -d "host=$POSTGRES_HOST port=5432 dbname=$POSTGRES_DB user=$POSTGRES_USER sslmode=verify-full sslrootcert=/rds-ca.pem" \
            "$@"
    fi
}
