# Secret enumeration and queries

The campaign's `secrets/` directory is the canonical home for every Secret (per [ADR-0014](../docs/adr/0014-secrets-as-multi-container-lifecycle-objects.md)). When `/wrap-session`, `/prep-session`, or `/ingest` needs to ask "what Secrets does this campaign have / which ones touch this container / does this candidate already exist / is this `belongs_to:` list valid?", they walk `secrets/` directly. This reference is the canonical prose spec for the four query operations and the validator.

The reference Python at [`tests/test_secret_store.py`](../tests/test_secret_store.py) (shipped by issue #36) is a near-translation of the algorithms described here; the v0.1 convention is that the SKILL.md prose describes what the LLM walks at runtime and the reference Python pins the spec so prose and algorithm cannot silently drift. Changes here must keep that suite green and stay reflected in the prose.

The Secret schema (the fields the algorithms read from each file's frontmatter) lives in [`~/.claude/skills/ttrpg-gm/references/frontmatter-schemas.md`](./frontmatter-schemas.md). The slug normalization rule the dedup query uses lives in [`~/.claude/skills/ttrpg-gm/references/dedup-matching.md`](./dedup-matching.md). The non-ephemeral container set the validator enforces lives in CONTEXT.md ("Non-ephemeral container" entry).

## Four operations

This reference covers four operations:

- **`list_all`** — enumerate every Secret file under `secrets/`, parsed and slug-sorted.
- **`find_by_container`** — given a container path, return every Secret whose `belongs_to:` includes it. The "secrets owned by this container" query for `/prep-session` (Secret Push), `/wrap-session` (cross-context surfacing during extraction), and `/ingest` (cross-doc dedup).
- **`find_dedup_candidates`** — given a candidate Secret name, return existing Secrets that collide under the dedup normalization rule. The write-time dedup check `/wrap-session` and `/ingest` run before staging a new Secret.
- **`validate_belongs_to`** — given a candidate `belongs_to:` list, accept if at least one entry is a valid non-ephemeral container path; reject empty lists, all-ephemeral lists, and lists with unknown folder roots.

## Container set the validator enforces

Two folder-root sets, lifted from CONTEXT.md's "Non-ephemeral container" entry and ADR-0014:

- **Non-ephemeral folders (valid Secret containers):** `adventures`, `npcs`, `pcs`, `locations`, `factions`, `items`.
- **Ephemeral folders (rejected as Secret containers):** `threads`, `beats`, `consequences`, `sessions`, `.ttrpg-staging`.

A folder root not in either set (e.g., `random/foo`, or a typo like `npc/maren.md` missing the `s`) is treated as **invalid** — neither ephemeral nor non-ephemeral. The validator rejects with a message distinguishing the cases (so a GM hand-editing a `belongs_to:` typo gets a clear diagnostic).

## `list_all` — full enumeration

**Input:** a campaign root.

**Behavior:**

1. If `<campaign>/secrets/` does not exist, return an empty list. (A campaign without any Secrets is a valid state.)
2. Walk the directory contents in slug-sorted order (sort by filename). The deterministic ordering matters for `find_by_container` and `find_dedup_candidates`, both of which iterate `list_all`'s output — and for `/prep-session` Brief content stability.
3. For each entry:
   - Skip if it is not a file or does not end in `.md`.
   - Read the file as UTF-8.
   - Split into frontmatter (parsed as YAML) and body. If parsing fails (the file does not start with `---\n`, has no closing `\n---\n`, or YAML is malformed), **skip the file silently** — the enumeration treats it as "not a Secret." Surfacing malformed-Secret cases is the lint's job (or the agent's separate health check), not this query's responsibility.
4. Return a list of Secret records, each carrying:
   - `slug` — the filename stem (`maren-is-the-spy` for `secrets/maren-is-the-spy.md`).
   - `path` — the absolute path to the file.
   - `frontmatter` — the parsed YAML mapping.
   - `body` — the body text after the closing frontmatter delimiter.
   - convenience accessors for `status`, `belongs_to`, `revealed_by` (each returning the frontmatter value with a safe default — `""` for status, `[]` for the list fields).

**Determinism.** Two calls in succession against the same `secrets/` tree return the same list in the same order. Filesystem iteration order is sorted explicitly; the LLM walking `ls secrets/` at runtime must sort the output before iterating.

## `find_by_container` — reverse lookup of `belongs_to:`

**Input:** a campaign root and a container path string (e.g., `"npcs/maren.md"`, `"adventures/the-prism/"`).

**Behavior:**

1. **Normalize the query path through the alias map.** Per [ADR-0017](../docs/adr/0017-npc-aliases-via-frontmatter-and-piped-links.md), Reference-note containers may carry a frontmatter `aliases:` list of other names the entity goes by. Before matching, the query path is canonicalized:
   - If the path resolves directly to an existing canonical file (the file at `container_path` exists and its frontmatter does not redirect), use `container_path` as-is.
   - If the path does **not** resolve to an existing file (e.g., the caller queried `npcs/the-shadow.md` but no such file exists), scan the relevant kind folder for a Reference note whose normalized `aliases:` (per the slug rule in `~/.claude/skills/ttrpg-gm/references/dedup-matching.md`) includes the query path's slug. If exactly one canonical claims the alias, substitute that canonical's path as the matching target. If zero or more than one canonical claims the alias, fall back to the literal `container_path` (matching nothing or the literal entry as it appears).
   - Adventure containers (directory-form paths like `adventures/the-prism/`) and PC files do not currently use `aliases:` for canonicalization; the field is available on every Reference-note kind but the v0.2 cut targets NPCs / Locations / Factions / Items.
2. Call `list_all` to get the enumeration.
3. For each Secret, check whether the canonicalized query path is **exact-string-equal** to any entry in the Secret's `belongs_to:` list.
4. Return the matching Secrets in `list_all` order (slug-sorted).

**Exact-string matching after canonicalization.** Inside the loop, matching remains literal:

- Trailing slashes are preserved (`adventures/the-prism/` is distinct from `adventures/the-prism`). The canonical form for Adventure containers is the directory-form with trailing slash; querying without the trailing slash returns zero hits even if the canonical form exists in `belongs_to:`.
- Case-sensitive (`npcs/Maren.md` does not match `npcs/maren.md`).

Predictability wins over convenience. The bidi-link linter handles symmetry repair; this query just answers "is anything claiming to belong to this canonical path?" The runtime caller (the LLM) is responsible for passing a reasonable form of the container path; the alias-canonicalization step is the one accommodation, so that *"what Secrets touch The Shadow?"* gives the same answer as *"what Secrets touch Maren?"* when both refer to the same NPC.

**Why canonicalize at the query, not at write time.** Secrets' `belongs_to:` is authored by the GM (with agent proposals at extraction time); the field's source of truth is the Secret file. Silently rewriting `belongs_to:` during a read query would mask drift (a Secret authored against the wrong slug should surface at the bidi-link linter, not be quietly canonicalized away). Normalizing at the query keeps the Secret file's content stable and routes the corrective write through the lint pass per `~/.claude/skills/ttrpg-gm/references/bidi-link-maintenance.md` instead.

**Non-existence is fine.** `find_by_container` does not check that the container file exists — that's the linter's job. A query against `npcs/does-not-exist.md` that doesn't resolve via aliases returns an empty list (nothing claims it), not an error.

## `find_dedup_candidates` — write-time dedup scan

**Input:** a campaign root and a candidate Secret name (the proposed H1 / canonical-name string, or a candidate slug).

**Behavior:**

1. Normalize the candidate name per the slug normalization rule in `~/.claude/skills/ttrpg-gm/references/dedup-matching.md` (lowercase, strip `.md`, ASCII-fold accents, strip leading "the ", collapse runs of non-alphanumerics to single hyphens, trim).
2. Call `list_all` to enumerate every Secret.
3. For each Secret, check **two** match conditions:
   - **Slug match.** Normalize the Secret's filename slug; if it equals the normalized candidate, it's a hit.
   - **First-heading-title match.** Find the first `# <text>` line in the Secret's body; normalize it; if it equals the normalized candidate, it's also a hit.
4. Return the matching Secrets in `list_all` order. A Secret matching by either condition counts once (don't double-add).

**Returns a list, not an Optional.** Even when only one match is expected in a healthy campaign, the return type is a list so the LLM can surface multi-hit collisions to the GM. If two Secrets ever collide on normalized form (shouldn't happen but can), both surface — the GM decides which is canonical.

**Why filename-slug + first-heading match.** Same reasoning as the wider dedup rule in `~/.claude/skills/ttrpg-gm/references/dedup-matching.md`: the first heading is the file's canonical name as the GM sees it; a candidate that name-matches either the slug or the H1 is the same Secret. Matching only the slug would miss the case where a GM hand-renamed a Secret's H1 but the filename is stale.

**Scoped to `secrets/` only.** Per ADR-0014's "Dedup is a `secrets/`-only scan," this query never walks Threads, Consequences, Beats, or Reference notes — Secrets dedup against Secrets. The other lifecycle objects have their own dedup paths (`~/.claude/skills/ttrpg-gm/references/dedup-matching.md` scoped to each kind's folder).

**Classification is the LLM's job.** This query just surfaces matches. The LLM (per `~/.claude/skills/ttrpg-gm/references/dedup-matching.md` "Match classification" and `~/.claude/skills/ttrpg-gm/references/secret-extraction.md`'s dedup section) decides whether a hit is a confident UPDATE (same Secret, append `belongs_to:` or merge body) or an ASK (similar name, possibly distinct Secret — surface the *"merge, separate, or rename?"* prompt to the GM).

## `validate_belongs_to` — invariant enforcement

**Input:** a list of container path strings, the candidate `belongs_to:` for a Secret being written.

**Behavior:**

1. Strip whitespace from each entry; drop empty / whitespace-only entries.
2. If the cleaned list is empty, **reject** with a message naming the ADR: *"belongs_to: is empty; every Secret must belong to at least one non-ephemeral container (ADR-0014)."*
3. For each cleaned entry, look at the leading folder segment (everything before the first `/`).
   - If the folder root is in the **non-ephemeral set**, the entry is valid.
   - If the folder root is in the **ephemeral set**, the entry is ephemeral.
   - Otherwise, the entry is invalid (unknown folder root).
4. **Accept** if at least one entry is valid. (Ephemeral or invalid entries co-existing alongside a valid one don't block acceptance; the SKILL.md prose may warn the GM about ephemeral entries, but the validator doesn't reject the list outright.)
5. **Reject** with distinguished messages otherwise:
   - All-ephemeral list (entries are all ephemeral, no invalid ones): *"belongs_to: contains only ephemeral container paths (...); Secrets must belong to a non-ephemeral container per ADR-0014."*
   - Otherwise (invalid entries, possibly mixed with ephemeral): *"belongs_to: contains no valid non-ephemeral container paths (invalid entries: ..., ephemeral: ...)."*

**Path form.** Entries are expected in POSIX form with forward slashes. Trailing slashes are tolerated (Adventure containers are directory-form: `adventures/the-prism/`). The validator doesn't check that the container *file* exists — that's the linter's job (`~/.claude/skills/ttrpg-gm/references/bidi-link-maintenance.md`). The validator only checks that the *path shape* is acceptable.

**Why reject unknown folder roots.** A typo like `npc/maren.md` (missing the `s`) would silently slip through if the validator only checked for ephemeral entries; downstream the bidi-link maintenance would fail with a less-clear "file not found" error. Rejecting unknown roots at the validator gives a clearer diagnostic at the right moment.

## When to invoke each operation

- **`list_all`** — any time a skill needs the full Secret set. `/prep-session` reads it for the Secret Push question's predicate (which Secrets are `partially-revealed`, which are `hidden` for an active Adventure). `/wrap-session` reads it during extraction to check candidate names. `/ingest` Phase 3 reads it during cross-doc dedup.
- **`find_by_container`** — `/prep-session` per-container surfacing ("what Secrets touch the NPC the party is about to meet?"). `/wrap-session` cross-context surfacing during extraction ("the notes mention Maren — what Secrets does she own that might be relevant?"). `/ingest` when a source doc introduces a Secret claiming a container another doc already wrote — confirm the existing Secrets on that container so the GM sees the full set when approving the new one.
- **`find_dedup_candidates`** — write-time, every time `/wrap-session` Pass (Secret extraction) or `/ingest` Phase 3 proposes a new Secret. Before staging the Secret file, run this query; route results to the dedup classification per `~/.claude/skills/ttrpg-gm/references/secret-extraction.md`.
- **`validate_belongs_to`** — write-time, every time a Secret's `belongs_to:` is set or modified. Run before staging the Secret file (catches empty / all-ephemeral / typo cases before they reach the bidi-link maintenance pass). The wrap-session approval step also runs this on the GM-edited final `belongs_to:` to catch hand-edit damage before promotion.

## What this query layer does not handle

- **Mutation.** All four operations are read-only. Writing Secrets is `/wrap-session`'s and `/ingest`'s job, gated by the staging pattern. The store enumerates and queries; the skills mutate.
- **Container-side back-references.** Whether a container actually has a `## Secrets` section linking back to a Secret claimed in `belongs_to:` is the bidi-link linter's question, not this query's. `find_by_container` answers "what claims this container?" not "what does the container link back to?"
- **Status-based filtering.** "All `partially-revealed` Secrets" or "all Secrets with empty `revealed_by:`" is per-skill filter logic on top of `list_all`. The store doesn't pre-bucket; callers iterate.
- **Malformed Secret surfacing.** `list_all` skips unparseable Secret files silently. Surfacing malformed Secrets ("hey, `secrets/foo.md` has broken YAML, you should fix it") is a separate health-check concern — either the bidi-link linter's job (it walks the same tree and can flag parse failures) or a future preflight check.
- **Atlas content.** v0.1 is single-repo (ADR-0006); the store walks one campaign root only. Cross-campaign Secret enumeration is out of scope.
