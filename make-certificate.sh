#!/bin/bash
#
# Makes the certificate nginx serves PSells with, at https://psells.localhost.
#
# Two things, the first only once:
#
#   1. A certificate authority (CA) of PSells' own, in ~/PSells-CA. Its
#      certificate is what the Mac is told to trust, by hand, once. It can
#      sign for psells.localhost and nothing else: its name constraint permits
#      that one name and excludes every IP address, so if its key ever leaked
#      it could not be used to impersonate any other site. It lasts five years.
#
#   2. A certificate for psells.localhost, signed by that CA, with its key, in
#      data/tls/ beside this script. nginx serves these two files. It lasts
#      397 days, inside the 398 days browsers allow a public certificate, and
#      running this script again signs a new one with the same CA, so renewing
#      needs no change to the keychain.
#
# Nothing here goes near the repository or an image: ~/PSells-CA is outside the
# project, and data/ is ignored by git and by the Docker build.
#
#     ./make-certificate.sh
#
# PSELLS_CA_DIR and PSELLS_TLS_DIR point it somewhere else, which is how the
# tests run it without touching either real folder.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

CA_DIR="${PSELLS_CA_DIR:-$HOME/PSells-CA}"
TLS_DIR="${PSELLS_TLS_DIR:-$SCRIPT_DIR/data/tls}"

NAME="psells.localhost"
CA_DAYS=1826
CERT_DAYS=397

CA_KEY="$CA_DIR/ca.key"
CA_CERT="$CA_DIR/ca.crt"
KEY="$TLS_DIR/$NAME.key"
CERT="$TLS_DIR/$NAME.crt"

fail() {
    printf 'make-certificate.sh: %s\n' "$1" >&2
    exit 1
}

command -v openssl > /dev/null || fail "openssl not found on PATH"

# Every file this script creates is readable by its owner only, keys above all.
umask 077

# Work happens in a folder of its own, and a certificate only takes its real
# name once it is complete, so a failure halfway never leaves a key without a
# certificate, or a certificate for the wrong key, where nginx would read it.
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# P-256 elliptic-curve keys: what browsers and Let's Encrypt use by default,
# smaller and faster than RSA at the same strength. Written by genpkey, which
# both OpenSSL and the LibreSSL that ships with macOS understand.
new_key() {
    openssl genpkey -algorithm EC -pkeyopt ec_paramgen_curve:P-256 -out "$1"
}

# The CA, once ------------------------------------------------------------------

if [ ! -f "$CA_KEY" ] || [ ! -f "$CA_CERT" ]; then
    if [ -e "$CA_KEY" ] || [ -e "$CA_CERT" ]; then
        fail "$CA_DIR holds half a CA; move it aside rather than overwrite it"
    fi

    mkdir -p "$CA_DIR"
    chmod 700 "$CA_DIR"

    # basicConstraints CA:TRUE with pathlen:0: it signs certificates, and none
    # of them may be a CA in turn. keyUsage: signing certificates and nothing
    # else. nameConstraints does the limiting. A constraint applies only to the
    # kinds of name it lists, so without the two excluded IP ranges this CA
    # could still sign for 127.0.0.1, or any address at all. Critical, so a
    # program that cannot enforce a constraint must refuse the certificate
    # rather than ignore the constraint.
    cat > "$WORK/ca.cnf" <<EOF
[req]
distinguished_name = dn
prompt = no
x509_extensions = ca

[dn]
O = PSells
CN = PSells local CA for $NAME only

[ca]
basicConstraints = critical, CA:TRUE, pathlen:0
keyUsage = critical, keyCertSign, cRLSign
nameConstraints = critical, permitted;DNS:$NAME, excluded;IP:0.0.0.0/0.0.0.0, excluded;IP:0:0:0:0:0:0:0:0/0:0:0:0:0:0:0:0
subjectKeyIdentifier = hash
EOF

    new_key "$WORK/ca.key"
    openssl req -new -x509 -config "$WORK/ca.cnf" -key "$WORK/ca.key" \
        -days "$CA_DAYS" -sha256 -out "$WORK/ca.crt"

    mv "$WORK/ca.key" "$CA_KEY"
    mv "$WORK/ca.crt" "$CA_CERT"
    NEW_CA=1
