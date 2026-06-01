# Settings-path preflight

All three skills (`/ingest` Phase 2 onward, `/prep-session`, `/wrap-session`) run the same preflight check at the very start of every invocation: confirm the absolute paths baked into `.claude/settings.json` still match the current campaign root. If the campaign was moved on disk after `/ingest` Phase 1 scaffolded it, the baked permission rules no longer apply to the current directory and every routine Edit/Write the skill performs will hit a permission prompt. This reference is the canonical spec for that check; each SKILL.md just points here.

The check is the runtime half of the same concern the `_comment_path` / `_comment_recovery` fields in `templates/.claude/settings.json.template` cover at rest (issue #12). Those comments tell a GM reading the file by hand that paths are baked; this preflight tells the agent (and the GM) automatically, the moment a skill runs from a moved campaign root.

## When this runs

**Before any other work in the skill.** Specifically, before:

- reading campaign state (`campaign.md`, `adventures/`, `sessions/`, etc.),
- writing any file (including staging files under `.ttrpg-staging/`),
- running any other Step 0 / pre-flight check the skill has (campaign-repo marker check, session-target resolution, etc.).

If the skill resolves a campaign root before doing anything else (the "Locate the campaign repo" step in `/prep-session` and `/wrap-session`, or Phase 3 Step 0's input-validation in `/ingest`), run **that** resolution first, then run this preflight against the resolved campaign root. The preflight needs to know which directory to compare against; it cannot run earlier than campaign-root resolution.

Run the preflight **once per skill invocation**. Cache the result for the rest of the run — even if the GM declines regeneration, do not re-prompt later in the same session.

## What this reads

`.claude/settings.json` at the **campaign root** (the directory resolved by the skill's "Locate the campaign repo" / "Validate the target" step). Not at cwd unless cwd is itself the campaign root.

If `.claude/settings.json` does not exist, the preflight is a no-op — the campaign was scaffolded with an older plugin version, or the file was deleted intentionally, or this is the rare hand-built campaign repo. Do not warn, do not propose creating the file. Proceed silently.

If `.claude/settings.json` exists but does not parse as JSON, surface the parse error to the GM verbatim and stop the skill — a corrupted settings file is a bigger problem than a path mismatch and the GM needs to know.

## What this compares

The preflight compares the campaign-root baked path against its current resolved value.

### Campaign-root check

From `permissions.allow`, find the first entry of the form `Edit(/<absolute_path>/...)`. Extract the absolute prefix — everything between the leading `Edit(/` and the next path segment that contains a glob (`**`, `*`, `?`) or the closing `)`. Concretely, for the template-generated entry `Edit(/Users/sofia/campaigns/my-game/npcs/**)`, the extracted prefix is `/Users/sofia/campaigns/my-game`.

Compare that prefix against the resolved campaign root. To avoid false positives:

- **Canonicalize both paths** before comparing. Resolve symlinks (`readlink -f` semantics, or the language equivalent) and normalize away trailing slashes. Two paths that differ only because one goes through a symlink and the other through the realpath must compare equal.
- **Compare as strings after canonicalization.** Case-sensitive on Linux; case-insensitive comparison is not required — macOS's HFS+/APFS default-case-insensitive behavior is consistent on both sides, since both paths come from the same OS.

### Combined behavior

If the baked campaign-root prefix matches the current resolved value, proceed silently. The skill continues with no further preflight output.

If the campaign-root check is missing the rule it inspects (no `Edit(/...)` entry exists in `permissions.allow`), treat the missing check the same as the file-missing case: no-op, proceed silently. The GM has hand-edited away the baked paths and the preflight has nothing to check against.

The plugin-install Read rule no longer carries a baked-in absolute home path — issue #69 replaced the `Read({{HOME}}/.claude/skills/ttrpg-gm/**)` form with `Read(${CLAUDE_PLUGIN_ROOT}/**)`, which Claude Code resolves at match time without a substitution. There is no home-path check to run anymore.

## What this does on mismatch

If the campaign-root check fails, surface the discrepancy to the GM with this exact prompt format:

> Your `.claude/settings.json` has baked-in paths pointing at `<old prefix>`, but this campaign lives at `<current campaign root>`. The campaign was likely moved. Regenerate the file from the current path? (Y/n)

Use the canonicalized form of every path in the prompt — the GM should see what's actually compared, not the raw uncanonicalized strings.

Then wait for the GM's response. Do not start the skill's other Step 0 / Step 1 work in parallel; the GM may want to cancel after seeing the mismatch.

### On Y (or empty / no response that disagrees)

Regenerate `.claude/settings.json` at the campaign root by re-running the same path-substitution `/ingest` Phase 1 Step 2 runs:

1. Read `../templates/.claude/settings.json.template` from the plugin install (relative to this reference's location at `references/preflight.md`).
2. Substitute `{{CAMPAIGN_PATH}}` with the canonicalized campaign root (without trailing slash, as the template expects).
3. Write the result to `.claude/settings.json` at the campaign root, **scoped to the regeneration boundary** below.

**Safe regeneration scope.** The preflight rewrites only the keys the template controls:

- `permissions.allow`
- `permissions.deny` (if present in the template; currently the template has no `deny` block, but if a future template adds one, the preflight rewrites it the same way)
- `_comment_path` (the `{{CAMPAIGN_PATH}}`-interpolated description from issue #12)
- `_comment_recovery` (the recovery hint from issue #12)

Any other top-level key the GM has hand-added to `.claude/settings.json` — e.g., `env`, `hooks`, custom `_comment_*` keys the GM authored, a `model` override — is **preserved verbatim**. Concretely: read the existing `.claude/settings.json` into memory, render the template into memory, then merge by overwriting only the keys in the regeneration scope. Do not naively replace the whole file with the template render.

If `permissions` exists in the GM's file with extra keys beyond `allow` / `deny` (e.g., a custom `defaultMode`), preserve those extra keys under `permissions` and rewrite only `allow` / `deny`.

After the write, tell the GM concisely what changed: *"Regenerated `.claude/settings.json` with paths rooted at `<current campaign root>`. Hand-added keys preserved."* Then continue with the skill's other Step 0 / Step 1 work.

### On N (or any explicit decline)

Proceed with the skill's other work using the stale settings file. Do not regenerate, do not modify any file, do not warn again in the same session. Every subsequent Edit/Write the skill performs will still produce a permission prompt — the GM has chosen to live with that for this run.

Record the decline in skill-run state so the preflight does not re-prompt on later steps of the same invocation. The decline does **not** persist across separate skill invocations — the next `/prep-session` or `/wrap-session` from the same moved campaign will re-prompt.

## Idempotence properties the preflight guarantees

The preflight is designed so the same campaign at the same path on different runs produces no warning and no file modification. Specifically:

- **Same path, freshly scaffolded campaign:** the extracted prefix matches the campaign root exactly; preflight is silent.
- **Same path, accessed through a symlink:** canonicalization resolves both sides to the same realpath; preflight is silent. This is the false-positive case the canonicalization rule exists to prevent — a GM whose campaign lives at `/Volumes/data/campaigns/sunless` and is accessed through `~/campaigns/sunless` (a symlink) must not see a warning.
- **Same path, trailing slash on one side:** normalization strips trailing slashes before comparison; preflight is silent.
- **Different path (campaign moved):** preflight prompts once, GM accepts → `.claude/settings.json` rewritten with the new path; subsequent invocations from the same new path are silent.
- **Different path (campaign moved), GM declined:** preflight prompts once per invocation; declining suppresses re-prompts for the rest of that run only.

## What this does NOT do

- **Does not touch git.** No staging, no committing, no `git status`. If the GM accepts regeneration, `.claude/settings.json` ends up modified in the working tree; the GM commits it (or not) on their own schedule, the same way they commit any other file the skills write.
- **Does not modify any file other than `.claude/settings.json`.** Not `CLAUDE.md`, not `.gitignore`, not any of the rules files under `.claude/rules/`. If those have drifted from the templates, that's a separate concern outside this preflight's scope.
- **Does not regenerate the file structurally beyond the path substitution.** If the plugin's `templates/.claude/settings.json.template` has gained new permission entries since the GM's campaign was scaffolded, those new entries land in the regenerated file as a side effect — but the preflight does not advertise that as its purpose, and the GM should not rely on the preflight as a template-upgrade mechanism. A future "upgrade the campaign scaffold" workflow may handle that intentionally; this isn't it.
- **Does not prompt for anything other than the regenerate-yes-no question.** No follow-up questions about which paths to update, no per-entry confirmation, no "should I also update X?". The GM's choice is binary: regenerate the whole settings file (with safe scope) or proceed with the stale one.
- **Does not run on every step of the skill.** Once per invocation. The skills cache the decision (proceed silently, regenerated-then-proceed, or declined-and-proceed) for the rest of the run.

## What the skills should do with this

Each SKILL.md has a pointer at the top: *"Before any other work, follow the procedure in `preflight.md`. If the GM declines regeneration, continue with the current settings — do not warn again this run."* The pointer is the only thing the skill says about the preflight; the procedure stays here.

If a skill needs to know whether regeneration happened (it currently doesn't — the regenerated file is just used implicitly by Claude Code's permission matcher on subsequent Edit/Write calls), it can read `.claude/settings.json` itself; the preflight does not return structured state to the skill.
