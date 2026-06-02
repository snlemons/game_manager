# Campaign scaffolder

The scaffolder is the deterministic procedure that turns an empty (or near-empty) target directory into a fresh ttrpg-gm campaign repo: it writes the plugin's seven template files into the target, runs `git init`, and makes a single initial commit. Per [ADR-0020](../docs/adr/0020-modularization-via-shared-references.md), the scaffolder is consumed by `/init-campaign`, `/init-adventure` (standalone mode), and `/ingest` (for the "scaffolded?" precondition check — read-only, slice G). This reference is the canonical spec; each consuming SKILL.md just points here.

The behavior is fully deterministic — no LLM judgement, no conversational refinement. The agent reads templates, substitutes three placeholders verbatim, writes seven files in a specific order, runs `git init`, and makes one commit. The reference-impl Python at `../tests/test_ingest_scaffolding.py` mirrors this spec for spec-drift detection.

## Inputs the caller provides

Every consumer that runs the scaffolder must supply:

- **Target directory** — where the campaign repo should live. May be an empty directory, a not-yet-existing directory, or (with explicit GM confirmation) a directory containing only source notes the consumer wants to ingest later. **Never** scaffold over a directory that already contains a campaign repo (presence of `campaign.md`, `.claude/rules/sessions.md`, `.claude/rules/adventures.md`, or a non-trivial `.git/`); abort and tell the GM.
- **Campaign name** — human-readable (e.g. *The Sunless Citadel Revisited*). Used in `CLAUDE.md` and `campaign.md`.
- **System** — the rule system (e.g. *D&D 5e*, *Pathfinder 2e*, *Call of Cthulhu*). Free-form prose.

If any of these are missing, the consumer must ask the GM for them before invoking the scaffolder. Don't invent campaign names or system labels.

## Step 1: Validate the target

1. Resolve the target directory to an absolute path.
2. If it doesn't exist, create it (and any missing parent directories).
3. If it exists and is non-empty, check for any of these markers of an existing campaign:
   - `campaign.md`
   - `.claude/rules/sessions.md`
   - `.claude/rules/adventures.md`
   - a `.git/` directory with any commits beyond an empty initial state

   If any marker is present, **stop** and tell the GM the directory looks like an existing campaign repo. Don't overwrite. Don't merge. (This is the same check `/ingest`'s scaffolded-precondition surface inspects in read-only mode.)
4. If it exists, is non-empty, and has none of those markers (e.g. it has source-doc markdown files the GM wants ingested in a later phase), confirm with the GM before proceeding.

## Step 2: Write the seven template files

The plugin ships seven templates under `../templates/` (relative to this reference). For each, read the template from that path, substitute placeholders, and write to the target. The agent's cwd is the *campaign* directory, not the plugin install — these relative paths resolve from the reading file's location, which is what Claude Code's markdown-link resolution uses for skill / reference reads. Filenames have a `.template` suffix in the plugin; strip the suffix on write.

**Order matters: `.claude/settings.json` is written FIRST so its permission rules are in effect before the remaining six writes.** The agent's first write of `.claude/settings.json` will prompt the GM for permission (the file doesn't exist yet, so no campaign-scoped permissions apply yet — this is unavoidable). After the GM accepts, the freshly-written `permissions.allow` array covers the remaining six template writes (`CLAUDE.md`, `.claude/rules/*`, `campaign.md`, `.gitignore` are all in the allow list), and the rest of the scaffold proceeds without further prompts. The file is written first even though it isn't committed (see Step 3) — it's gitignored from the start because it carries machine-local absolute paths.

Write the templates in this exact order:

| # | Template source (path relative to this reference) | Written to (relative to target) |
|---|---|---|
| 1 | `../templates/.claude/settings.json.template` | `.claude/settings.json` |
| 2 | `../templates/CLAUDE.md.template` | `CLAUDE.md` |
| 3 | `../templates/.claude/rules/sessions.md.template` | `.claude/rules/sessions.md` |
| 4 | `../templates/.claude/rules/adventures.md.template` | `.claude/rules/adventures.md` |
| 5 | `../templates/.claude/rules/style.md.template` | `.claude/rules/style.md` |
| 6 | `../templates/campaign.md.template` | `campaign.md` |
| 7 | `../templates/.gitignore.template` | `.gitignore` |

The `.gitignore` excludes `.ttrpg-staging/`, which the skills use as a scratchpad for diff-style review surfaces (proposed descriptions, brief drafts, wrap proposals) that the GM edits in their IDE before approval. Staging contents are never committed. It also excludes `.claude/settings.json` (next paragraph).

The `.claude/settings.json` pre-approves the standard Edit/Write/MultiEdit operations the plugin's skills perform on the campaign's structured folders (`npcs/`, `locations/`, etc.) so the GM isn't prompted for every file the agent writes during routine extraction. It also pre-approves a few read-only git commands the skills run for state inspection. The file is **gitignored** (the scaffolder's `.gitignore` excludes `.claude/settings.json`) because it carries absolute paths baked in at scaffold time — committing it would just guarantee drift on clone. The convention (which paths the plugin pre-approves) follows the campaign via the scaffolder template, not via a committed file; a fresh clone regenerates the file by re-running the scaffolder (via `/init-campaign` or `/ingest` Phase 1) against the clone's location.

### Placeholder substitutions

Apply these substitutions to template content before writing. The same map applies to every template; templates that don't reference a given placeholder are unaffected.

