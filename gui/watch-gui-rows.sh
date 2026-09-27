#!/usr/bin/env bash
# Watchdog for the Settings → Voice rows that this patch adds.
#
# Why it exists: `hermes update` replaces the checkout, which removes the patch, the schema seed and the
# built rows. This script notices and repairs what it can, so the rows stop being something you have to
# remember.
#
# Contract with the cron job that runs it: stdout is delivered verbatim, and EMPTY stdout sends nothing.
# So silence means "everything is in place" — it speaks only when the state changes and something needs
# a human. It never repacks on its own unless you drop an AUTOPACK file next to it (a repack takes
# minutes and bounces the running app).
set -uo pipefail

REPO="${HERMES_REPO:-$HOME/.hermes/hermes-agent}"
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PATCH="$DIR/gui-rows.patch"
STATE_FILE="$DIR/.watch-state"
APP_DIST="$REPO/apps/desktop/release/mac-arm64/Hermes.app/Contents/Resources/app.asar.unpacked/dist"
MARKER="voice.mic_device_id"

git -C "$REPO" rev-parse --git-dir >/dev/null 2>&1 || { echo "watch-gui-rows: not a Hermes checkout at $REPO"; exit 0; }
[ -f "$PATCH" ] || { echo "watch-gui-rows: patch missing at $PATCH"; exit 0; }

head="$(git -C "$REPO" rev-parse --short HEAD)"
applied=0
git -C "$REPO" apply --check --reverse "$PATCH" >/dev/null 2>&1 && applied=1
seeded=0
grep -q '"mic_device_id"' "$REPO/hermes_cli/config_defaults.py" 2>/dev/null && seeded=1
built=0
grep -rqs "$MARKER" "$APP_DIST"/assets/*.js 2>/dev/null && built=1

state="" message=""

if [ "$applied" = 1 ] && [ "$seeded" = 1 ] && [ "$built" = 1 ]; then
  state="ok@$head"                       # nothing to say
elif [ "$applied" = 0 ]; then
  if git -C "$REPO" apply --check "$PATCH" >/dev/null 2>&1; then
    git -C "$REPO" apply "$PATCH" && applied=1
    state="reapplied@$head"
    message="An update removed the Settings → Voice rows; I re-applied the patch and the schema seed to $head.

They show up after a repack (one command, a few minutes, reload the app afterwards):
  $DIR/apply-gui-rows.sh"
    if [ -f "$DIR/AUTOPACK" ]; then
      message="$message

AUTOPACK is set, so I am rebuilding the app now."
      ( cd "$REPO/apps/desktop" && npm run pack >/dev/null 2>&1 ) && message="$message
Rebuild finished — reload the app (⌘R)."
    fi
  elif [ -f "$REPO/apps/desktop/src/lib/voice-devices.ts" ]; then
    # The new files exist but the patch neither applies nor reverses: a half-applied tree (an update
    # interrupted mid-restore, or a hand-edit). Say that, rather than blaming a version move.
    state="partial@$head"
    message="The Settings → Voice patch is only partially present in $head — the new files exist but the patch neither applies nor reverses cleanly, so the rows may be inconsistent. Ask Neko-chan to restore or re-cut gui-rows.patch."
  else
    state="stale@$head"
    message="Hermes moved past the version this patch targets (checkout $head), so it cannot re-apply itself any more. The Settings → Voice rows are gone until it is re-cut — ask Neko-chan to re-cut gui-rows.patch for $head."
  fi
elif [ "$seeded" = 0 ]; then
  state="unseeded@$head"
  message="The patch is applied but the two voice device keys are missing from hermes_cli/config_defaults.py, so the Microphone/Speaker rows cannot render. Re-run:
  $DIR/apply-gui-rows.sh"
elif [ "$built" = 0 ]; then
  state="needs-repack@$head"
  message="The Settings → Voice rows are in the source but not in the built app, so the running app does not show them. One repack fixes it:
  $DIR/apply-gui-rows.sh"
fi

# Speak once per state change, not every tick.
if [ "$state" != "$(cat "$STATE_FILE" 2>/dev/null)" ]; then
  printf '%s\n' "$state" > "$STATE_FILE"
  [ -n "$message" ] && printf '%s\n' "$message"
fi
exit 0
