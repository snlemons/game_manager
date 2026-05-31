# Test fixtures

## `ingest_inputs/`

Two markdown source docs in the shape `/ingest` consumes:

- **`lost-mines.md`** — Adventure-shaped (a story arc the party would
  run), with embedded Reference notes, Threads, Beats, and Consequences
  per the domain vocabulary in `CONTEXT.md`.
- **`phandalin-gazetteer.md`** — World-info-shaped (Reference-note dump,
  no Adventure structure).

**Sera** appears in both docs as the same village blacksmith of
Phandalin — the named recurring entity that exercises cross-doc dedup
per `/ingest` SKILL.md Step 3b. A correctly behaving extraction should
produce exactly one `npcs/sera.md` regardless of which doc is processed
first.

This fixture is the input contract for `/ingest`. It is consumed by
`tests/test_ingest_scaffolding.py` (which today tests only the
deterministic scaffolder phase against this same fixture's target
directory; the dedup criterion documented above is held for a future
LLM-driven integration test).

## `secrets/`

A small post-ingest campaign whose `secrets/` directory exercises the
Secret schema, multi-container `belongs_to`, and bidirectional
container linking from [ADR-0014](../../docs/adr/0014-secrets-as-multi-container-lifecycle-objects.md).
Consumed by `tests/test_secret_store.py` and `tests/test_bidi_link.py`.

Four Secrets:

- **`secrets/maren-is-the-spy.md`** — multi-container Secret
  belonging to `npcs/maren.md` AND `adventures/the-prism/`. Status:
  `hidden`. Exercises the multi-container query path.
- **`secrets/prism-core-is-cursed.md`** — multi-container Secret
  belonging to `adventures/the-prism/` AND `items/the-prism-core.md`.
  Status: `partially-revealed` (one Clue Beat has landed).
- **`secrets/vault-key-in-temple.md`** — single-container Secret
  belonging to `locations/old-temple.md`. Status: `hidden`.
- **`secrets/jhera-survived.md`** — multi-container Secret belonging
  to `npcs/jhera.md` AND `factions/silent-court.md`. Status:
  `revealed`. **Intentional lint case:** `npcs/jhera.md` is *missing*
  the `## Secrets` back-reference — the bidi linker must flag this.

Container files:

- **`npcs/maren.md`** — correctly back-links to its Secret.
- **`npcs/jhera.md`** — missing `## Secrets` section (lint case:
  missing back-reference).
- **`npcs/orin.md`** — contains an **orphan** wiki-link to
  `secrets/orin-betrayed-us` (no such Secret file exists). Lint case:
  orphan link.
- **`npcs/halric.md`** — unrelated NPC with no Secret. Confirms
  `find_by_container` does not false-positive on containers that
  appear nowhere in any `belongs_to`.
- **`adventures/the-prism/adventure.md`** — correctly back-links to
  both its Secrets.
- **`locations/old-temple.md`**, **`items/the-prism-core.md`**,
  **`factions/silent-court.md`** — each correctly back-links to its
  Secret(s).

The fixture is structurally a campaign repo but does not store a
`.claude/` subtree — these tests don't need scaffolded settings or
rules, only the lifecycle-object files the SecretStore and
BidiLinkManager reference impls walk.
