#!/bin/bash
#
# Shows a macOS notification, for the Mac's background jobs to say they failed:
#
#     notify.sh "PSells backup failed" "the new dump does not restore"
#
# The Mac is not monitored, so a job that fails would otherwise be seen only
# in its log, when someone looked. backup.sh, start-stack.sh and
# refresh-analytics.sh call this when they fail. The text reaches AppleScript
# as arguments, never as part of the script, so nothing in a message can
# change what runs. A reason never carries a figure or a record.
#
# It never fails the job that calls it: without osascript, or if the
# notification cannot be shown, it says nothing and exits 0.

title=${1:-PSells}
message=${2:-}

command -v osascript > /dev/null || exit 0
osascript - "$title" "$message" > /dev/null 2>&1 <<'APPLESCRIPT' || true
on run argv
    display notification (item 2 of argv) with title (item 1 of argv) sound name "Basso"
end run
APPLESCRIPT
exit 0
