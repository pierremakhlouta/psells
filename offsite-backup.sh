#!/bin/bash
#
# Copies a proved backup off the Mac, encrypted, into iCloud Drive, and proves
# the copy decrypts back to the same bytes.
#
# Run by backup.sh after each dump has been restored and counted, with the
# names of the dump and the configuration copy it made in ~/PSells-Backups/daily:
#
#     offsite-backup.sh psells-STAMP.dump config-STAMP.json
#
# The real records otherwise never leave the Mac, and they leave here only
# encrypted. The two files are packed into one archive and encrypted with age
# to the public key in data/backup-recipient.txt, which can lock and not
# unlock. The private key that unlocks it is kept twice: in the Mac's
# Keychain, as psells-backup-key, so each copy is proved the morning it is
# made, and in a password manager, so a lost Mac loses nothing. iCloud only
# ever holds ciphertext, kept 30 days like the copies on the Mac.
#
# It prints one line on success, and on failure a reason on standard error;
# it never prints the key or any record.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_DIR="${PSELLS_BACKUP_DIR:-$HOME/PSells-Backups/daily}"
OFFSITE_DIR="${PSELLS_OFFSITE_DIR:-$HOME/Library/Mobile Documents/com~apple~CloudDocs/PSells-Backups}"
RECIPIENT="$SCRIPT_DIR/data/backup-recipient.txt"
KEYCHAIN_ITEM=psells-backup-key
KEEP_DAYS=30

# launchd's PATH lacks Homebrew, where age is. Appended, so a test's stand-in,
# found first, is the one used.
PATH="$PATH:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
export PATH

die() {
    echo "$1" >&2
    exit 1
}

[ $# -eq 2 ] || die "usage: offsite-backup.sh psells-STAMP.dump config-STAMP.json"
dump=$1
config=$2
for file in "$dump" "$config"; do
    [ -s "$BACKUP_DIR/$file" ] || die "no $file in $BACKUP_DIR"
done
command -v age > /dev/null || die "age is not installed: brew install age"
[ -s "$RECIPIENT" ] ||
    die "no data/backup-recipient.txt, so the off-Mac copy is not set up; see RUNBOOK.md"

mkdir -p "$OFFSITE_DIR"
name="${dump%.dump}.tar.age"
target="$OFFSITE_DIR/$name"
partial="$target.partial"
# Never leave a half-written copy looking like a backup.
trap 'rm -f "$partial"' EXIT

tar -cf - -C "$BACKUP_DIR" "$dump" "$config" | age -R "$RECIPIENT" > "$partial" ||
    die "could not encrypt the backup"

# Proved before it gets its real name: decrypted with the Keychain's key and
# each file compared with the one it came from. The key reaches age through a
# file descriptor, never a command line or a file on disk.
key=$(security find-generic-password -s "$KEYCHAIN_ITEM" -w 2> /dev/null) ||
    die "no private key in the Keychain under $KEYCHAIN_ITEM; see RUNBOOK.md"
for file in "$dump" "$config"; do
    decrypted=$(age -d -i <(printf '%s\n' "$key") "$partial" | tar -xOf - "$file" | shasum -a 256) ||
        die "the encrypted copy does not decrypt with the Keychain's key"
    original=$(shasum -a 256 < "$BACKUP_DIR/$file")
    [ "${decrypted%% *}" = "${original%% *}" ] ||
        die "the encrypted copy of $file does not match the original"
done
unset key

mv "$partial" "$target"
# Only this script's copies, by name, and only once they are a month old.
find "$OFFSITE_DIR" -name 'psells-*.tar.age' -mtime +"$KEEP_DAYS" -delete

echo "$name  $(wc -c < "$target" | tr -d ' ') bytes, decrypted and matched"
