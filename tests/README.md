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
    pytest tests/test_wrap_session_idempotency.py -v

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
- Fixtures live under `tests/fixtures/<feature_name>/`. Each fixture's
  purpose is documented in `tests/fixtures/README.md` where applicable.
- `tests/conftest.py` exposes session-scoped `repo_root`,
  `templates_dir`, and `fixtures_dir` path fixtures so test files
  don't recompute paths.
- Skill-specific reference impls live inline in `tests/test_*.py`
  alongside the assertions that consume them. Anything imported across
  test files lives in `tests/_helpers.py` (issue #112) — the
  underscore prefix tells pytest "not a test file". No `test_*.py`
  file imports from another `test_*.py` file.
- Tests use `tmp_path` for any filesystem mutation. They never write
  inside the repo.
- Tests assert **external behavior**: file paths written, frontmatter
  parseability, JSON validity, enum membership against the canonical
  set in `CONTEXT.md` / ADRs, git-repo shape. They never assert
  specific extractor prose, specific NPC counts, or LLM-phrased text.
- Per-test data shared across cases lives in plain `for candidate in
  (...)` loops inside a single `def test_*`, preserving per-case
  diagnostic context through assertion-message f-strings. Reserve
  `@pytest.mark.parametrize` for cases the suite genuinely treats as
  independent tests.
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

### `test_wrap_session_idempotency.py` — issue #9

Verifies the **external behavior** of `/wrap-session` against a
fixture campaign repo, against the three acceptance criteria from
issue #9:

1. **No duplicates on re-run.** Re-running `/wrap-session` against
   the same `notes.md` after corrections does not create new files
   for Threads, Consequences, Beats, or Reference notes that already
   exist under a matching name. Tested by exercising the dedup
   normalization spec from `skills/wrap-session/SKILL.md` Step 2
   "Dedup" against the fixture's existing lifecycle objects.
2. **Confirm-before-overwrite of an existing `log.md`.** The re-run
   guard (`skills/wrap-session/SKILL.md` Step 1 "Re-run guard") is
   exercised by simulating the staging-then-cancel path: a proposed
   `log.md` is staged under `.ttrpg-staging/wrap/` and then the
   staging directory is removed (the "cancel" outcome). The existing
   `log.md` must be byte-identical before and after.
3. **Deterministic `campaign.md` regeneration.** Composing
   `campaign.md` from identical campaign state twice produces
   byte-identical content. Tested via a reference composer that
   mirrors the section ordering specified in ADR-0007 and SKILL.md
   Step 5 #7.

The fixture under `tests/fixtures/wrap_session_idempotency/` is a
small post-ingest campaign repo with a populated `notes.md` in
`sessions/2026-05-29-session-5/`. It stores its `.claude/` subtree
under `dot_claude/`; the test harness renames that on copy into
`tmp_path` to escape harness sandboxing on nested `.claude/` paths.
Future tests handling scaffolded `.claude/` content can reuse the
same trick.

### Why reference implementations, not real skill invocations?

Both `/ingest` and `/wrap-session` are multi-phase LLM-driven skills.
Only some phases (e.g., `/ingest` Phase 1 scaffold, `/wrap-session`
dedup normalization, `/wrap-session` `campaign.md` composition) are
purely deterministic — the rest are LLM-driven. Invoking the LLM
from a unit test would mean either:

- A real model call per test run (slow, flaky, requires auth and
  network, non-hermetic), or
- A mocked model that just replays canned answers (which would not
  exercise the actual skill — the canned answers would be doing the
  asserting).

For the deterministic phases, reference Python implementations plus
structural assertions give full, hermetic coverage. Each reference
implementation is intentionally a thin near-translation of the
relevant `SKILL.md` step — if the spec changes shape, the reference
implementation must change with it, and the test will catch any
silent drift between spec and behavior.

## Coverage gaps (carried for future tests)

**From issue #8:** Dedup correctness — a named recurring entity
across two source docs should land as exactly one Reference-note file
(`npcs/sera.md`) regardless of which doc is processed first. This
lives in the LLM-driven extraction loop (SKILL.md Phase 3 Steps 2 and
3b) and is not testable by a reference implementation. The fixture
for this future test is in place at `tests/fixtures/ingest_inputs/` —
two markdown docs both naming **Sera** the village blacksmith of
Phandalin. When an LLM-driven integration test gets added (e.g., a
`claude --print`-based runner), the assertions are straightforward.

**From issue #9:** End-to-end LLM-driven `/wrap-session` invocation
isn't covered. The current suite tests the *specification* the skill
encodes — dedup normalization, the staging-then-cancel invariant,
the regeneration ordering — not the LLM agent's compliance with that
specification. A genuine end-to-end test would need a reliably-
installed Claude Code CLI, canned approval responses for the GM
prompts, and tolerance for LLM non-determinism in extracted prose.
