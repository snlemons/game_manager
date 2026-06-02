# Campaign-repo location pattern

Every v0.3 skill that touches campaign content has to answer the same upstream question first: *am I sitting in a scaffolded campaign repo?* The answer routes to one of four orchestration shapes depending on the skill's intent. This reference is the canonical home for the **marker set** that defines a scaffolded campaign and the **four routing shapes** the skills use; each consuming SKILL.md cites this reference and layers its skill-specific phrasing (verbatim hard-stop messages, GM-facing locate-or-ask prompts, mode confirmation prompts) on top.

Per [ADR-0019](../docs/adr/0019-init-campaign-as-bootstrapping-front-door.md) the marker set is load-bearing — it's the structural definition of "scaffolded" that distinguishes the bootstrap entry (`/init-campaign`) from the extension entries (`/ingest`, `/init-adventure`, `/prep-session`, `/wrap-session`). Per [ADR-0020](../docs/adr/0020-modularization-via-shared-references.md) the marker check is consumed by ≥2 skills, so it lifts to a shared reference instead of duplicating across SKILL.md prose.

## The four-marker set

A directory counts as a scaffolded campaign repo when **all four** of these files are present at the directory root:

1. `CLAUDE.md`
2. `.claude/rules/sessions.md`
3. `.claude/rules/adventures.md`
4. `campaign.md`

The check is a read-only `is_file()`-equivalent presence test. Content is not validated — the scaffolder owns content invariants at write time (see `scaffolder.md` Step 1), and the runtime location check only inspects presence. An empty `CLAUDE.md` counts as present; a missing-but-named symlink does not.

The marker list is the same one `scaffolder.md` Step 1 consults when it refuses to overwrite an existing campaign (the scaffolder additionally inspects `.git/` to detect "this is already a repo," but runtime location checks ignore `.git/` — see the note under "What this reference is not" below). When the marker list changes — adding a fifth required file, dropping one — both this reference and `scaffolder.md` Step 1 must update together.

### Why these four specifically

- **`CLAUDE.md`** carries the campaign-scoped agent instructions; without it, the agent has no campaign-local glossary or rules to consult.
- **`.claude/rules/sessions.md`** and **`.claude/rules/adventures.md`** are the path-scoped rule files [ADR-0012](../docs/adr/0012-rule-organization-via-claude-rules.md) introduces — their presence signals the campaign was scaffolded by the plugin, not just any directory the GM dropped a `CLAUDE.md` into.
- **`campaign.md`** is the agent-maintained Campaign overview ([ADR-0007](../docs/adr/0007-temporal-model-and-campaign-overview.md)) — its presence signals the scaffold completed (not interrupted mid-write).

Each of the four is mandatory because dropping any one would let a half-scaffolded or partially-deleted campaign masquerade as scaffolded.

## The four orchestration shapes

Each consuming skill applies the marker check and routes based on what it found. The four shapes below differ in **what they do with the answer**, not in **how they ask the question** — the question is always the same four-marker presence test.

### Shape A — Hard-stop

**Used by:** `/ingest` (its upfront precondition check, slice G).

**Semantics:** the skill cannot do meaningful work without a scaffolded campaign — `/ingest`'s job is to extract content *into* one — and the user-facing remediation is to route to `/init-campaign`. The hard-stop is the load-bearing UX: it tells the GM exactly which verb to invoke instead, so the misrouted call is one prompt away from recovery rather than a confused multi-turn negotiation.

**Routing:**

- **All four markers present:** silently proceed to the next step (typically the settings preflight).
- **Any marker absent:** hard-stop with a verbatim GM-facing message that names `/init-campaign` as the bootstrap entry and `/ingest` as the verb to retry once the scaffold is restored. The exact message text lives in the consuming SKILL.md, not here — see `skills/ingest/SKILL.md` "Precondition: scaffolded?" for the verbatim phrasing slice G pinned.

**Invariants:**

- No filesystem writes at this step, regardless of outcome.
- No conversational fallback — the skill does not ask the GM "where is the campaign?" because the failure mode is intentional misrouting, not user confusion about cwd. (`/ingest` against an unscaffolded directory is the v0.1/v0.2 muscle-memory case ADR-0019 is replacing.)
- No silent fallback to `/init-campaign` — the skill names the next verb but does not invoke it. Skill composition is the GM's call.

### Shape B — Locate-or-ask

**Used by:** `/prep-session` (Step 0), `/wrap-session` (Step 0).

