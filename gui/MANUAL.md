# Reapplying the Settings → Voice rows, by hand

The rows this patch adds are **not** something the plugin can contribute — the app builds them from a
bundle-compiled `SECTIONS` list inside `apps/desktop`, so they need either this patch or upstream's own
work ([#117088](https://github.com/NousResearch/hermes-agent/pull/117088), the device pickers).

**Everything here is offline.** No agent, no tokens — the scripts and the patch are already on disk.

## Where things live

| Thing | Path |
|---|---|
| Active kit | `~/.hermes/patches/openrouter-voice-gui/active-<BASE>/` — `gui-rows.patch`, `apply-gui-rows.sh`, `watch-gui-rows.sh` |
| Current base | `d4d2ab7b5d` |
| Hermes checkout | `~/.hermes/hermes-agent`, branch **`gui-rows`** (commit `1919defd50`) holds the applied rows |
| The launchable app | `~/Applications/Hermes.app` |
| **The installer** | `/Applications/Hermes.app` — **never write here**, that path is `Hermes-Setup`, not the app |
| Plugin (installed) | `~/.hermes/plugins/openrouter-voice` |
| Plugin (dev clone) | `~/HERMES DEFAULT WORKSPACE/Repos/Home/openrouter-voice` |

## 1. The normal case, after `hermes update`

```bash
# a) apply (idempotent — it says "already applied" and stops if nothing to do)
~/.hermes/patches/openrouter-voice-gui/active-d4d2ab7b5d/apply-gui-rows.sh

# b) the applier repacks but does not move the build into your app home — do that yourself
rm -rf ~/Applications/Hermes.app
cp -R ~/.hermes/hermes-agent/apps/desktop/release/mac-arm64/Hermes.app ~/Applications/Hermes.app

# c) relaunch the app (not just ⌘R): the Microphone/Speaker rows come from the backend's
#    served schema, which the Python process read at boot.
```

`apply-gui-rows.sh --no-pack` applies without the several-minute repack.

If it prints **"does not apply … it needs re-cutting"**, the base has moved. Go to step 3.

## 2. If you keep the checkout on the `gui-rows` branch

The rows are a commit there (`1919defd50`), so nothing is silently stashed and no file is lost:

```bash
git -C ~/.hermes/hermes-agent checkout gui-rows     # your working tree already has them applied
git -C ~/.hermes/hermes-agent log --oneline -1      # confirm you are on it
```

`hermes update` checks out `main`, so afterwards either `git checkout gui-rows` again, or stay on `main`
and use step 1.

## 3. Re-cutting when the base has moved

Only the files upstream edits cause this. Find out which:

```bash
R=~/.hermes/hermes-agent
K=~/.hermes/patches/openrouter-voice-gui/active-d4d2ab7b5d     # the kit you are re-cutting FROM
git -C "$R" apply --check "$K/gui-rows.patch" 2>&1 | grep "does not apply"
```

For each blocking file, port it with a **three-way merge** — old base + patch vs today's upstream:

```bash
S=~/.hermes/cache/scratch/recut; REL=apps/desktop/src/app/settings/constants.ts   # ← the blocking file
BASE=d4d2ab7b5d; NEWBASE=$(git -C "$R" rev-parse --short HEAD)
mkdir -p "$S"/{old,plus,merged}/$(dirname "$REL")

git -C "$R" show "$BASE:$REL"      > "$S/old/$REL"
cp "$S/old/$REL"                     "$S/plus/$REL"
( cd "$S/plus" && git apply --include="*/$(basename "$REL")" "$K/gui-rows.patch" )   # guaranteed clean
git -C "$R" show HEAD:"$REL"       > "$S/merged/$REL"

git merge-file -p "$S/merged/$REL" "$S/old/$REL" "$S/plus/$REL" > "$S/merged/$REL.new"
grep -c '^<<<<<<<' "$S/merged/$REL.new"        # 0 = clean; otherwise resolve: keep BOTH sides
cp "$S/merged/$REL.new" "$R/$REL"
```

Resolving a conflict: these are adjacent insertions, so **keep both** — upstream's new line and the
patch's new rows. (In `constants.ts`: upstream's `stt.xai.model` / `stt.streaming` beside the patch's
`stt.openrouter.model`, `tts.openrouter.*`.)

Then apply the rest, regenerate the patch, and refresh the kit:

```bash
FILES=$(git -C "$R" apply --numstat "$K/gui-rows.patch" | awk '{print $3}')
BLOCKED='apps/desktop/src/app/settings/constants.ts apps/desktop/src/app/settings/config-field.tsx'
git -C "$R" apply $(for f in $BLOCKED; do printf -- "--exclude=%s " "$f"; done) "$K/gui-rows.patch"

for f in $FILES; do git -C "$R" add -N "$f"; done          # so new files appear in the diff
git -C "$R" diff HEAD -- $FILES > /tmp/gui-rows-new.patch
git -C "$R" reset -q -- $FILES

git -C "$R" apply --check --reverse /tmp/gui-rows-new.patch && echo "OK: reverses cleanly"   # must pass

N=~/.hermes/patches/openrouter-voice-gui/active-$NEWBASE; mkdir -p "$N"
cp /tmp/gui-rows-new.patch "$N/gui-rows.patch"
sed "s/-45871e100f/-$NEWBASE/; s/-d4d2ab7b5d/-$NEWBASE/" "$K/apply-gui-rows.sh" > "$N/apply-gui-rows.sh"
cp "$K/watch-gui-rows.sh" "$N/"; chmod +x "$N"/*.sh
```

The totals should stay **1722 insertions / 12 deletions**. If they moved by more than a line or two,
a hunk was dropped — re-check before trusting it.

Keep the old kit as history (`retired-<oldbase>/`) rather than overwriting it.

## 4. Verifying a re-cut (cheap, in this order)

```bash
R=~/.hermes/hermes-agent; PLUG=~/.hermes/plugins/openrouter-voice

# types — NOTE the heap flag: without it tsc dies as "Abort trap: 6" with zero TS errors
cd "$R/apps/desktop" && NODE_OPTIONS=--max-old-space-size=8192 npx tsc --noEmit; echo "tsc=$?"

# the patch's own surfaces
npx vitest run src/app/settings/voice-device-picker.test.tsx src/app/settings/voice-preview-button.test.tsx \
  src/app/settings/voice-volume-slider.test.tsx src/app/settings/config-field.preview-wiring.test.tsx \
  src/lib/voice-devices.test.ts src/lib/voice-volume.test.ts        # expect 6 files / 34 tests

# the plugin itself
"$R/venv/bin/python" -m pytest "$PLUG/tests" -q                      # expect 33 passed, 1 skipped

# is the row actually in the built app? (3 files = built in)
grep -rl voice.mic_device_id ~/Applications/Hermes.app/Contents/Resources/app.asar.unpacked/dist/assets/*.js | wc -l
```

## Pitfalls that cost time

- **`npx tsc --noEmit` OOMs now.** Default heap (~2 GB) is too small for this app; the failure looks
  like a crash, not a type error (`FATAL ERROR: Reached heap limit`, `Abort trap: 6`). Use
  `NODE_OPTIONS=--max-old-space-size=8192`, which exits 0.
- **`hermes update` rebuilds the desktop from a clean tree** (`install-stamp.json` → `"dirty": false`)
  and checks out `main`, so the rows vanish twice over. Re-apply (step 1).
- **The watchdog's cron job is gone** (`~/.hermes/cron/jobs.json` → `{"jobs": []}`), so nothing
  re-applies or tells you about it. Either re-create it or re-run step 1 after updates.
- **Never write into `/Applications/Hermes.app`** — that is the installer; overwriting it replaces the
  installer with a stale build.
- **Reload (⌘R) is not enough** for the two device rows: they come from the served schema, which is
  read when the backend boots. Restart the app.
- **Committing in this repo needs `ruff` on PATH** (lefthook pre-commit). Without it the commit aborts
  with `exit status 127`: `export PATH=~/.hermes/hermes-agent/venv/bin:$PATH`.
- **Keep the copies honest.** The patch carries its own OpenRouter STT/TTS catalogs (in
  `constants.ts`); the plugin's `models.py` is the one to re-probe (`python models.py --live`). If you
  refresh the catalogs, update both.