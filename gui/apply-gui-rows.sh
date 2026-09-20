#!/usr/bin/env bash
# Add the Settings → Voice device pickers, the OpenRouter model/voice/speed rows and their Preview
# buttons to a Hermes Desktop checkout.
#
# Why this is a patch and not part of the plugin: the desktop builds those rows from a bundle-compiled
# `SECTIONS` list ("the curated voice keys are the single source of which per-provider fields exist"),
# so neither a plugin nor a config entry can create one. The provider NAME appears in the dropdown from
# config alone; the rows need this edit plus a repack.
#
# Two things this script cannot do for you:
#   * `hermes update` checks out main and rebuilds the desktop, which removes the rows again — re-run
#     this after an update.
#   * the patch is cut against a specific commit, and upstream edits the same files most releases. When
#     the base has moved the apply fails loudly (below) rather than half-applying; ask for a refreshed
#     patch rather than patching by hand.
#
# Usage:
#   ./apply-gui-rows.sh                 # apply + repack
#   ./apply-gui-rows.sh --no-pack       # apply only
#   HERMES_REPO=/path/to/checkout ./apply-gui-rows.sh
set -euo pipefail

HERMES_REPO="${HERMES_REPO:-$HOME/.hermes/hermes-agent}"
PATCH_DIR="$(cd "$(dirname "$0")" && pwd)"
PATCH="$PATCH_DIR/gui-rows.patch"
# The commit this patch was generated against. Used only to explain a failure.
BASE="${GUI_PATCH_BASE:-93940214ea}"
PACK=1
[ "${1:-}" = "--no-pack" ] && PACK=0

# rev-parse rather than a .git directory test: a linked worktree has .git as a file.
git -C "$HERMES_REPO" rev-parse --git-dir >/dev/null 2>&1 || {
  echo "not a Hermes checkout: $HERMES_REPO" >&2; exit 2; }
[ -f "$HERMES_REPO/apps/desktop/src/app/settings/constants.ts" ] || {
  echo "missing apps/desktop/src/app/settings/constants.ts under $HERMES_REPO" >&2; exit 2; }
[ -f "$PATCH" ] || { echo "missing $PATCH" >&2; exit 2; }

# "Already applied" is decided by the patch reversing cleanly — a sentinel string in one file can lie
# once upstream ships the same key for its own reasons.
if git -C "$HERMES_REPO" apply --check --reverse "$PATCH" 2>/dev/null; then
  echo "already applied — the Voice tab shows the device pickers, the OpenRouter rows and their Preview"
  echo "buttons once the app is repacked and the backend restarted"
elif git -C "$HERMES_REPO" apply --check "$PATCH" 2>/dev/null; then
  git -C "$HERMES_REPO" apply "$PATCH"
  echo "applied"
else
  HEAD_SHA="$(git -C "$HERMES_REPO" rev-parse --short HEAD)"
  {
    echo "gui-rows.patch does not apply to $HERMES_REPO (at $HEAD_SHA)."
    echo "  The patch is cut against $BASE; upstream edits the same files most releases, so a moved base"
    echo "  means it needs re-cutting — ask for a refreshed gui-rows.patch instead of applying by hand."
  } >&2
  exit 1
fi

if [ "$PACK" = "1" ]; then
  echo "repacking the desktop (several minutes; reload the app afterwards with ⌘R) ..."
  ( cd "$HERMES_REPO/apps/desktop" && npm run pack )
  echo "done — reload the app (⌘R) to pick up the new bundle"
  echo "     If the microphone/speaker rows are missing, restart the app rather than reloading: the rows"
  echo "     are bundled, but the two voice.*_device_id keys come from the backend's served schema, which"
  echo "     the running Python process read at boot (hermes_cli/config_defaults.py)."
fi