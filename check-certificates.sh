#!/bin/bash
#
# Warns, a month ahead, before one of PSells' certificates on the Mac expires.
#
# Run by backup.sh every morning, after the backup; also safe to run by hand:
#
#     ./check-certificates.sh
#
# Nothing else would say: the browser would one day simply refuse
# https://psells.localhost. Three certificates are checked, each where it
# lives: the one nginx serves (data/tls/, 397 days), the cluster's
# (~/PSells-Kind/tls/, the same), and the certificate authority that signs
# both (~/PSells-CA/, five years). One that is missing is skipped, since the
# cluster's, for one, is optional. Each within 30 days of its end gets a line
# and a notification, every day until it is renewed, naming the command that
# renews it; one already expired says so.
#
# The CA is warned about earlier, 30 days before it has 397 days left:
# make-certificate.sh refuses, from then on, to sign a certificate that would
# outlive it, so the next renewal of either certificate would fail.
#
# It prints one line per certificate checked and exits 0 whatever it finds:
# a warning, not a failure of the backup that runs it.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CA_DIR="${PSELLS_CA_DIR:-$HOME/PSells-CA}"
KIND_TLS_DIR="${PSELLS_KIND_TLS_DIR:-$HOME/PSells-Kind/tls}"
DAY=$((24 * 60 * 60))
# make-certificate.sh's CERT_DAYS.
CERT_DAYS=397

# OpenSSL, as make-certificate.sh requires, not the LibreSSL macOS ships in
# /usr/bin, which launchd's PATH finds first. The openssl on PATH is kept when
# it is OpenSSL, so a test's stand-in, found first, is the one used.
case "$(openssl version 2> /dev/null)" in
    "OpenSSL "*) ;;
    *) PATH="/opt/homebrew/opt/openssl@3/bin:/usr/local/opt/openssl@3/bin:$PATH" ;;
esac
export PATH

# The sentence -checkend prints, not its exit status, as in
# make-certificate.sh: OpenSSL 3.6.0 exited 0 on "Certificate will expire".
expires_within() {
    openssl x509 -in "$1" -noout -checkend "$2" 2> /dev/null || true
}

check() {
    local label=$1 file=$2 warn_days=$3 renew=$4 ends
    [ -f "$file" ] || return 0
    ends=$(openssl x509 -in "$file" -noout -enddate 2> /dev/null | sed 's/^notAfter=//')
    case "$(expires_within "$file" 0) | $(expires_within "$file" $((warn_days * DAY)))" in
        "Certificate will expire | "*)
            echo "$label: EXPIRED $ends"
            "$SCRIPT_DIR/notify.sh" "PSells certificate expired" "$label expired $ends. Renew: $renew" || true ;;
        "Certificate will not expire | Certificate will expire")
            echo "$label: expires within $warn_days days, $ends"
            "$SCRIPT_DIR/notify.sh" "PSells certificate expires soon" "$label expires $ends. Renew: $renew" || true ;;
        "Certificate will not expire | Certificate will not expire")
            echo "$label: ok until $ends" ;;
        *)
            echo "$label: unreadable"
            "$SCRIPT_DIR/notify.sh" "PSells certificate unreadable" "$label: $file" || true ;;
    esac
}

check "The Mac's certificate" "$SCRIPT_DIR/data/tls/psells.localhost.crt" 30 \
    "./make-certificate.sh, then docker compose restart proxy"
check "The cluster's certificate" "$KIND_TLS_DIR/psells.localhost.crt" 30 \
    "PSELLS_TLS_DIR=~/PSells-Kind/tls ./make-certificate.sh, then k8s/up.sh"
check "The certificate authority" "$CA_DIR/ca.crt" $((CERT_DAYS + 30)) \
    "a new CA, trusted again on the Mac, then both certificates (RUNBOOK.md)"
exit 0