- `{{CAMPAIGN_NAME}}` → the GM-supplied campaign name, verbatim.
- `{{CAMPAIGN_SYSTEM}}` → the GM-supplied system, verbatim.
- `{{CAMPAIGN_PATH}}` → the resolved absolute path of the target campaign directory (e.g. `/Users/sofia/Documents/my-campaign`), **without** a trailing slash. The template uses this to bake absolute-path permission rules into `.claude/settings.json` (with a leading `/` already present in the template so the result is the `//absolute/path` form Claude Code's permission matcher requires). This makes permission grants survive any cwd or project-root resolution oddities. The cost is that moving the campaign directory invalidates the paths — the GM would need to regenerate (via `../references/preflight.md`) or hand-edit `.claude/settings.json` after a move.

The substitution is a literal string replacement — no escaping, no templating-language semantics. If a campaign name happens to contain `{{` or `}}`, that's fine: only the three documented tokens match.

Issue #69 dropped the prior `{{HOME}}` substitution: the plugin-install Read rule now uses `${CLAUDE_PLUGIN_ROOT}`, which Claude Code resolves at match time without an upfront text substitution. The scaffolder must not introduce new `{{...}}` placeholders without coordinating updates to every template and to the reference-impl test.

### Intermediate directories

Create intermediate directories as needed (notably `.claude/rules/`). Do not write any other files. In particular, do not create empty `npcs/`, `locations/`, `factions/`, `items/`, `adventures/`, `sessions/`, `threads/`, `consequences/`, `beats/`, or `pcs/` directories — they appear when content first lands in them, not before. (The `pcs/` directory is populated by `/ingest` Phase 2 Step 5b when the survey-confirmed PC roster is non-empty; it stays absent on a scaffold-only run, per [ADR-0018](../docs/adr/0018-pc-roster-as-survey-deliverable.md).)

## Step 3: Initialize the git repo and make an initial commit

Run these commands in the target directory:

```
git init
git add CLAUDE.md .claude/rules/sessions.md .claude/rules/adventures.md .claude/rules/style.md campaign.md .gitignore
git commit -m "Scaffold campaign repo via ttrpg-gm /ingest"
```

`.claude/settings.json` is **not** included in the `git add` argument list — it was written in Step 2 (so its permissions are in effect for the rest of the scaffolder run) but it's gitignored by the `.gitignore` Step 2 just wrote, so it stays untracked. Six files committed; seven files written. (Per [ADR-0021](../docs/adr/0021-gm-writing-style-via-claude-rules-style.md), `.claude/rules/style.md` is committed even though it's GM-authored thereafter — the GM's voice belongs in version control, and the agent's `Edit`/`Write`/`MultiEdit` against it is blocked by the `permissions.deny` block in `.claude/settings.json`.)

The commit message is the same regardless of which consumer invoked the scaffolder (`/ingest` Phase 1 today, `/init-campaign` post-v0.3, future `/init-adventure` standalone mode). Future tooling (e.g., an `/upgrade-campaign` skill) may consult the commit subject to detect plugin-scaffolded repos, so the subject line is load-bearing — keep it stable across consumers.

If `git init` reports the directory is already a git repo, do **not** re-init. Stage and commit on the existing branch only with explicit GM confirmation; otherwise stop and tell the GM.

Do not configure `user.name` or `user.email` from the plugin. Use whatever the GM's git config provides; if the commit fails because git has no identity configured, surface the underlying git error to the GM verbatim and stop.

## Step 4: Report what was written

Tell the GM, concisely:

- the target directory (absolute path),
- the six files committed in the initial commit (the five content templates plus `.gitignore`); note `.claude/settings.json` was also written but is intentionally gitignored (machine-local absolute paths),
- the initial commit's hash and message.

What happens after the report is consumer-specific:

- `/ingest` continues into Phase 2 (Survey) when invoked with an input directory, or ends the workflow when invoked scaffold-only. No confirmation prompt — downstream phases have their own review gates.
- `/init-campaign` continues into its pitch-elicitation conversational loop (post-v0.3).
- `/init-adventure` standalone mode hands off to the adventure-shaped content walkthrough (post-v0.3).
- `/ingest`'s "scaffolded?" precondition check (slice G) runs Step 1 inspection only and does not invoke Steps 2–4; it uses the marker check from Step 1 to decide whether to direct the GM to `/init-campaign` or proceed with extraction.

## Idempotency: re-running against an existing scaffold

If a consumer re-invokes the scaffolder against a target directory that already has the markers from Step 1 (`campaign.md`, `.claude/rules/sessions.md`, `.claude/rules/adventures.md`, or non-trivial `.git/`), Step 1 stops before any file is written. The existing campaign is untouched — no template overwrites, no second commit, no `git init` re-run. This is the intended contract: the scaffolder is destructive of an empty target and protective of a populated one. There is no merge-mode, no force-mode, no `--update` flag; a GM who wants to refresh just `.claude/settings.json` after a move uses `../references/preflight.md`, not the scaffolder.

The "exists but non-empty without markers" case (Step 1.4) is the one consumer-confirmable path. If the GM confirms, the scaffolder proceeds as if the target were empty — the existing non-marker files are left in place and the seven templates land alongside them. The initial commit only stages the six scaffolded paths; pre-existing files stay untracked unless the GM stages them separately.

## What this reference does NOT cover

- **Permission-prompt UX.** The first `.claude/settings.json` write triggers a permission prompt; the agent's response handling for that prompt is Claude Code platform behavior, not scaffolder spec.
- **Path preflight on already-scaffolded campaigns.** That's `../references/preflight.md`'s job. The scaffolder writes paths the preflight may later detect as stale; recovery from staleness is out of scope here.
- **The post-scaffold workflow.** Each consumer handles its own next-phase routing per Step 4. The scaffolder ends at the initial commit.
- **Validation of template content.** The scaffolder is a pass-through over `../templates/`. Template-content invariants (Adventure status enum, `permissions.allow` shape, etc.) are validated by `../tests/test_ingest_scaffolding.py` and `../tests/test_settings_template.py`, not by the runtime scaffolder.
