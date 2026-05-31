# Bidirectional `## Secrets` link maintenance

Per [ADR-0014](../docs/adr/0014-secrets-as-multi-container-lifecycle-objects.md), every container listed in a Secret's `belongs_to:` carries a `## Secrets` section in its file body wiki-linking back to the Secret file. **The Secret file is the source of truth for content; the container's section is a derived view the agent maintains on every Secret write.** This reference is the canonical prose spec for that maintenance algorithm — the linker that keeps Secret↔container symmetry intact, and the linter that flags drift caused by manual GM edits.

The reference Python at [`tests/test_bidi_link.py`](../tests/test_bidi_link.py) (shipped by issue #36) is a near-translation of the algorithm described here; the v0.1 convention is that the SKILL.md prose describes the algorithm the LLM follows at runtime, and the reference Python pins the spec so drift between the prose and the algorithm becomes a test failure. Changes here must keep that suite green and stay reflected in the prose.

The Secret schema (where `belongs_to:` is defined as a non-empty list of non-ephemeral container paths) lives in [`~/.claude/skills/ttrpg-gm/references/frontmatter-schemas.md`](./frontmatter-schemas.md). The Secret extraction heuristic that produces the candidate `belongs_to:` list lives in [`~/.claude/skills/ttrpg-gm/references/secret-extraction.md`](./secret-extraction.md). The store enumeration that the linter walks lives in [`~/.claude/skills/ttrpg-gm/references/secret-store.md`](./secret-store.md).

## Two operations

This reference covers two operations, both invoked from `/wrap-session`, `/prep-session`, and `/ingest`:

- **`apply_belongs_to`** — given a Secret being written (newly created or having its `belongs_to:` modified), ensure every container in `belongs_to:` carries a `## Secrets` section back-linking the Secret. Idempotent on re-apply: re-running against an already-linked container is a no-op (the file's bytes don't change).
- **`lint`** — walk the campaign, find drift cases where the symmetry is broken (orphan wiki-links pointing at deleted Secrets, missing back-references where a Secret claims a container but the container doesn't link back). Reported as findings the GM can reconcile.

## `apply_belongs_to` — the maintenance algorithm

**Input:** a campaign root, a Secret slug, the Secret's `belongs_to:` list, and a short summary string (one line, used as the bullet's trailing description — typically pulled from the Secret's H1 or the first sentence of its body).

**Output:** a per-container result map: `True` if the container's file was modified (back-link added), `False` if the file was already correct (idempotent no-op).

**Behavior, per container in `belongs_to:`:**

1. **Resolve the container path to its file.** For Reference-note containers (`npcs/<slug>.md`, `locations/<slug>.md`, `factions/<slug>.md`, `items/<slug>.md`, `pcs/<slug>.md`), the path *is* the file. For Adventure containers (`adventures/<slug>/`, directory form, trailing slash), resolve to `adventures/<slug>/adventure.md` per the Adventure schema.
2. **Verify the container file exists.** If the file does not exist, surface the missing file to the GM and stop — **do not silently scaffold a container from a Secret write**. The Secret's `belongs_to:` is a claim about containers the campaign already has; if a claim is wrong, the GM resolves it (rename the slug, create the container first, or remove the entry from `belongs_to:`).
3. **Read the container file.** Split into frontmatter (preserve verbatim) and body.
4. **Check for an existing back-reference.** Scan the body for any wiki-link of the form `[[secrets/<slug>]]` matching the Secret slug being applied. The match is on the wiki-link text only; the spec requires the link to live under a `## Secrets` heading, but the linker treats any body-position back-reference as satisfying the symmetry (the section grouping is editorial — the load-bearing property is link presence).
5. **If a back-reference is already present, the file is correct.** Return `False` for this container; do not modify the file.
6. **Otherwise, add the back-reference.** The bullet shape is `- [[secrets/<slug>]] — <summary>`. Insert it into the body:
   - **If a `## Secrets` section already exists**, append the bullet at the end of that section (just before the next `## ` heading, or at EOF if no further H2). Preserve every existing bullet in the section — never overwrite GM-authored entries.
   - **If no `## Secrets` section exists**, append a fresh section at the end of the file: a blank line, then `## Secrets`, then a blank line, then the bullet, then a trailing newline.
7. **Rewrite the file.** Preserve the frontmatter block byte-for-byte. Write the new body in place of the old body.
8. Return `True` for this container.

**Idempotency.** Running the algorithm twice against the same Secret + container produces identical bytes on the second run. The first run adds the bullet; the second run finds the existing back-reference in step 4 and short-circuits in step 5. The test suite asserts byte-identical-on-rerun; any implementation that adds duplicate bullets or whitespace drift on re-apply is a bug.

**Frontmatter preservation.** The container's frontmatter is preserved verbatim — never rewritten, never reordered, never re-serialized. The linker only touches body text. If the container has no frontmatter, the file is treated as all-body.

**Adventure container resolution.** `adventures/the-prism/` resolves to `adventures/the-prism/adventure.md`. The directory itself is not a markdown file; the link goes into the Adventure's main markdown file. The `## Secrets` section sits in the body of `adventure.md` just like any other Reference note.

## When to invoke `apply_belongs_to`

Every time a Secret is created or its `belongs_to:` is modified:

- **`/wrap-session`** Step 5 — after writing a newly approved Secret file, call `apply_belongs_to` with the Secret's slug, `belongs_to:` list, and a summary derived from the Secret's H1.
- **`/ingest`** Phase 3 — same shape: after writing each approved Secret in a doc's batch, call `apply_belongs_to` to maintain the back-references in every named container.
- **`/wrap-session` Secret merge (dedup UPDATE).** When the dedup rule (`~/.claude/skills/ttrpg-gm/references/dedup-matching.md`) routes a candidate Secret to a confident UPDATE on an existing Secret with an added container in `belongs_to:`, the new container needs a back-reference too. Call `apply_belongs_to` with the full updated `belongs_to:` list — the previously-linked containers short-circuit (idempotent no-op) and only the newly added container is modified.

Do **not** invoke `apply_belongs_to` when a Secret's body changes without the `belongs_to:` set changing — the back-references already exist and the summary on the bullet is a stable one-liner, not a live mirror of the Secret's body. (A future revision of this spec might re-sync summaries on body changes; v0.1 leaves the bullet text stable to avoid spurious file churn.)

## The staging-pattern wrapper

`apply_belongs_to` operates on **live files**, not staged files. The staging pattern (`~/.claude/skills/ttrpg-gm/references/staging-pattern.md`) defers writes outside `.ttrpg-staging/` until after GM approval, so the bidi-link maintenance follows the same two-step shape every UPDATE entry does:

1. **At staging time (Step 4 of `/wrap-session`'s and `/ingest`'s respective review steps):** for each container in the Secret's `belongs_to:` that does not already back-link the Secret, stage an UPDATE entry for that container — `cp` the live container file into `.ttrpg-staging/wrap/<container-path>` (or `.ttrpg-staging/doc-<N>/<container-path>` for `/ingest`), then Edit the staged copy to add the `## Secrets` bullet. This makes the proposed change visible in the GM's IDE diff alongside the Secret's CREATE entry.
2. **At promotion time (Step 5):** the staged container file moves to the live container path, replacing the previous content. The `apply_belongs_to` algorithm runs against the *live* tree as a verification pass — if the GM didn't edit the staged container away, the verification is a no-op; if the GM deleted the staged container (rejecting the back-reference write), the live container retains its prior state and a lint finding will surface the missing back-reference on the next preflight.

Skills that need only the live-tree apply (e.g., `/prep-session` does not write Secrets but may need to heal a lint case the GM acknowledged) can call `apply_belongs_to` directly without staging.

## `lint` — the symmetry-drift detector

**Input:** a campaign root.

**Output:** a list of findings, each carrying:

- `kind` — `"orphan"` or `"missing-back-reference"`.
- `container` — the container file's path relative to the campaign root (or the raw `belongs_to:` entry for missing-back-reference findings where the container file itself doesn't exist).
- `secret_slug` — the Secret slug at issue.
- `message` — a self-contained, actionable message naming the container path and the slug, so a GM reading the lint output can act on it without cross-referencing other state.

**Two failure modes surfaced:**

### 1. Orphan wiki-links

A container file contains a `[[secrets/<slug>]]` wiki-link in its body, but no `secrets/<slug>.md` file exists. The container is referencing a deleted or renamed Secret.

**Detection:**

1. Enumerate the set of valid Secret slugs (`{p.stem for p in secrets/*.md}`).
2. For every container file under the non-ephemeral folder roots (`npcs/`, `pcs/`, `locations/`, `factions/`, `items/` — each file; `adventures/<slug>/adventure.md` for Adventures), scan the body for wiki-links matching `[[secrets/<slug>]]`.
3. For each linked slug that is not in the valid-Secret set, emit an `"orphan"` finding.

**Resolution path the GM has:** rename the Secret back to the expected slug, or remove the orphan wiki-link from the container body. Neither action is one the agent takes silently — the lint surfaces the case for GM judgment.

### 2. Missing back-references

A Secret's `belongs_to:` claims a container, but the container's body has no wiki-link back to the Secret. The Secret-side claim is in place; the container-side back-reference is missing.

**Detection:**

1. For every Secret file under `secrets/*.md`, parse the `belongs_to:` list.
2. For each container in the list:
   - **If the container file does not exist**, emit a `"missing-back-reference"` finding noting that the container file itself is missing. (The Secret's claim is wrong, or the container was deleted after the Secret was written.)
   - **If the container file exists** but its body has no `[[secrets/<slug>]]` wiki-link back to this Secret, emit a `"missing-back-reference"` finding noting the symmetry break.

**Resolution path the GM has:** the agent can heal the case by re-running `apply_belongs_to` with the Secret's current `belongs_to:` — that's the corrective write the symmetry contract describes. Alternatively, the GM can edit the Secret's `belongs_to:` to remove the unlinked container, which makes the lint go quiet without a back-reference write. Both are valid; the lint surfaces; the GM picks.

## When to invoke `lint`

The lint is **not** invoked on every skill run — it walks the full `secrets/` tree and every container file, which is more work than the per-Secret `apply_belongs_to` pass needs.

The intended invocation points:

- **`/wrap-session` Step 0** (settings preflight is already idempotent; the bidi-link lint can run alongside it once per wrap invocation, surfacing findings before extraction starts). Findings are reported to the GM as part of the closing message or as ambiguity clarification if they overlap with the wrap's work.
- **`/prep-session`** at preflight — same shape.
- **`/ingest` Phase 4** — final pass after all per-doc Secret writes, catching cases where one doc's Secret references a container another doc didn't yet write.
- **On-demand** when the GM asks the agent to "check Secret links" or sees suspicious Brief output (a Secret expected but missing from the Secret Push question).

If the lint finds nothing, the agent doesn't surface anything — silence is the success signal. If the lint finds drift, the agent reports the findings as a short list with the actionable message per finding, and asks whether to heal them now (re-run `apply_belongs_to` for the missing-back-reference cases) or surface them for GM manual review.

## What this algorithm does not handle

- **Cross-campaign Secrets / Atlas content.** v0.1 is single-repo (ADR-0006); the linter walks one campaign root only. If a future Atlas exposes shared Secrets, the linter's container enumeration needs to grow — out of scope here.
- **Renamed containers.** If the GM renames `npcs/maren.md` to `npcs/maren-ironweave.md`, every Secret with `npcs/maren.md` in its `belongs_to:` becomes a missing-back-reference finding (the container path is wrong, even if `npcs/maren-ironweave.md` does back-link). The agent surfaces the case; the GM updates the Secret's `belongs_to:` (the right fix). The linter doesn't auto-rename.
- **Renamed Secrets.** Same shape: the agent doesn't auto-update wiki-links in container bodies when a Secret slug changes. Renaming a Secret is the GM's action; the lint catches the drift on the next preflight.
- **Section content beyond the back-reference bullet.** GMs may write additional prose under `## Secrets` (a paragraph framing the section, a sub-heading for "Secrets the party suspects but doesn't know"). The linker treats any back-reference in the body as satisfying the symmetry — the section's *content* is GM-owned, not agent-owned.
- **Heading-case variants.** `## Secrets`, `## secrets`, `## SECRETS` — the linker only inserts the canonical `## Secrets` casing, but the back-reference check ignores section grouping (it's a body-wide wiki-link scan). A GM-authored `## secrets` heading with a back-reference link beneath it satisfies the check. New back-references the linker writes use `## Secrets`.
