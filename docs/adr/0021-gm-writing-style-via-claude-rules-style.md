# GM writing-style and tone guide via `.claude/rules/style.md`

Agent-drafted prose in a campaign — Briefs, Logs, Reference-note bodies, Adventure descriptions, Thread / Consequence / Beat / Secret prose, regenerated `campaign.md` — currently has no GM-authored voice steering. Output drifts toward the model's house voice (mid-formal, mid-tense, model-generic vocabulary) instead of matching the campaign's prose tone. v0.2 dogfooding surfaced this as a consistent friction: every artifact needs hand-correction for voice even when its structure is fine.

This ADR pins the steering mechanism: a **GM-authored `.claude/rules/style.md`** file, scaffolder-shipped as a stub, auto-loaded via `paths:` frontmatter whenever the agent edits artifacts under the campaign's content-bearing directories. The file is read by the agent and **never written by it**; the scaffolder seeds the stub once, and the GM owns its contents thereafter.

See [issue #56](https://github.com/snlemons/game_manager/issues/56) for the source analysis and the four options considered (A: rule-file + path-glob; B: `CLAUDE.md` section; C: standalone file + explicit skill reads; D: extraction-skill-derived profile). This ADR adopts Option A.

## Why a rule file, not a `CLAUDE.md` section or a standalone file

The two rejected alternatives both fail load characteristics:

- **`CLAUDE.md` section.** Always loaded into every interaction, including ones that draft nothing. Style prose riding into `/timeline` or `/wrap-session`'s extraction pass is dead weight in working context. The `CLAUDE.md` budget belongs to cross-cutting campaign facts (system, linking syntax, lifecycle-object overview) that the agent uses constantly; style prose belongs scoped to drafting moments.
- **Standalone file + explicit skill reads.** Every drafting skill must opt-in via prose like *"read `style.md` before drafting any Log."* New skills (`/init-campaign`, `/init-adventure`, future authoring skills) would silently miss it unless their authors remember to add the opt-in. Path-scoped rule loading auto-applies on the right paths without per-skill plumbing.

The path-scoped rule mechanism solves both: load when an artifact is being touched, skip otherwise, no per-skill opt-in required. The mechanism is the same one [ADR-0012](./0012-rule-organization-via-claude-rules.md) established for session and adventure conventions; this ADR is purely additive within that pattern.

## Why GM-authored, not agent-extracted

[Issue #56](https://github.com/snlemons/game_manager/issues/56)'s Option D proposed an extraction skill (analogous to the `sme-voice-profile` pattern) that derives a voice profile from existing GM-authored prose. Rejected for v0.3 as the *primary* mechanism — extraction quality is its own design problem, and a campaign's style preferences often diverge from its existing corpus (the GM is *changing* their voice for this campaign, not preserving the last one). The consumption surface needs to ship before the extraction layer is worth building. A future `/extract-style` skill that drafts the initial `style.md` from existing prose is plausible as an add-on; the consumption mechanism this ADR pins does not block or commit to it.

## The GM-authored-not-agent-written contract

The template ships with placeholder sections and example prose blocks. Once the GM edits the file, the agent **reads but does not write** to it. This is the inverse of the [ADR-0007](./0007-temporal-model-and-campaign-overview.md) GM-editorial unread file (themes, pitch, house rules) — that one the agent doesn't touch *at all*; this one the agent reads on every matching draft but cannot edit. Three categories of campaign files now exist by edit-direction:

| Category | Example | Agent reads? | Agent writes? |
|---|---|---|---|
| Agent-maintained | `campaign.md`, Log drafts during `/wrap-session` | Yes | Yes (regenerated / drafted) |
| GM-editorial unread | the file referenced by ADR-0007 line 41 (themes, pitch, house rules) | No | No |
| **GM-authored steering** | **`.claude/rules/style.md` (this ADR)** | **Yes** | **No** |

The contract is enforced two ways: (1) the template file's header prose tells the GM the contract explicitly so manual agent prompts to "edit my style.md" land on a refusal, and (2) the scaffolded `.claude/settings.json` carries `permissions.deny` entries for `Edit` / `Write` / `MultiEdit` against the specific path, so even if a skill or sub-agent attempts a write the permission matcher rejects it. The deny entries are an interlock, not the primary contract — the primary contract is the prose at the top of the file.

## Path-glob mechanism

The stub ships with this frontmatter:

```yaml
---
paths:
  - "sessions/**/*.md"
  - "adventures/**/*.md"
  - "npcs/**/*.md"
  - "pcs/**/*.md"
  - "locations/**/*.md"
  - "factions/**/*.md"
  - "items/**/*.md"
  - "threads/**/*.md"
  - "consequences/**/*.md"
  - "beats/**/*.md"
  - "secrets/**/*.md"
---
```

The eleven globs cover every content-bearing campaign directory — every directory the GM-facing prose lives in. Auto-load fires when the agent reads or edits any markdown file inside any of them. `campaign.md` (campaign root) is deliberately excluded because its composer (`references/campaign-overview-composer.md`) is structured by the spec, not by free prose — the style guide has little to apply there. The campaign's own `CLAUDE.md` and the other `.claude/rules/*.md` files are also excluded; they aren't artifacts whose voice the GM cares about.

The GM may add or remove globs to suit. The starter set is generous; trimming it to (say) `sessions/**` only would scope the steering to Briefs and Logs alone, which is a reasonable simpler stance for GMs who only care about narrative-voice in those documents.

## Template content principles

The stub follows three principles from [issue #56](https://github.com/snlemons/game_manager/issues/56)'s recommendation:

1. **Prose with examples, not rule lists.** Show what the voice sounds like; don't try to fully axiomatize it. Each placeholder section pairs a one-line prompt question with an inline example block (in a blockquote) the GM replaces with their own prose. Rule lists invite over-specification and lose the cadence-and-feel signals that examples carry naturally.
2. **Tight length budget.** The header guidance says roughly 50 to 200 lines. The file rides into working context on every matching draft; bloat costs agent attention the prose itself needs. The stub is around 70 lines as shipped, leaving headroom for GM additions.
3. **Empty sections are signals, not failures.** The stub explicitly tells the GM to leave or delete sections they don't care about. An empty "tense" section signals no strong preference — better than a fabricated one the agent then applies inappropriately.

Placeholder sections cover the categories #56 surfaced: formality and register, tense (especially narrative tense for Logs), vocabulary preferences, PC referencing conventions, narrative voice, and an open "anything else" section for patterns that don't fit the named categories.

## Composition with ADR-0012

[ADR-0012](./0012-rule-organization-via-claude-rules.md) pinned `.claude/rules/` as the directory for path-scoped rules, with the plugin owning specific filenames (`sessions.md`, `adventures.md`) and the GM free to add their own. This ADR adds a third plugin-owned filename — `style.md` — but with a different ownership semantic: the plugin owns the *initial scaffold* of the file's contents; the GM owns the file thereafter. ADR-0012's directory-ownership rule ("the plugin owns specific filenames, not the directory") is unchanged; this ADR refines it to ("the plugin owns specific filenames; for some of them, ownership of the file body transfers to the GM after scaffold").

The agent never proposes edits to `style.md` during `/wrap-session`, `/ingest`, or any other workflow. If the GM asks the agent to "update the style file," the agent surfaces the GM-authored contract and declines the write; the GM edits the file directly in their IDE.

## Considered alternatives (rejected)

- **`CLAUDE.md` section** — see "Why a rule file" above. Loads on every interaction; wrong context budget.
- **Standalone file with per-skill reads** — see same section. No auto-load; new skills miss it silently.
- **Extraction skill (`sme-voice-profile`-style)** — see "Why GM-authored" above. Plausible add-on; not the primary consumption mechanism.
- **Per-artifact style files (`style-briefs.md`, `style-logs.md`, ...)** — rejected as premature. v0.3 ships one file covering all artifacts; if dogfooding shows the lump is too coarse (Brief voice vs. Log voice diverging), a future ADR shards the file. Starting with one file lets us discover whether the shard is actually needed.
- **Atlas-level / GM-level style files inheriting into campaigns** — out of scope for v0.3. Adds install-clone-vs-campaign-clone resolution complexity (per #56's *"per-GM"* scope note). Per-campaign style is the v0.3 lean; cross-campaign style propagation is a future Atlas-adjacent concern.

## What this ADR does not commit to

- **Per-artifact style sharding.** Single file for v0.3. Future PRD if dogfooding diverges.
- **An `/extract-style` skill.** Plausible later; not part of v0.3.
- **Inheritance from an Atlas or user-level style file.** Per-campaign only.
- **Agent-side style validation.** The agent applies the style guide as steering; it does not lint drafts against the file's content or report style-conformance metrics. The GM is the only arbiter of whether the voice landed.
- **Migration for existing v0.1 / v0.2 scaffolded campaigns.** Existing campaigns can opt in by creating `.claude/rules/style.md` by hand using this template as a model; an automated `/upgrade-campaign` path is out of scope (same as the rule-drift concern noted in ADR-0012).

## Consequences

- New `templates/.claude/rules/style.md.template` — stub with GM-authored-not-agent-written header, eleven-path frontmatter, six placeholder sections with prose-and-example shape.
- `templates/.claude/settings.json.template` gains a `permissions.deny` block carrying `Edit` / `Write` / `MultiEdit` entries against `/{{CAMPAIGN_PATH}}/.claude/rules/style.md`. The deny block is new — settings template previously had only `permissions.allow`.
- `templates/CLAUDE.md.template` gains a short *"Writing style and voice"* section pointing at the rule file and surfacing the GM-authored contract, plus a Pointers entry.
- `CONTEXT.md` gains a *"Writing style guide"* glossary entry distinguishing this file from the ADR-0007 GM-editorial unread file and from agent-maintained files like `campaign.md`.
- A new `tests/test_style_template.py` validates the stub's structural shape (YAML-parseable frontmatter with the eleven globs, presence of the GM-authored contract prose, ASCII-only quotes, line-count within the documented budget) and the `permissions.deny` block in `settings.json.template` carries the expected three entries against the style file path.
- The template file lands under `templates/.claude/rules/` in this slice but the scaffolder ship-list wiring landed separately in issue #103 (slice K follow-up). That follow-up extended `references/scaffolder.md`'s file-enumeration table from six rows to seven, added `.claude/rules/style.md` to the initial-commit `git add` line (the file is committed, not gitignored — the GM's voice belongs in version control), and extended `EXPECTED_SCAFFOLDED_FILES` / `EXPECTED_COMMITTED_FILES` in `tests/test_ingest_scaffolding.py` plus added a `TestStyleRuleShipped` class covering disk-write / initial-commit / template-byte-equality. New campaigns scaffolded after #103 land automatically include `.claude/rules/style.md`; the design committed by this ADR (file, location, contract, glob set) was unchanged by the wiring slice.
- Future authoring skills (`/init-campaign`, `/init-adventure`, future `/draft-*` skills) automatically pick up the style steering on matching paths with no per-skill opt-in, now that the scaffolder wiring (#103) has landed. New content directories added in future versions need their globs added to the stub (or the GM extends the campaign's own copy).
