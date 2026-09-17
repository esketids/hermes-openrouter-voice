#!/usr/bin/env bash
# Add the Settings → Voice "OpenRouter Model" row.
#
# Why this is a patch and not part of the plugin: the desktop builds those rows from a
# bundle-compiled `SECTIONS` list ("the curated voice keys are the single source of which
# per-provider fields exist"), so neither a plugin nor a config entry can create one. The provider
# NAME appears in the dropdown from config alone; the model ROW needs this edit plus a repack.
#
# `hermes update` checks out main and rebuilds the desktop, which removes it again — re-run this
# after an update if you want the row back.
#
# Usage:
#   ./gui/apply-gui-rows.sh                 # apply + repack
#   ./gui/apply-gui-rows.sh --no-pack       # apply only
#   HERMES_REPO=/path/to/checkout ./gui/apply-gui-rows.sh
set -euo pipefail

HERMES_REPO="${HERMES_REPO:-$HOME/.hermes/hermes-agent}"
PATCH_DIR="$(cd "$(dirname "$0")" && pwd)"
CONSTANTS="$HERMES_REPO/apps/desktop/src/app/settings/constants.ts"
PACK=1
[ "${1:-}" = "--no-pack" ] && PACK=0

[ -d "$HERMES_REPO/.git" ] || { echo "not a Hermes checkout: $HERMES_REPO" >&2; exit 2; }
[ -f "$CONSTANTS" ] || { echo "missing $CONSTANTS" >&2; exit 2; }

if grep -q "'stt.openrouter.model'" "$CONSTANTS"; then
  echo "already applied — the Voice tab will show the OpenRouter Model row after a repack"
else
  echo "applying gui-rows.patch to $HERMES_REPO ..."
  if ! git -C "$HERMES_REPO" apply "$PATCH_DIR/gui-rows.patch"; then
    echo "patch did not apply cleanly — upstream changed constants.ts; rebase gui-rows.patch" >&2
    exit 1
  fi
  echo "applied"
fi

if [ "$PACK" = "1" ]; then
  echo "repacking the desktop (several minutes; reload the app afterwards with ⌘R) ..."
  ( cd "$HERMES_REPO/apps/desktop" && npm run pack )
  echo "done — reload the app (⌘R) to pick up the new bundle"
fi
