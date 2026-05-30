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