**Semantics:** the skill operates against an established campaign — cwd is the most common but not guaranteed campaign root (the GM may invoke from a sibling directory or from a worktree). When cwd is the campaign, the skill silently uses it; when it isn't, the skill asks the GM for the campaign path and re-checks there. This is the asymmetric case Shape A doesn't cover — both `/prep-session` and `/wrap-session` are extension verbs whose value-add lives entirely inside an existing campaign, but neither has a "go bootstrap one" recovery to point at the way `/ingest` does, because the GM clearly already has a campaign in mind.

**Routing:**

- **All four markers present in cwd:** cwd is the campaign repo — use it as the campaign root for the rest of the workflow.
- **Any marker absent in cwd:** ask the GM for the absolute path of the campaign repo. Resolve their answer to an absolute path (accept `~/`-anchored paths). Re-check the four markers at that path.
  - **All four markers present at the GM-supplied path:** use it as the campaign root.
  - **Any marker still absent:** surface what was missing and stop. The campaign isn't scaffolded; this is not a Shape A hard-stop with a route-to-`/init-campaign` message (because the GM has supplied a path they believe is a campaign) — it's a "your campaign at this path looks broken" surface. The skill stops without proceeding to the rest of the workflow.

**Invariants:**

- Every path the rest of the workflow touches (`sessions/...`, `adventures/...`, `beats/...`, `.ttrpg-staging/...`) resolves *relative to the campaign root*, not relative to cwd. Pass absolute paths to file tools so they work regardless of cwd.
- Do not repeat the locate-or-ask exchange if the campaign root is already determined in this run. The check is per-invocation, not per-step.
- The skill-specific phrasing of the GM-facing question (the verbatim "I don't see a scaffolded campaign in the current directory" prompt) lives in the consuming SKILL.md, not here — see `skills/prep-session/SKILL.md` and `skills/wrap-session/SKILL.md` Step 0 for the canonical phrasings.

### Shape C — Auto-detect mode

**Used by:** `/init-adventure` (Step 0a).

**Semantics:** the skill runs in one of two modes — **in-campaign** (cwd is already a scaffolded campaign; add the new Adventure to it) or **standalone** (cwd is not yet a campaign; scaffold a campaign-shaped repo, then add the Adventure as its first). The marker check decides the mode; a GM confirmation prompt before any filesystem write is the load-bearing safety net for ambiguous cases.

**Routing:**

- **All four markers present in cwd:** in-campaign mode. The cwd is the campaign root.
- **None of the four markers present, and cwd is empty (or contains only files the GM has confirmed are not a campaign repo):** standalone mode. The cwd will become the campaign root after the scaffolder runs.
- **Some markers present, others absent:** the cwd looks like a partially-scaffolded or half-broken campaign. **Stop** and surface to the GM with the absent vs. present marker list, asking whether to run from a different directory.
- **Non-campaign content present and not GM-confirmed as safe:** ask before continuing — offering the standalone-alongside-existing-files path or the wrong-directory exit.

**Invariants:**

- The detection is a **check, not a write** — no files change at the detection step.
- A GM confirmation prompt **must** run before any filesystem write per ADR-0019's "wrong-mode write is high-cost" principle. The skill-specific phrasing of that prompt lives in the consuming SKILL.md, not here — see `skills/init-adventure/SKILL.md` Step 0b for the canonical phrasings of the two confirmation cases (in-campaign vs. standalone).
- The GM can override the detected mode at the confirmation prompt (in-campaign → standalone, or vice versa). The marker check is the agent's best read; the GM owns the final call.

### Shape D — Already-scaffolded?

**Used by:** `/init-campaign` (Step 7 / Step D1, via the shared scaffolder).

**Semantics:** the skill's whole job is to scaffold a campaign repo. The marker check answers the question *"is there already a scaffolded campaign here that we'd be clobbering?"* The scaffolder reference owns the canonical check (and additionally consults `.git/` for the "already a git repo" case); `/init-campaign` consumes the scaffolder, so Shape D reduces to "delegate to the scaffolder's Step 1 marker check."

**Routing:**

