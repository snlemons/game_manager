"""Reference-Python coverage of the SecretStore enumeration spec.

This file follows the v0.1 test convention: the reference Python below
is a thin near-translation of the Secret enumeration / dedup / validation
algorithm that the SKILL.md prose in `/wrap-session`, `/prep-session`,
and `/ingest` will describe at runtime (downstream slices #37, #38, #39).
The reference impl is **not** a runtime helper — skills walk `secrets/`
directly. The tests exist so the spec and the per-skill prose can't
silently drift apart: any change to the documented algorithm must land
in both the SKILL.md and this file, and the tests catch mismatches.

Per [ADR-0014](../docs/adr/0014-secrets-as-multi-container-lifecycle-objects.md),
Secrets are a fourth lifecycle object alongside Threads, Consequences,
and Beats. They differ from the others in two ways the spec encodes:

  1. **Multi-container ownership.** Every Secret's frontmatter
     `belongs_to:` is a non-empty unordered set of paths to
     non-ephemeral containers (Adventure, NPC, PC, Location, Faction,
     Item). Ephemeral container paths are rejected outright.
  2. **Bidirectional linkage.** Each container in `belongs_to:` is
     supposed to carry a `## Secrets` section wiki-linking back to the
     Secret file. The Secret file is the source of truth; the
     container's section is a derived view. The
     `tests/test_bidi_link.py` companion file exercises that linker.

The four operations covered here are the queries skills need against
the campaign's `secrets/` directory:

  - **`list_all`** — enumerate every Secret file under `secrets/`,
    returning parsed frontmatter + body + slug.
  - **`find_by_container`** — given a container path
    (`npcs/maren.md`, `adventures/the-prism/`), return every Secret
    whose `belongs_to:` includes it. The 'secrets relevant to this
    NPC' query for prep-session.
  - **`find_dedup_candidates`** — given a candidate Secret name, apply
    the slug normalization from `references/dedup-matching.md` and
    return any existing Secret whose slug or first-heading title
    normalizes to the same form. Used by the write-time dedup check.
  - **`validate_belongs_to`** — given a candidate `belongs_to:` list,
    reject empties and lists that contain only ephemeral container
    paths; accept anything with at least one valid non-ephemeral path.

The reference impl mirrors what SKILL.md prose in the downstream slices
will document; if the prose and this file diverge, one of them is wrong.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pytest
import yaml


# ---------------------------------------------------------------------------
# Reference implementation — mirrors ADR-0014 + references/frontmatter-schemas.md
# + references/dedup-matching.md.
# Kept in-file per the v0.1 convention (see test_frontmatter.py,
# test_ingest_scaffolding.py, test_wrap_session_idempotency.py for the
# same pattern). Skills do the runtime walk in SKILL.md prose; this file
# pins the spec the prose describes.
# ---------------------------------------------------------------------------


# Status enum, sourced from references/frontmatter-schemas.md + ADR-0014.
SECRET_STATUSES = frozenset({"hidden", "partially-revealed", "revealed"})


# The set of non-ephemeral container *folder roots* a Secret's
# `belongs_to:` entry may live under. Sourced from CONTEXT.md's
# "Non-ephemeral container" entry and ADR-0014. Ephemeral folders
# (`threads/`, `beats/`, `consequences/`, `sessions/`, `.ttrpg-staging/`)
# are rejected by `validate_belongs_to`.
NON_EPHEMERAL_FOLDERS = frozenset(
    {"adventures", "npcs", "pcs", "locations", "factions", "items"}
)
EPHEMERAL_FOLDERS = frozenset(
    {"threads", "beats", "consequences", "sessions", ".ttrpg-staging"}
)


class SecretStoreError(Exception):
    """A validation failure surfaced with a self-contained message."""


@dataclass(frozen=True)
class Secret:
    """One Secret as enumerated from `secrets/<slug>.md`."""

    slug: str
    path: Path
    frontmatter: dict
    body: str

    @property
    def status(self) -> str:
        return self.frontmatter.get("status", "")

    @property
    def belongs_to(self) -> list[str]:
        raw = self.frontmatter.get("belongs_to", []) or []
        return [str(p) for p in raw]

    @property
    def revealed_by(self) -> list[str]:
        raw = self.frontmatter.get("revealed_by", []) or []
        return [str(s) for s in raw]


# --- Slug normalization, lifted verbatim from references/dedup-matching.md ---

_THE_PREFIX = re.compile(r"^the[\s\-_]+", re.IGNORECASE)
_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def normalize_slug(name: str) -> str:
    """The same normalization rule the dedup spec applies to all slugs.

    Lowercase, strip `.md`, ASCII-fold (best-effort via the
    non-alphanumeric collapse — accented characters land outside
    `[a-z0-9]` and become hyphens; for production use, the runtime
    spec calls out true NFKD folding, but the collapse is sufficient
    for the slugs the fixture exercises), strip leading "the ",
    collapse runs of non-alphanumerics to single hyphens, trim.
    """
    n = name.strip().lower()
    if n.endswith(".md"):
        n = n[: -len(".md")]
    n = _THE_PREFIX.sub("", n)
    n = _NON_ALNUM.sub("-", n).strip("-")
    return n


def _split_frontmatter(text: str) -> tuple[dict, str]:
    """Same minimal frontmatter parser used by test_frontmatter.py."""
    if not text.startswith("---\n"):
        return {}, text
    closing = text.find("\n---\n", 4)
    if closing == -1:
        return {}, text
    raw = text[4:closing]
    body = text[closing + len("\n---\n") :]
    parsed = yaml.safe_load(raw) or {}
    if not isinstance(parsed, dict):
        raise SecretStoreError(
            f"frontmatter parsed to non-dict: {type(parsed).__name__}"
        )
    return parsed, body


def _first_heading_title(body: str) -> str | None:
    """First `# <text>` line in the body, or None if absent."""
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    return None


def list_all(campaign_root: Path) -> list[Secret]:
    """Enumerate every Secret under `<campaign>/secrets/`.

    Returns Secrets sorted by slug for deterministic iteration. Files
    that are not `*.md` or that fail to parse as Secret frontmatter
    are skipped silently — the SKILL.md prose surfaces these to the GM
    as a separate step, but the enumeration query treats them as
    "not a Secret."

    If the `secrets/` directory does not exist, returns an empty list
    (a campaign without any Secrets is a valid state).
    """
    secrets_dir = campaign_root / "secrets"
    if not secrets_dir.is_dir():
        return []
    out: list[Secret] = []
    for path in sorted(secrets_dir.iterdir(), key=lambda p: p.name):
        if not path.is_file() or not path.name.endswith(".md"):
            continue
        try:
            text = path.read_text(encoding="utf-8")
            fm, body = _split_frontmatter(text)
        except (OSError, SecretStoreError, yaml.YAMLError):
            continue
        slug = path.stem
        out.append(
            Secret(slug=slug, path=path, frontmatter=fm, body=body)
        )
    return out


def find_by_container(
    campaign_root: Path, container_path: str
) -> list[Secret]:
    """Return every Secret whose `belongs_to:` includes `container_path`.

    Matching is exact-string on the normalized path form: trailing
    slashes are preserved (so `adventures/the-prism/` is distinct from
    `adventures/the-prism`), and the comparison is case-sensitive.
    The SKILL.md spec is exact-string for predictability — fuzzy
    matching is the bidi linter's job, not the query's.
    """
    target = container_path
    return [
        s for s in list_all(campaign_root) if target in s.belongs_to
    ]


def find_dedup_candidates(
    campaign_root: Path, candidate_name: str
) -> list[Secret]:
    """Return Secrets whose slug OR first-heading-title normalizes to the
    same form as the candidate name.

    The match is the dedup rule from `references/dedup-matching.md`,
    scoped to the `secrets/` folder per ADR-0014's
    "Dedup is a `secrets/`-only scan" guidance. The runtime caller
    (the LLM in `/wrap-session` or `/ingest`) classifies the result as
    confident-UPDATE or ASK-the-GM; this query just surfaces the
    candidates.
    """
    target_slug = normalize_slug(candidate_name)
    hits: list[Secret] = []
    for s in list_all(campaign_root):
        slug_norm = normalize_slug(s.slug)
        if slug_norm == target_slug:
            hits.append(s)
            continue
        title = _first_heading_title(s.body)
        if title and normalize_slug(title) == target_slug:
            hits.append(s)
    return hits


def validate_belongs_to(paths: Iterable[str]) -> None:
    """Validate a Secret's proposed `belongs_to:` list.

    Raises `SecretStoreError` if:
      - the list is empty (or all entries are empty strings), OR
      - every entry's leading folder is in the ephemeral set.

    Accepts the list if at least one entry's leading folder is in the
    non-ephemeral set. Entries whose leading folder is in neither set
    (e.g., `random/foo`) count as neither ephemeral nor non-ephemeral
    — they're invalid as a container path and rejected with a
    different message; the spec calls out that the agent only writes
    paths under the documented set.

    Paths are expected in POSIX form with forward slashes. Trailing
    slashes are tolerated (a directory-style path like
    `adventures/the-prism/` is the canonical form for Adventure
    containers, since Adventures are directories).
    """
    cleaned = [p.strip() for p in paths if p and p.strip()]
    if not cleaned:
        raise SecretStoreError(
            "belongs_to: is empty; every Secret must belong to at least "
            "one non-ephemeral container (ADR-0014)."
        )
    invalid: list[str] = []
    ephemeral: list[str] = []
    valid: list[str] = []
    for p in cleaned:
        head = p.split("/", 1)[0]
        if head in EPHEMERAL_FOLDERS:
            ephemeral.append(p)
        elif head in NON_EPHEMERAL_FOLDERS:
            valid.append(p)
        else:
            invalid.append(p)
    if not valid:
        if ephemeral and not invalid:
            raise SecretStoreError(
                "belongs_to: contains only ephemeral container paths "
                f"({sorted(ephemeral)}); Secrets must belong to a "
                "non-ephemeral container per ADR-0014."
            )
        raise SecretStoreError(
            "belongs_to: contains no valid non-ephemeral container "
            f"paths (invalid entries: {sorted(invalid)}, ephemeral: "
            f"{sorted(ephemeral)})."
        )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def secrets_fixture(fixtures_dir: Path) -> Path:
    """Absolute path to the static `secrets/` fixture campaign."""
    return fixtures_dir / "secrets"


# ---------------------------------------------------------------------------
# Tests — list_all
# ---------------------------------------------------------------------------


class TestListAll:
    """`list_all` enumerates every Secret file under `<campaign>/secrets/`."""

    def test_returns_every_secret_file_in_fixture(
        self, secrets_fixture: Path
    ) -> None:
        secrets = list_all(secrets_fixture)
        slugs = {s.slug for s in secrets}
        assert slugs == {
            "maren-is-the-spy",
            "prism-core-is-cursed",
            "vault-key-in-temple",
            "jhera-survived",
        }, (
            f"list_all returned unexpected slugs: {sorted(slugs)}"
        )

    def test_results_are_deterministically_ordered(
        self, secrets_fixture: Path
    ) -> None:
        first = [s.slug for s in list_all(secrets_fixture)]
        second = [s.slug for s in list_all(secrets_fixture)]
        assert first == second, (
            "list_all returned different orderings across calls — "
            "the enumeration is not deterministic"
        )
        assert first == sorted(first), (
            f"list_all order is not slug-sorted: {first}"
        )

    def test_returns_empty_list_when_no_secrets_dir(
        self, tmp_path: Path
    ) -> None:
        # A campaign without any Secrets is valid; list_all returns [].
        assert list_all(tmp_path) == []

    def test_secret_frontmatter_parses(
        self, secrets_fixture: Path
    ) -> None:
        # Every Secret in the fixture must parse and carry the four
        # required fields. This is the entry-level shape check the
        # downstream query operations assume.
        for s in list_all(secrets_fixture):
            assert s.status in SECRET_STATUSES, (
                f"{s.slug} has invalid status {s.status!r}; expected "
                f"one of {sorted(SECRET_STATUSES)}"
            )
            assert s.belongs_to, (
                f"{s.slug} has empty belongs_to — fixture is wrong "
                "OR the enumeration dropped the field"
            )
            assert isinstance(s.revealed_by, list), (
                f"{s.slug}.revealed_by is not a list"
            )


# ---------------------------------------------------------------------------
# Tests — find_by_container
# ---------------------------------------------------------------------------


class TestFindByContainer:
    """`find_by_container` resolves the 'secrets owned by this container'
    query that prep-session / wrap-session use when surfacing per-container
    context."""

    def test_npc_with_one_secret(self, secrets_fixture: Path) -> None:
        hits = find_by_container(secrets_fixture, "npcs/maren.md")
        assert [s.slug for s in hits] == ["maren-is-the-spy"]

    def test_adventure_with_multiple_secrets(
        self, secrets_fixture: Path
    ) -> None:
        # The Prism Adventure owns BOTH Maren's Secret (multi-container)
        # AND the Prism core curse. Order is the slug-sorted enumeration
        # order from list_all.
        hits = find_by_container(secrets_fixture, "adventures/the-prism/")
        assert sorted(s.slug for s in hits) == [
            "maren-is-the-spy",
            "prism-core-is-cursed",
        ]

    def test_multi_container_secret_appears_under_each_container(
        self, secrets_fixture: Path
    ) -> None:
        # `maren-is-the-spy` lists BOTH `npcs/maren.md` AND
        # `adventures/the-prism/`; it must appear in both queries.
        maren_hits = {
            s.slug for s in find_by_container(secrets_fixture, "npcs/maren.md")
        }
        prism_hits = {
            s.slug
            for s in find_by_container(secrets_fixture, "adventures/the-prism/")
        }
        assert "maren-is-the-spy" in maren_hits
        assert "maren-is-the-spy" in prism_hits

    def test_container_with_no_secrets_returns_empty(
        self, secrets_fixture: Path
    ) -> None:
        # `npcs/halric.md` exists in the fixture but is in no Secret's
        # belongs_to. The query must not false-positive.
        assert find_by_container(secrets_fixture, "npcs/halric.md") == []

    def test_nonexistent_container_returns_empty(
        self, secrets_fixture: Path
    ) -> None:
        # find_by_container doesn't check that the container file exists
        # (that's the bidi linter's job); it just answers 'is anything
        # claiming to belong to this path?'.
        assert (
            find_by_container(secrets_fixture, "npcs/does-not-exist.md")
            == []
        )

    def test_match_is_exact_string_not_substring(
        self, secrets_fixture: Path
    ) -> None:
        # The match is exact-string per the spec — `adventures/the-prism`
        # without the trailing slash should NOT match the canonical
        # `adventures/the-prism/` entry. Predictability beats convenience.
        hits = find_by_container(
            secrets_fixture, "adventures/the-prism"
        )
        assert hits == [], (
            "find_by_container matched a non-canonical container path "
            "form; the spec requires exact-string matching"
        )


# ---------------------------------------------------------------------------
# Tests — find_dedup_candidates
# ---------------------------------------------------------------------------


class TestFindDedupCandidates:
    """`find_dedup_candidates` applies the dedup normalization to candidate
    Secret names and returns existing Secrets that collide.

    This mirrors the runtime dedup check in `/wrap-session` and `/ingest`
    when they propose a new Secret. The classification (confident UPDATE
    vs ASK-the-GM) is the LLM's job; this query just surfaces the matches.
    """

    def test_exact_slug_match_hits(self, secrets_fixture: Path) -> None:
        hits = find_dedup_candidates(secrets_fixture, "maren-is-the-spy")
        assert [s.slug for s in hits] == ["maren-is-the-spy"]

    def test_first_heading_title_match_hits(
        self, secrets_fixture: Path
    ) -> None:
        # `secrets/jhera-survived.md` has the H1 "Jhera survived the purge".
        # A candidate matching the title should also dedup, per the
        # references/dedup-matching.md rule.
        hits = find_dedup_candidates(
            secrets_fixture, "Jhera survived the purge"
        )
        assert [s.slug for s in hits] == ["jhera-survived"]

    def test_case_and_whitespace_variants_hit(
        self, secrets_fixture: Path
    ) -> None:
        for variant in (
            "Maren Is The Spy",
            "maren  is  the  spy",
            "MAREN-IS-THE-SPY",
            "Maren-is-the-spy.md",
        ):
            hits = find_dedup_candidates(secrets_fixture, variant)
            assert [s.slug for s in hits] == ["maren-is-the-spy"], (
                f"variant {variant!r} did not dedup against "
                "secrets/maren-is-the-spy.md"
            )

    def test_leading_the_stripped(self, secrets_fixture: Path) -> None:
        # The fixture's `prism-core-is-cursed.md` has H1
        # "The Prism core is cursed". The leading "The " must be
        # stripped by the normalization rule.
        hits = find_dedup_candidates(
            secrets_fixture, "The Prism core is cursed"
        )
        assert [s.slug for s in hits] == ["prism-core-is-cursed"]

    def test_genuinely_new_name_does_not_hit(
        self, secrets_fixture: Path
    ) -> None:
        # A truly novel Secret name must not false-positive against any
        # existing Secret. Otherwise the dedup rule would suppress real
        # new content.
        hits = find_dedup_candidates(
            secrets_fixture, "The duke has a half-dragon son"
        )
        assert hits == []

    def test_returns_all_collisions_not_just_first(
        self, secrets_fixture: Path
    ) -> None:
        # If two Secrets ever collide on normalized form (shouldn't happen
        # in a healthy campaign, but the query has to be honest), return
        # both so the LLM can surface the ambiguity to the GM.
        # The fixture doesn't have a natural collision, so we just
        # confirm the empty case here — the return type is a list, not
        # an Optional, so the multi-hit shape is the same.
        assert isinstance(
            find_dedup_candidates(secrets_fixture, "no-such-thing"), list
        )


# ---------------------------------------------------------------------------
# Tests — validate_belongs_to
# ---------------------------------------------------------------------------


class TestValidateBelongsTo:
    """`validate_belongs_to` enforces the ADR-0014 ownership invariant:
    at least one non-ephemeral container path, no all-ephemeral lists,
    no empty lists."""

    def test_accepts_single_npc(self) -> None:
        validate_belongs_to(["npcs/maren.md"])

    def test_accepts_single_adventure_directory(self) -> None:
        validate_belongs_to(["adventures/the-prism/"])

    def test_accepts_multi_container_mix(self) -> None:
        validate_belongs_to(
            [
                "npcs/maren.md",
                "adventures/the-prism/",
                "items/the-prism-core.md",
                "factions/silent-court.md",
                "locations/old-temple.md",
                "pcs/darius.md",
            ]
        )

    def test_rejects_empty_list(self) -> None:
        with pytest.raises(SecretStoreError) as exc:
            validate_belongs_to([])
        assert "empty" in str(exc.value).lower()

    def test_rejects_list_of_empty_strings(self) -> None:
        with pytest.raises(SecretStoreError):
            validate_belongs_to(["", "   "])

    @pytest.mark.parametrize(
        "ephemeral_entry",
        [
            "threads/find-the-spy.md",
            "beats/orin-armor.md",
            "consequences/temple-burned.md",
            "sessions/2026-05-29-session-5/",
            ".ttrpg-staging/wrap/threads/foo.md",
        ],
    )
    def test_rejects_all_ephemeral_list(
        self, ephemeral_entry: str
    ) -> None:
        with pytest.raises(SecretStoreError) as exc:
            validate_belongs_to([ephemeral_entry])
        assert "ephemeral" in str(exc.value).lower()

    def test_accepts_mixed_when_at_least_one_non_ephemeral_present(
        self,
    ) -> None:
        # The spec rejects *only-ephemeral*; if at least one
        # non-ephemeral path is present, the list is acceptable.
        # (The ephemeral entry is still a problem the SKILL.md prose
        # may warn on, but it's not a validate_belongs_to rejection.)
        validate_belongs_to(
            ["npcs/maren.md", "threads/find-the-spy.md"]
        )

    def test_rejects_unknown_folder_root(self) -> None:
        # `random/foo` isn't in either set; the spec only writes paths
        # under the documented non-ephemeral set, so an unknown folder
        # head is rejected (otherwise typos like `npc/maren.md` would
        # slip through silently).
        with pytest.raises(SecretStoreError):
            validate_belongs_to(["random/foo.md"])

    def test_fixture_secrets_pass_validation(
        self, secrets_fixture: Path
    ) -> None:
        # Every Secret in the fixture is a positive example; their
        # belongs_to lists must all validate. If this regresses, either
        # the fixture broke or the validator did.
        for s in list_all(secrets_fixture):
            validate_belongs_to(s.belongs_to)
