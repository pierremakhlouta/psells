#!/bin/bash
#
# Reminds Pierre, through the morning backup, that the AWS demonstration is
# ending. AWS's free plan closes the account about 27 March 2027; from 1 March
# until then each morning shows a notification and prints a line for the
# backup's log, so the shutdown in RUNBOOK.md ("End the demonstration") is
# done before anything starts failing. Outside those dates it does nothing.
#
# PSELLS_TODAY (YYYY-MM-DD) stands in for today's date in the tests.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FROM=2027-03-01
ENDS=2027-03-27

today="${PSELLS_TODAY:-$(date +%F)}"

if [[ ! "$today" < "$FROM" && ! "$today" > "$ENDS" ]]; then
    message="AWS's free plan closes about $ENDS. Follow RUNBOOK.md, End the demonstration."
    "$SCRIPT_DIR/notify.sh" "PSells demo ends soon" "$message" || true
    echo "$message"
fi
