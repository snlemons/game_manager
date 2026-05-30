# Tests

Automated tests for the `ttrpg-gm` plugin. This is the first test
infrastructure in the repo — the convention is being established here
in response to issue #8 (`/ingest` scaffolding test). Subsequent test
work should align with or deliberately diverge from these choices.

## Running

From the repo root:

    pytest tests/

Or a single test file:

    pytest tests/test_ingest_scaffolding.py -v

Requirements:

- **Python 3.9+** (the codebase targets a Claude Code runtime, but the
  tests run anywhere modern Python does).
- **`pytest`** — test runner.
- **`pyyaml`** — used to parse YAML frontmatter in scaffolded rule
  files. Already a standard install on the maintainer's machine.

No additional CI is wired up by this PR — that's a separate
infrastructure decision the maintainer should make once both initial
tests (issue #8 here, issue #9 for `/wrap-session` idempotency) have
landed and the pattern is settled.

## Conventions established here

- Tests live under `tests/` at the repo root.
- Fixtures live under `tests/fixtures/`. Each fixture's purpose is
  documented in `tests/fixtures/README.md`.
- `tests/conftest.py` exposes session-scoped `repo_root`,
  `templates_dir`, and `fixtures_dir` path fixtures so test files
  don't recompute paths.
- Tests use `tmp_path` for any filesystem mutation. They never write
  inside the repo.
- Tests assert **external behavior**: file paths written, frontmatter
  parseability, JSON validity, enum membership against the canonical
  set in `CONTEXT.md` / ADRs, git-repo shape. They never assert
  specific extractor prose, specific NPC counts, or LLM-phrased text.
- Domain vocabulary in test names and fixture content follows
  `CONTEXT.md` (Adventure, Reference note, Beat, Thread, Consequence,
  Campaign overview).

## Test files

### `test_ingest_scaffolding.py` — issue #8

Tests the deterministic Phase 1 scaffolder of `/ingest` (per
`skills/ingest/SKILL.md` Phase 1 and ADR-0013). The test embeds a
small **reference scaffolder** in Python — a faithful implementation
of SKILL.md Phase 1 Steps 1–3 — and runs it against a `tmp_path`
target using the real `templates/` directory.

What is asserted:

- All six templated files land at the documented paths (`CLAUDE.md`,
  `.claude/rules/sessions.md`, `.claude/rules/adventures.md`,
  `.claude/settings.json`, `campaign.md`, `.gitignore`).
- No `{{TOKEN}}` placeholder survives the substitution pass — every
  written file is fully resolved.
- The two `.claude/rules/*.md` files parse as YAML frontmatter +
  markdown body, both have a non-empty `paths:` glob list scoping
  them, and both have non-empty bodies.
- The Adventure rule file's documented status enum matches the
  canonical lifecycle set `{introduced, active, completed,
  abandoned}` from CONTEXT.md and ADR-0007 — by token presence in the
  body, not by prose matching.
- `.claude/settings.json` is valid JSON, contains a non-empty
  `permissions.allow` array, and has the campaign's absolute path
  baked into its matcher patterns (SKILL.md Phase 1 Step 2).
- `git init` produced a repo, the initial commit's subject is exactly
  `Scaffold campaign repo via ttrpg-gm /ingest`, that commit tracks
  the six scaffolded paths and nothing else, and `git status` is
  clean.

### Why a reference scaffolder, not a real `/ingest` invocation?

The full `/ingest` workflow has four phases. Only Phase 1 (scaffold)
is purely deterministic — Phases 2–4 (survey, per-doc extraction,
wrap-up) are LLM-driven. Invoking the LLM from a unit test would mean
either:

- A real model call per test run (slow, flaky, requires auth and
  network, non-hermetic), or
- A mocked model that just replays canned answers (which would not
  exercise the actual skill — the canned answers would be doing the
  asserting).

Phase 1 in isolation covers most of the issue #8 acceptance criteria
on its own (file structure, frontmatter validity, `git init` +
commit). For those criteria, a reference Python implementation of
Phase 1 plus structural assertions gives full, hermetic coverage. The
reference scaffolder is intentionally a thin near-translation of
SKILL.md Phase 1 Steps 1–3 — if the SKILL.md spec changes shape, the
reference scaffolder must change with it, and the test will catch any
silent drift between spec and behavior.

### Coverage gap (carried for a future test)

One acceptance criterion from issue #8 is **not** covered by this
test:

- **Dedup correctness**: a named recurring entity across two source
  docs should land as exactly one Reference-note file
  (`npcs/sera.md`) regardless of which doc is processed first.

This criterion lives entirely inside the LLM-driven extraction loop
(SKILL.md Phase 3 Steps 2 and 3b). It is not testable by a reference
implementation because the extraction step is not deterministic.

The fixture for this future test is already in place at
`tests/fixtures/ingest_inputs/` — two markdown docs, one
Adventure-shaped and one world-info-shaped, both naming **Sera** the
village blacksmith of Phandalin. When the maintainer adds an
LLM-driven integration test (e.g., a `claude --print`-based runner
that invokes `/ingest` headlessly against this fixture), the
assertions for it are straightforward: after the run, the campaign
target should contain exactly one `npcs/sera.md`, and that file's
body should mention Phandalin's forge.

The fixture is preserved here so the input contract is fixed now,
even though the integration test is deferred. Changes to the dedup
behavior in `/ingest` SKILL.md should drive matching updates to this
fixture (or an explicit decision that the existing fixture remains
representative).