- **All four markers present (or any other scaffolder Step 1 marker like a non-trivial `.git/`):** the scaffolder refuses to re-scaffold and stops. `/init-campaign` surfaces the refusal to the GM and does not proceed to its from-scratch / docs-mode steps (there is no campaign to bootstrap — one already exists).
- **All four markers absent and the target directory is empty (or doesn't yet exist):** the scaffolder proceeds with its Steps 2–4 writes. `/init-campaign` continues into its post-scaffold steps (pitch elicitation, PC roster, optional first-Adventure sub-flow in from-scratch mode; the extraction pipeline in docs mode).
- **All four markers absent but the directory contains non-campaign files** (source-doc markdown the GM is about to ingest, loose notes the GM has not yet ingested): the scaffolder's Step 1.4 branch asks for GM confirmation before scaffolding alongside the existing files. `/init-campaign` surfaces that confirmation to the GM.

**Invariants:**

- The marker check is delegated to the scaffolder's Step 1 — `/init-campaign` does not re-implement it.
- The scaffolder's idempotency contract guarantees the check is destructive of an empty target and protective of a populated one. There is no merge-mode, no force-mode.
- The skill-specific orchestration on top of the scaffolder delegation (mode prompt, pitch refinement, PC roster, optional first-Adventure handoff) lives in the consuming SKILL.md, not here — see `skills/init-campaign/SKILL.md` for the canonical orchestration.

## Why one reference, four shapes

The marker set is one thing — a structural definition of "scaffolded campaign repo." The four shapes are four orchestration patterns layered on top of that single definition. Lifting the marker set to a shared reference means a future change to what counts as scaffolded (adding a fifth required file, dropping `.claude/rules/adventures.md`) is one edit here plus a coordinated edit in `scaffolder.md` Step 1 — not four edits across four SKILL.md files. The shape definitions, by contrast, are stable in shape (each skill's *intent* is fixed) but vary in phrasing (each SKILL.md owns its GM-facing message). Layering the phrasing on top of the shape means the GM-facing UX stays skill-owned while the structural check stays single-source.

This is the same pattern `staging-pattern.md` uses for the multi-skill staging lifecycle — one reference documents the shared lifecycle, each SKILL.md documents the per-skill sub-paths and response shapes on top. The campaign-locate pattern follows the same shape: one reference for the marker set + the four routing shapes, four SKILL.md files for the verbatim phrasings.

## What this reference is not

- **Not the scaffolder spec.** `scaffolder.md` owns the procedure for *writing* the seven template files, the `git init`, and the initial commit when scaffolding a new campaign. This reference owns the inspection-only marker check that decides whether scaffolding is needed (Shape D) or whether the campaign root is correctly located (Shapes A/B/C). The marker list overlaps with the scaffolder's Step 1 marker list; the writing procedure does not.
- **Not the settings preflight.** `preflight.md` owns the check for whether `.claude/settings.json`'s baked absolute paths still match the campaign root. The campaign-locate check runs before the preflight (it identifies the campaign root the preflight then validates settings against), so the two are sequential, not overlapping.
- **Not a `.git/` check.** The scaffolder consults `.git/` at Step 1 to detect "already a git repo" — that's a scaffolder-specific concern (refusing to re-init). Runtime location checks (Shapes A/B/C) ignore `.git/`: the agent's question is "is this a scaffolded *campaign*?", and a directory can be a git repo without being a scaffolded campaign. Shape D delegates to the scaffolder, so it inherits the `.git/` check via that delegation.
- **Not a heuristic-with-content-validation.** The check is purely structural — file presence only. Content invariants (Adventure status enum, `permissions.allow` shape, etc.) are validated by other test surfaces, not by the location check.
- **Not skill-discovery.** This reference does not answer "which skill should the GM invoke?" — that's the SKILL.md description fields and the GM's intent. Each shape encodes *what one specific skill does* once it knows where the campaign root is (or isn't).

## Cross-references

- `scaffolder.md` Step 1 — the canonical marker list at scaffold time (writes), shared with this reference's marker list (reads).
- `skills/ingest/SKILL.md` "Precondition: scaffolded?" — Shape A's verbatim hard-stop phrasing.
- `skills/prep-session/SKILL.md` Step 0 — Shape B's locate-or-ask phrasing, plus the settings preflight integration.
- `skills/wrap-session/SKILL.md` Step 0 — Shape B's locate-or-ask phrasing (sibling to `/prep-session`), plus the settings preflight and bidi-link lint integration.
- `skills/init-adventure/SKILL.md` Step 0 — Shape C's mode auto-detection plus the GM confirmation prompt.
- `skills/init-campaign/SKILL.md` Steps 7 / D1 — Shape D's scaffolder delegation.
- [ADR-0019](../docs/adr/0019-init-campaign-as-bootstrapping-front-door.md) — the skill split that makes the four shapes coherent (`/init-campaign` is the bootstrap front door; `/ingest`, `/prep-session`, `/wrap-session`, `/init-adventure` are extension verbs).
- [ADR-0020](../docs/adr/0020-modularization-via-shared-references.md) — the modularization discipline this reference is an instance of.