else
    NEW_CA=0
fi

# A certificate the CA outlives -------------------------------------------------

# A certificate is only as good as the CA that signed it. One that outlived its
# CA would stop working on the day the CA expired, earlier than its own date
# says, with an error that points at the wrong file.
#
# The sentence -checkend prints is read, not its exit status. OpenSSL 3.6.0
# prints "Certificate will expire" and still exits 0, so a check on the status
# passes every CA; the test for this failed on a Mac with that version.
CA_EXPIRY="$(openssl x509 -in "$CA_CERT" -noout -checkend $((CERT_DAYS * 86400)) 2> /dev/null || true)"
case "$CA_EXPIRY" in
    "Certificate will not expire") ;;
    "Certificate will expire")
        fail "the CA in $CA_DIR expires within $CERT_DAYS days; make a new one (move $CA_DIR aside and run this again), and trust the new ca.crt" ;;
    *)
        fail "could not read the CA certificate $CA_CERT" ;;
esac

# The certificate for psells.localhost ------------------------------------------

# CA:FALSE: it can never sign anything itself. digitalSignature and serverAuth:
# it proves a server's identity in a TLS handshake and is good for nothing
# else. subjectAltName is the name browsers check; the common name is ignored
# by them and kept only for people reading the certificate.
cat > "$WORK/cert.cnf" <<EOF
[cert]
basicConstraints = critical, CA:FALSE
keyUsage = critical, digitalSignature
extendedKeyUsage = serverAuth
subjectAltName = DNS:$NAME
subjectKeyIdentifier = hash
authorityKeyIdentifier = keyid
EOF

new_key "$WORK/cert.key"
openssl req -new -key "$WORK/cert.key" -subj "/CN=$NAME" -out "$WORK/cert.csr"

# A random 128-bit serial number. Two certificates from one CA must never share
# one, and a counter kept in a file is one more file to lose.
#
# openssl reports progress on the error stream even when it succeeds, so that
# stream is kept in a file and shown only if signing fails. Thrown away
# instead, a failure here would stop the script with no word of why.
if ! openssl x509 -req -in "$WORK/cert.csr" \
    -CA "$CA_CERT" -CAkey "$CA_KEY" -set_serial "0x$(openssl rand -hex 16)" \
    -days "$CERT_DAYS" -sha256 \
    -extfile "$WORK/cert.cnf" -extensions cert \
    -out "$WORK/cert.crt" 2> "$WORK/sign.log"; then
    fail "signing with $CA_DIR failed: $(cat "$WORK/sign.log")"
fi

# Checked before it replaces anything: signed by this CA, for this name, within
# the constraint.
openssl verify -CAfile "$CA_CERT" "$WORK/cert.crt" > /dev/null \
    || fail "the new certificate does not verify against $CA_CERT"

mkdir -p "$TLS_DIR"
chmod 700 "$TLS_DIR"
mv "$WORK/cert.key" "$KEY"
mv "$WORK/cert.crt" "$CERT"

# What happened ------------------------------------------------------------------

printf 'Certificate: %s\n' "$CERT"
printf 'Key:         %s\n' "$KEY"
openssl x509 -in "$CERT" -noout -enddate

if [ "$NEW_CA" = 1 ]; then
    cat <<EOF

A new CA was made in $CA_DIR. Trust it for this user once, by hand:

    security add-trusted-cert -r trustRoot -k ~/Library/Keychains/login.keychain-db "$CA_CERT"

macOS asks for your password. Firefox keeps its own list and is not covered.
EOF
fi
