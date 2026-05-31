# Deterministic spec items live in `lib/` as Python helpers invoked via Bash

The plugin establishes a **`lib/` directory at the repo root** holding Python helper scripts that encode deterministic spec items. Skills invoke helpers via Bash; SKILL.md prose tells the LLM when to call them and how to interpret their output. This formalizes the D-style optimization tracked in [#24](https://github.com/snlemons/game_manager/issues/24) and resolves the v0.1 / v0.2 asymmetry that arose when v0.2 introduced new deterministic concerns (Secret enumeration, bidirectional linking) on top of v0.1 spec items that still lived as SKILL.md prose with test-only reference Python.

## What goes in `lib/`

A spec item earns a helper when **all three** of these are true (the criteria from [#24](https://github.com/snlemons/game_manager/issues/24)):

1. **The logic is deterministic** — no LLM judgment in the loop.
2. **It runs many times per session or per workflow** — savings compound.
3. **The reference doc currently has to lean on LLM care to get right** — a deterministic helper removes a class of bugs.

What stays in SKILL.md prose: anything where LLM judgment is in the loop — extraction heuristics, prose composition, ambiguity clarification, kind classification at extraction time, question phrasing, response handling. Predicate evaluation with judgment-laden terms (e.g., "borderline relevance score") also stays in prose, with the predicates themselves living as structured data in `references/` so a future helper can absorb them when the judgment terms harden.

## Initial promotion set (v0.2)

Seven helpers ship in v0.2 — the v0.1 candidates from [#24](https://github.com/snlemons/game_manager/issues/24) plus two new ones surfaced by the Secret architecture ([ADR-0014](./0014-secrets-as-multi-container-lifecycle-objects.md)):

| Helper | Origin | Encodes |
|---|---|---|
| `lib/frontmatter.py` | v0.1 promotion | Schema validation per `references/frontmatter-schemas.md`. |
| `lib/dedup.py` | v0.1 promotion (Secret-extended) | Slug normalization + near-match detection per `references/dedup-matching.md`. |
| `lib/backlinks.py` | v0.1 promotion | `[[wiki link]]` graph inversion across the campaign repo. |
| `lib/campaign_overview.py` | v0.1 promotion | `campaign.md` rendering per `references/campaign-overview-composer.md`. |
| `lib/preflight.py` | v0.1 promotion | Settings path check per `references/preflight.md`. |
| `lib/secret_store.py` | v0.2 | Secret enumeration, `belongs_to` validation, container backlink lookup. |
| `lib/bidi_link.py` | v0.2 | Symmetric `## Secrets` section maintenance; orphan lint. |

## Language

**Python 3.9+.** Already a test-time dependency; v0.2 makes it a runtime dependency. README's Install section documents this. Bash + standard CLI tools (`yq`, `jq`, `grep`) is acceptable for pure file traversal that doesn't touch YAML, but Python is the default whenever structured data is involved.

No third-party dependencies beyond `pyyaml`. New deps require an ADR amendment to justify the added install surface.

## Calling convention

Skills invoke helpers via the Bash tool. Each helper:

- Is executable as `python3 lib/<name>.py <args...>`.
- Exits non-zero on error with the error message on stderr; exits zero on success with structured output (JSON or newline-delimited paths) on stdout.
- Takes the campaign root as its first positional arg (so the helper can resolve all paths relative to it without inheriting cwd).
- Documents its CLI surface in a module docstring; SKILL.md authors read the docstring, not the source.

SKILL.md tells the LLM the helper's purpose and the expected output shape. The LLM is responsible for invoking the helper, checking the exit status, parsing the output, and surfacing errors verbatim to the GM if something fails. The LLM does *not* improvise around helper failures — a failing helper is a real problem the GM needs to know about.

## Testing

Tests bind directly to the helpers in `lib/` rather than re-encoding the spec as a separate "near-translation" in `tests/`. Single source of truth; no drift risk.

- Each helper has a `tests/test_<name>.py` file.
- Tests use the existing fixture pattern (`tests/fixtures/<feature_name>/`) and `tmp_path` for mutations.
- Tests assert external behavior (output shape, file contents, exit codes) — not internal helper organization.
- The existing v0.1 reference impls in `tests/test_ingest_scaffolding.py` and `tests/test_wrap_session_idempotency.py` get *replaced* by direct calls into the promoted helpers; the assertions stay, the impl-under-test moves.

End-to-end LLM-driven skill invocation remains intentionally untested per the existing convention (`tests/README.md` "Coverage gaps"). The helpers cover the deterministic phases; LLM compliance with SKILL.md prose remains a dogfooding concern.

## Considered alternatives

- **Stay test-only (all helpers as reference Python in `tests/`, SKILL.md prose drives runtime).** Rejected for v0.2 because the new Secret architecture has high enough query/write frequency that prose-only runtime would be brittle and token-expensive. Specifically, `bidi_link` as prose requires the LLM to do N+1 idempotent file edits per Secret write — a realistic failure mode.
- **Promote only v0.2's new helpers, leave v0.1 candidates as prose.** Rejected as creating asymmetric runtime mechanisms — Reference note dedup via prose, Secret dedup via helper, same shape of work, different mechanism. Inconsistent mental model for SKILL.md authors.
- **Bash + standard CLI tools, no Python.** Rejected for the structured-data helpers; YAML and JSON manipulation in pure shell is awkward and error-prone. Acceptable for `lib/backlinks.py` if pure grep suffices, but Python is the default for cross-helper consistency.
- **Separate `helpers/` repo, vendored or pip-installed.** Rejected as overengineering for v0.2's scale. `lib/` colocated with the plugin keeps the dependency surface inside the plugin's git tag.

## Consequences

- New top-level `lib/` directory with the seven helpers above.
- `pyyaml` and Python 3.9+ become runtime dependencies (previously test-time only). README's Install section updates to call this out.
- The existing reference Python in `tests/test_ingest_scaffolding.py` and `tests/test_wrap_session_idempotency.py` is extracted to the corresponding `lib/` helpers; the tests rebind their imports.
- New helper convention: each helper has a CLI surface documented in its module docstring; SKILL.md authors read the docstring, not the source.
- `references/` becomes the *spec home* (markdown describing what each helper does, what it asserts, what's in scope) while `lib/` becomes the *implementation home*. This matches the existing pattern where `references/` is the canonical spec and `tests/` historically held the executable mirror.
- [#24](https://github.com/snlemons/game_manager/issues/24) is resolved by v0.2 — closing comment should reference this ADR and list the initial promotion set.
- Future helpers added under this convention need no new ADR if they fit the three criteria; the convention is established here. ADR amendment only required for new third-party dependencies, new language additions, or a calling-convention shift.
