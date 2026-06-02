"""Reference-Python coverage of the PC roster proposal spec.

This file follows the v0.1 test convention: the reference Python below
is a thin near-translation of the PC roster proposal algorithm that
`references/pc-roster-proposal.md` documents at runtime. The reference
impl is **not** a runtime helper — skills follow the prose in
`pc-roster-proposal.md` directly. The tests exist so the spec and the
per-skill prose can't silently drift apart: any change to the documented
algorithm must land in both the reference and this file, and the tests
catch mismatches.

Per [ADR-0022](../docs/adr/0022-pc-roster-via-explicit-classification.md)
(superseding [ADR-0018](../docs/adr/0018-pc-roster-as-survey-deliverable.md))
and [ADR-0023](../docs/adr/0023-pc-source-doc-ingestion.md) (slice H2,
PC source-doc ingestion), the PC roster is a Phase 2 (Survey) deliverable.
The refined v0.3 mechanism pre-populates the staged file from three
sources — existing `pcs/<slug>.md` enumeration, auto-add from docs the
GM classifies `PC source: <slug>`, and a GM-typed-adds zone. The
skim-based PC candidate inference from ADR-0018 is gone: no frequency-
of-mention counting, no roster-section scanning, no "Likely PC" /
"Possible NPC" classification.

The four operations covered here mirror the four contract pieces of the
proposal:

  - **`enumerate_existing_pcs`** — given a campaign repo with a `pcs/`
    directory, list each existing PC file with its slug, H1, and
    `aliases:`. These pre-seed the `## Existing PCs` section.
  - **`render_survey_pcs_md`** — render the three-section staged file
    shape documented in pc-roster-proposal.md, including the empty
    states for each section.
  - **`parse_survey_pcs_md`** — walk the GM-edited staged file section
    by section, returning surviving pre-seeded entries (kept as
    no-promotion roster lines) and GM-typed entries (slugified,
    aliases parsed, body parsed) from the "Add other PCs here" zone.
  - **`stage_and_promote_stubs`** — stage only **new** entries (GM-typed
    adds) at `.ttrpg-staging/pcs/<slug>.md`, refuse promotion on
    collision with an existing `pcs/<slug>.md`, and promote
    successfully when no collision exists. Pre-seeded entries do not
    re-stage.

The reference impl mirrors what `references/pc-roster-proposal.md` and
`skills/ingest/SKILL.md` document; if the prose and this file diverge,
one of them is wrong.

Slice H1 of v0.3 implements the ADR-0018 supersession: skim inference
is dropped; existing-`pcs/` enumeration + GM-typed-adds zone replace it.
Slice H2 (this slice, ADR-0023) populates the `## Auto-added from PC
source: docs` section from `PC source: <slug>` doc classifications and
adds PC body enrichment + cross-extraction + bidi-link extension.
"""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

import pytest
import yaml


# ---------------------------------------------------------------------------
# Reference implementation — mirrors references/pc-roster-proposal.md and
# the dedup-matching slug normalization rule it borrows.
# Kept in-file per the v0.1 convention (see test_secret_store.py,
# test_ingest_scaffolding.py for the same pattern). Skills follow the
# prose in pc-roster-proposal.md at runtime; this file pins the spec.
# ---------------------------------------------------------------------------


# Slug normalization rule, sourced from references/dedup-matching.md.
# pc-roster-proposal.md's "Parsing the GM-edited roster" step says:
# "On any GM addition where the GM supplied a name rather than a slug,
#  slugify per the `dedup-matching.md` normalization rule before recording."
_LEADING_THE_RE = re.compile(r"^the[\s\-_]+", flags=re.IGNORECASE)
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")


def slugify(name: str) -> str:
    """Apply the dedup-matching.md normalization rule.

    1. lowercase
    2. strip trailing `.md`
    3. ASCII-fold accents (handled minimally for the test corpus)
    4. strip leading "the "
    5. collapse runs of non-alphanumerics to single hyphens
    6. trim leading/trailing hyphens
    """
    s = name.lower()
    if s.endswith(".md"):
        s = s[:-3]
    # Minimal ASCII fold for the cases the tests exercise.
    fold = str.maketrans({"é": "e", "è": "e", "ê": "e", "ç": "c", "ñ": "n"})
    s = s.translate(fold)
    s = _LEADING_THE_RE.sub("", s)
    s = _NON_ALNUM_RE.sub("-", s)
    return s.strip("-")


# ---------------------------------------------------------------------------
# Existing-pcs/ enumeration — the pre-seeding source under ADR-0022.
# ---------------------------------------------------------------------------


@dataclass
class ExistingPC:
    r"""One pre-seeded entry sourced from a `pcs/<slug>.md` file.

    Per pc-roster-proposal.md "Sources of pre-populated roster entries,"
    each existing PC file produces a roster line of shape
    `<slug>  — existing — \`pcs/<slug>.md\`[  — alias: <names>]`.
    The H1 is read for canonical-name preservation; aliases come from
    the frontmatter.
    """

    slug: str
    canonical_name: str = ""
    aliases: list[str] = field(default_factory=list)


def enumerate_existing_pcs(campaign_root: Path) -> list[ExistingPC]:
    """List every `pcs/<slug>.md` file in the campaign repo.

    Returns one `ExistingPC` per file, with the slug derived from the
    filename (stem), the canonical name read from the file's H1, and
    `aliases:` parsed from frontmatter (`[]` if absent). The list is
    sorted by slug for deterministic rendering.

    If `pcs/` doesn't exist, returns []. This is the "no existing PCs"
    case; the staged file renders an empty-state body in that section.
    """
    pcs_dir = campaign_root / "pcs"
    if not pcs_dir.is_dir():
        return []
    results: list[ExistingPC] = []
    for path in sorted(pcs_dir.glob("*.md")):
        slug = path.stem
        text = path.read_text(encoding="utf-8")
        canonical = _read_h1(text) or slug
        aliases = _read_frontmatter_aliases(text)
        results.append(
            ExistingPC(slug=slug, canonical_name=canonical, aliases=aliases)
        )
    return results


def _read_h1(text: str) -> str:
    """Return the first `# <text>` line after any frontmatter, or empty."""
    lines = text.splitlines()
    i = 0
    if lines and lines[0].strip() == "---":
        # Skip frontmatter.
        i = 1
        while i < len(lines) and lines[i].strip() != "---":
            i += 1
        i += 1  # Past the closing ---.
    for line in lines[i:]:
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    return ""


def _read_frontmatter_aliases(text: str) -> list[str]:
    """Return the `aliases:` list from frontmatter, or [] if absent."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return []
    fm_lines: list[str] = []
    for line in lines[1:]:
        if line.strip() == "---":
            break
        fm_lines.append(line)
    try:
        data = yaml.safe_load("\n".join(fm_lines)) or {}
    except yaml.YAMLError:
        return []
    aliases = data.get("aliases") or []
    if not isinstance(aliases, list):
        return []
    return [str(a) for a in aliases]


# ---------------------------------------------------------------------------
# Staged file rendering and parsing.
# ---------------------------------------------------------------------------


SURVEY_PCS_HEADER = """# Survey: proposed PC roster

Edit this list — confirm, rename, remove, or add. Existing PCs are pre-seeded
from `pcs/`. Add new PCs by typing them into the "Add other PCs here" zone
below. Empty the entire roster if you have no PCs to confirm yet — you can
add them later by hand-editing `pcs/` or by running `/ingest` against a
PC-roster doc.

To add a PC: type a new line in the "Add other PCs here" zone with the slug
(or a free-form name; the agent slugifies on continue). Optional one-line
description after a tab or two spaces becomes the stub file's body.
Nicknames go in `— alias: <name>` suffixes (multiple aliases
comma-separated).

"""


# Load-bearing section headings — the parser uses these to classify
# lines. The reference's "Staged file format" section pins them
# verbatim.
EXISTING_PCS_HEADING = "## Existing PCs"
AUTO_ADDED_HEADING = "## Auto-added from PC source: docs"
GM_ADDS_HEADING = "## Add other PCs here"

EXISTING_PCS_EMPTY_BODY = "(No existing PCs in `pcs/`.)"
AUTO_ADDED_EMPTY_BODY = "(No `PC source:` docs in this input directory.)"
GM_ADDS_INSTRUCTIONAL_BODY = (
    "(Type new PC entries below this line, one per line. Optional one-line "
    "body after tab/double-space. Optional `— alias: <name>` suffix.)"
)


@dataclass
class PcSourceAutoAdd:
    """One auto-add entry sourced from a `PC source: <slug>` doc classification.

    Per `references/pc-roster-proposal.md` (slice H2), each doc the GM
    classifies as `PC source: <slug>` during the description review
    contributes its declared `<slug>` to the staged roster's
    `## Auto-added from PC source: docs` section. The line shape carries
    the doc-name marker so the GM can see which source doc produced
    each auto-add.
    """

    slug: str
    doc_name: str = ""  # The source doc filename (basename), informational.


def render_survey_pcs_md(
    existing: list[ExistingPC],
    auto_added: list[PcSourceAutoAdd] | None = None,
) -> str:
    """Render `.ttrpg-staging/survey-pcs.md` per pc-roster-proposal.md.

    Three labeled sections:
      - `## Existing PCs` — one line per pre-seeded PC (slug + existing
        marker + optional alias suffix), or the empty-state body when
        `pcs/` is empty or absent.
      - `## Auto-added from PC source: docs` — one line per `PC source:
        <slug>` doc classification (slice H2), or the empty-state body
        when no input doc classifies as `PC source:`.
      - `## Add other PCs here` — instructional empty-state body; the
        GM types entries below it before saying continue.

    The three section headings are load-bearing; the parser keys off
    them when walking the file.
    """
    auto_added = auto_added or []
    parts = [SURVEY_PCS_HEADER, EXISTING_PCS_HEADING, ""]
    if existing:
        for pc in existing:
            line = f"{pc.slug}         — existing — `pcs/{pc.slug}.md`"
            if pc.aliases:
                line += f" — alias: {', '.join(pc.aliases)}"
            parts.append(line)
    else:
        parts.append(EXISTING_PCS_EMPTY_BODY)
    parts.append("")
    parts.append(AUTO_ADDED_HEADING)
    parts.append("")
    if auto_added:
        for entry in auto_added:
            doc_marker = (
                f" — auto-added from `{entry.doc_name}` "
                "(PC source classification)"
            )
            parts.append(f"{entry.slug}         {doc_marker.lstrip()}")
    else:
        parts.append(AUTO_ADDED_EMPTY_BODY)
    parts.append("")
    parts.append(GM_ADDS_HEADING)
    parts.append("")
    parts.append(GM_ADDS_INSTRUCTIONAL_BODY)
    parts.append("")
    return "\n".join(parts)


@dataclass
class ParsedRosterEntry:
    """A surviving PC entry after the GM's review.

    `source` distinguishes pre-seeded entries (which do not re-stage)
    from GM-typed adds (which stage a new stub and promote to
    `pcs/<slug>.md`) and from H2's auto-added entries (which act like
    gm_typed for staging — also stage and promote — but originate from
    `PC source: <slug>` doc classifications rather than the GM-typed-adds
    zone).
    """

    slug: str
    body: str = ""
    aliases: list[str] = field(default_factory=list)
    source: str = "gm_typed"  # "existing" | "gm_typed" | "pc_source"


_HEADER_PREFIX = "#"
# Suffix patterns the parser uses.
_EXISTING_MARKER_RE = re.compile(
    r"\s+—\s+existing\s+—\s+`pcs/[^`]+`", flags=re.IGNORECASE
)
_AUTO_ADDED_MARKER_RE = re.compile(
    r"\s+—\s+auto-added\s+from\s+`[^`]+`\s+\(PC source classification\)",
    flags=re.IGNORECASE,
)
_ALIAS_SUFFIX = re.compile(r"—\s*alias:\s*(.+?)\s*$", re.IGNORECASE)


def parse_survey_pcs_md(content: str) -> list[ParsedRosterEntry]:
    """Parse the GM-edited `.ttrpg-staging/survey-pcs.md` back to entries.

    Walk the file section by section. Each `## ` heading switches the
    current section; lines within a section are interpreted per that
    section's rules.

    Returns surviving entries in document order:
      1. Pre-seeded existing PCs from `## Existing PCs` (source="existing").
      2. Auto-added PCs from `## Auto-added from PC source: docs`
         (source="pc_source") — entries with the `auto-added from <doc>`
         marker. Lines in this section without the marker are treated
         as gm_typed (a tolerated GM-typo path).
      3. GM-typed adds from `## Add other PCs here` (source="gm_typed").
    """
    entries: list[ParsedRosterEntry] = []
    current_section: str | None = None

    for raw in content.splitlines():
        stripped = raw.strip()
        if not stripped:
            continue

        # Section heading?
        if stripped.startswith("## "):
            current_section = stripped
            continue
        # H1 / other header → not a section heading we recognize.
        if stripped.startswith(_HEADER_PREFIX):
            current_section = None
            continue

        # Anything before any section heading is contract prose; skip.
        if current_section is None:
            continue

        # Empty-state / instructional parentheticals are not entries.
        if stripped.startswith("(") and stripped.endswith(")"):
            continue

        if current_section == EXISTING_PCS_HEADING:
            entry = _parse_existing_line(stripped)
            if entry is not None:
                entries.append(entry)
        elif current_section == AUTO_ADDED_HEADING:
            entry = _parse_auto_added_line(stripped)
            if entry is not None:
                entries.append(entry)
        elif current_section == GM_ADDS_HEADING:
            entry = _parse_gm_typed_line(stripped)
            if entry is not None:
                entries.append(entry)
        else:
            # Unknown section heading — defensive skip.
            continue

    return entries


def _parse_auto_added_line(line: str) -> ParsedRosterEntry | None:
    r"""Parse a `## Auto-added from PC source: docs` line.

    Two shapes:
      - Auto-added: `<slug>  — auto-added from `<doc>` (PC source classification)[  — alias: ...]`
        → ParsedRosterEntry(slug=<slug>, source="pc_source", aliases=...).
      - GM-typed (typo path — GM hand-typed into the wrong section):
        falls through to `_parse_gm_typed_line` semantics with
        source="gm_typed".
    """
    if not _AUTO_ADDED_MARKER_RE.search(line):
        # GM typed something here that isn't an agent-authored auto-add;
        # treat as a gm_typed entry (tolerated typo path per the spec).
        return _parse_gm_typed_line(line)
    # Pull off any trailing `— alias: ...` suffix first.
    aliases: list[str] = []
    alias_match = _ALIAS_SUFFIX.search(line)
    if alias_match:
        alias_str = alias_match.group(1)
        aliases = [a.strip() for a in alias_str.split(",") if a.strip()]
        line = line[: alias_match.start()].rstrip(" —")
    # Strip the `— auto-added from <doc> (PC source classification)` marker.
    line = _AUTO_ADDED_MARKER_RE.sub("", line).strip()
    # First whitespace-delimited token is the slug.
    parts = line.split(None, 1)
    if not parts:
        return None
    slug = slugify(parts[0])
    if not slug:
        return None
    return ParsedRosterEntry(
        slug=slug, body="", aliases=aliases, source="pc_source"
    )


def _parse_existing_line(line: str) -> ParsedRosterEntry | None:
    r"""Parse an `## Existing PCs` line.

    Shape: `<slug>  — existing — \`pcs/<slug>.md\`[  — alias: <names>]`
    The slug is the first whitespace-delimited token; the `existing —
    \`pcs/...\`` marker is informational (the parser doesn't need it to
    classify, since the section heading already did). Aliases come
    from any `— alias:` suffix.
    """
    # Pull off any trailing `— alias: ...` suffix first.
    aliases: list[str] = []
    alias_match = _ALIAS_SUFFIX.search(line)
    if alias_match:
        alias_str = alias_match.group(1)
        aliases = [a.strip() for a in alias_str.split(",") if a.strip()]
        line = line[: alias_match.start()].rstrip(" —")
    # Strip the `— existing — \`pcs/...\`` marker if present.
    line = _EXISTING_MARKER_RE.sub("", line).strip()
    # First whitespace-delimited token is the slug.
    parts = line.split(None, 1)
    if not parts:
        return None
    slug = slugify(parts[0])
    if not slug:
        return None
    return ParsedRosterEntry(
        slug=slug, body="", aliases=aliases, source="existing"
    )


def _parse_gm_typed_line(line: str) -> ParsedRosterEntry | None:
    """Parse a GM-typed line from the `## Add other PCs here` zone.

    The GM may type:
      - a bare slug (`marisa`)
      - a free-form name (`The Shadow` → slugifies to `shadow`)
      - a slug with a one-line body separated by tab/double-space
        (`marisa  Marisa Stoneforge, dwarven smith`)
      - any of the above with a trailing `— alias: <name>` suffix
    """
    aliases: list[str] = []
    alias_match = _ALIAS_SUFFIX.search(line)
    if alias_match:
        alias_str = alias_match.group(1)
        aliases = [a.strip() for a in alias_str.split(",") if a.strip()]
        line = line[: alias_match.start()].rstrip(" —")

    # Split on tab or two-or-more spaces. The leading token is the
    # slug-or-name; anything after is the body.
    parts = re.split(r"[\t ]{2,}|\t", line, maxsplit=1)
    slug_token = parts[0].strip()
    body_text = parts[1].strip() if len(parts) > 1 else ""

    slug = slugify(slug_token)
    if not slug:
        return None
    return ParsedRosterEntry(
        slug=slug, body=body_text, aliases=aliases, source="gm_typed"
    )


# ---------------------------------------------------------------------------
# Stub staging and promotion to `pcs/<slug>.md`.
# ---------------------------------------------------------------------------


@dataclass
class StubPromotionResult:
    """What happened during staging + promotion.

    `promoted` holds the final paths of newly-promoted stubs.
    `collisions` holds slugs blocked by an existing `pcs/<slug>.md`.
    `skipped_existing` holds the slugs of pre-seeded entries that
    flowed through to the in-memory roster without staging anything
    (the existing file is left untouched).
    """

    promoted: list[str] = field(default_factory=list)
    collisions: list[str] = field(default_factory=list)
    skipped_existing: list[str] = field(default_factory=list)


def render_pc_stub(entry: ParsedRosterEntry) -> str:
    """Render a `pcs/<slug>.md` stub per pc-roster-proposal.md.

    Frontmatter:
      kind: pc
      aliases: [...]   (omitted entirely if none)

    Body: H1 (canonical-name form of the slug, or GM-supplied name
    parsed from the body) plus optional one-line description if the
    GM enriched the line.
    """
    fm_lines = ["---", "kind: pc"]
    if entry.aliases:
        fm_lines.append(f"aliases: [{', '.join(entry.aliases)}]")
    fm_lines.append("---")
    fm = "\n".join(fm_lines)

    # Canonical name from the slug: title-case each hyphen-separated
    # token. (`silas` → `Silas`, `the-shadow` → `The Shadow`.)
    h1 = " ".join(t.capitalize() for t in entry.slug.split("-"))

    body = ""
    if entry.body:
        body = f"\n{entry.body}\n"
    return f"{fm}\n\n# {h1}\n{body}"


def stage_and_promote_stubs(
    entries: list[ParsedRosterEntry],
    campaign_root: Path,
) -> StubPromotionResult:
    """Stage stubs at `.ttrpg-staging/pcs/<slug>.md` then promote.

    Per pc-roster-proposal.md "Stub staging and promotion to
    `pcs/<slug>.md`":
      - Pre-seeded entries (source="existing") do **not** re-stage and
        do **not** overwrite. They flow into the in-memory roster only.
      - New entries (source="gm_typed" or "pc_source") stage at
        `.ttrpg-staging/pcs/<slug>.md`.
      - If any new entry's slug collides with an existing
        `pcs/<slug>.md`, STOP and record the collision. Don't silently
        overwrite a GM-authored PC file.
      - On clean staging, promote each new stub to `pcs/<slug>.md`,
        delete the staged copy, and remove `.ttrpg-staging/pcs/` if
        it's empty.

    Empty roster (no entries at all) → no-op.

    Note on `pc_source` entries: under ADR-0023, a `PC source: <slug>`
    classification on a doc may name a PC that already exists in `pcs/`
    (the slug matches an existing entry). When the entry collides with
    an existing PC file, this function records the collision the same
    way it does for gm_typed — but the SKILL prose treats `pc_source`
    collisions as a no-op (the existing PC is the file to enrich during
    Phase 3, not a collision to surface). Tests for that distinction
    live below.
    """
    result = StubPromotionResult()
    if not entries:
        return result

    # Partition entries by source. Existing entries skip staging.
    new_entries = [e for e in entries if e.source != "existing"]
    for entry in entries:
        if entry.source == "existing":
            result.skipped_existing.append(entry.slug)

    if not new_entries:
        return result

    staging_dir = campaign_root / ".ttrpg-staging" / "pcs"
    pcs_dir = campaign_root / "pcs"

    # Stage every new stub first.
    staging_dir.mkdir(parents=True, exist_ok=True)
    staged_paths: list[Path] = []
    for entry in new_entries:
        staged_path = staging_dir / f"{entry.slug}.md"
        staged_path.write_text(render_pc_stub(entry), encoding="utf-8")
        staged_paths.append(staged_path)

    # Collision check.
    for entry in new_entries:
        live_path = pcs_dir / f"{entry.slug}.md"
        if live_path.exists():
            result.collisions.append(entry.slug)

    if result.collisions:
        return result

    # Promote.
    pcs_dir.mkdir(parents=True, exist_ok=True)
    for staged_path in staged_paths:
        live_path = pcs_dir / staged_path.name
        live_path.write_text(
            staged_path.read_text(encoding="utf-8"), encoding="utf-8"
        )
        staged_path.unlink()
        result.promoted.append(str(live_path.relative_to(campaign_root)))

    try:
        staging_dir.rmdir()
    except OSError:
        pass

    return result


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def _write_pc_file(
    campaign_root: Path,
    slug: str,
    canonical: str | None = None,
    aliases: list[str] | None = None,
    body: str = "",
) -> Path:
    """Helper to write a `pcs/<slug>.md` for the enumeration tests."""
    pcs_dir = campaign_root / "pcs"
    pcs_dir.mkdir(parents=True, exist_ok=True)
    fm_lines = ["---", "kind: pc"]
    if aliases:
        fm_lines.append(f"aliases: [{', '.join(aliases)}]")
    fm_lines.append("---")
    h1 = canonical or slug.capitalize()
    text = "\n".join(fm_lines) + f"\n\n# {h1}\n"
    if body:
        text += f"\n{body}\n"
    path = pcs_dir / f"{slug}.md"
    path.write_text(text, encoding="utf-8")
    return path


class TestSlugify:
    """The slug rule borrowed from dedup-matching.md."""

    def test_lowercases_and_hyphenates(self) -> None:
        assert slugify("Silas Stoneforge") == "silas-stoneforge"

    def test_strips_leading_the(self) -> None:
        assert slugify("The Shadow") == "shadow"

    def test_collapses_runs_of_non_alnum(self) -> None:
        assert slugify("Café  du   Monde!") == "cafe-du-monde"


class TestEnumerateExistingPCs:
    """The pre-seeding source for the refined mechanism."""

    def test_empty_when_pcs_dir_missing(self, tmp_path: Path) -> None:
        assert enumerate_existing_pcs(tmp_path) == []

    def test_empty_when_pcs_dir_present_but_empty(self, tmp_path: Path) -> None:
        (tmp_path / "pcs").mkdir()
        assert enumerate_existing_pcs(tmp_path) == []

    def test_lists_one_existing_pc(self, tmp_path: Path) -> None:
        _write_pc_file(tmp_path, "silas", canonical="Silas")
        [pc] = enumerate_existing_pcs(tmp_path)
        assert pc.slug == "silas"
        assert pc.canonical_name == "Silas"
        assert pc.aliases == []

    def test_lists_multiple_existing_pcs_sorted_by_slug(
        self, tmp_path: Path
    ) -> None:
        _write_pc_file(tmp_path, "silas")
        _write_pc_file(tmp_path, "rae")
        _write_pc_file(tmp_path, "betha")
        pcs = enumerate_existing_pcs(tmp_path)
        assert [p.slug for p in pcs] == ["betha", "rae", "silas"]

    def test_reads_aliases_from_frontmatter(self, tmp_path: Path) -> None:
        _write_pc_file(
            tmp_path, "helerel", canonical="Helerel", aliases=["Helly"]
        )
        [pc] = enumerate_existing_pcs(tmp_path)
        assert pc.aliases == ["Helly"]


class TestRenderSurveyPcsMd:
    """The `.ttrpg-staging/survey-pcs.md` shape under the refined mechanism."""

    def test_header_is_present(self) -> None:
        rendered = render_survey_pcs_md([])
        assert rendered.startswith("# Survey: proposed PC roster")

    def test_three_section_headings_are_present(self) -> None:
        rendered = render_survey_pcs_md([])
        assert EXISTING_PCS_HEADING in rendered
        assert AUTO_ADDED_HEADING in rendered
        assert GM_ADDS_HEADING in rendered

    def test_empty_existing_renders_empty_state_body(self) -> None:
        rendered = render_survey_pcs_md([])
        assert EXISTING_PCS_EMPTY_BODY in rendered

    def test_existing_pcs_render_as_pre_seeded_lines(self) -> None:
        existing = [
            ExistingPC(slug="silas", canonical_name="Silas"),
            ExistingPC(slug="rae", canonical_name="Rae"),
        ]
        rendered = render_survey_pcs_md(existing)
        # Each existing PC marked with "existing — `pcs/<slug>.md`".
        assert "silas" in rendered
        assert "existing — `pcs/silas.md`" in rendered
        assert "existing — `pcs/rae.md`" in rendered

    def test_existing_pc_with_alias_renders_alias_suffix(self) -> None:
        existing = [
            ExistingPC(
                slug="helerel",
                canonical_name="Helerel",
                aliases=["Helly"],
            )
        ]
        rendered = render_survey_pcs_md(existing)
        assert "— alias: Helly" in rendered

    def test_auto_added_section_empty_state(self) -> None:
        # H2's contract: when no `PC source:` docs are in the input,
        # the section renders the empty-state body.
        rendered = render_survey_pcs_md([])
        assert AUTO_ADDED_EMPTY_BODY in rendered

    def test_auto_added_section_with_one_pc_source_doc(self) -> None:
        # H2's primary path: one auto-added entry from a `PC source:` doc.
        rendered = render_survey_pcs_md(
            [],
            auto_added=[
                PcSourceAutoAdd(
                    slug="aldric", doc_name="aldric-backstory.md"
                )
            ],
        )
        assert AUTO_ADDED_EMPTY_BODY not in rendered
        assert "aldric" in rendered
        assert "aldric-backstory.md" in rendered
        assert "(PC source classification)" in rendered

    def test_auto_added_section_with_multiple_pc_source_docs(self) -> None:
        rendered = render_survey_pcs_md(
            [],
            auto_added=[
                PcSourceAutoAdd(slug="aldric", doc_name="aldric.md"),
                PcSourceAutoAdd(slug="vera", doc_name="vera.md"),
            ],
        )
        assert "aldric" in rendered
        assert "vera" in rendered

    def test_pc_source_classification_appears_only_under_auto_added_section(
        self,
    ) -> None:
        # The auto-add marker should land under the auto-added heading,
        # not inside the existing or gm-typed sections.
        rendered = render_survey_pcs_md(
            [ExistingPC(slug="silas", canonical_name="Silas")],
            auto_added=[
                PcSourceAutoAdd(slug="aldric", doc_name="aldric.md")
            ],
        )
        # Find the section boundaries.
        auto_added_idx = rendered.find(AUTO_ADDED_HEADING)
        gm_adds_idx = rendered.find(GM_ADDS_HEADING)
        assert auto_added_idx >= 0 and gm_adds_idx > auto_added_idx
        auto_added_section = rendered[auto_added_idx:gm_adds_idx]
        assert "aldric" in auto_added_section
        # The existing PC stays in its section.
        existing_idx = rendered.find(EXISTING_PCS_HEADING)
        existing_section = rendered[existing_idx:auto_added_idx]
        assert "silas" in existing_section
        assert "aldric" not in existing_section

    def test_gm_adds_zone_has_instructional_body(self) -> None:
        # The "Add other PCs here" zone is empty by default but
        # signals the GM where to type.
        rendered = render_survey_pcs_md([])
        assert GM_ADDS_INSTRUCTIONAL_BODY in rendered


class TestNoSkimBasedCandidateInference:
    """Assert the negative: skim inference is no longer present.

    Slice H1 explicitly drops the ADR-0018 skim-signal collection
    (frequency-of-mention, explicit-roster-section scanning,
    party-pronoun proximity, narrator-as-actor framing, "Likely PC" /
    "Possible NPC" classification labels). These tests pin that those
    mechanisms are absent from the reference and the staged file.
    """

    def test_no_classify_candidates_symbol_in_module(self) -> None:
        # The ADR-0018 mechanism's central aggregator was
        # `classify_candidates`. It's gone under ADR-0022.
        import sys

        mod = sys.modules[__name__]
        assert not hasattr(mod, "classify_candidates"), (
            "classify_candidates was the ADR-0018 skim-inference "
            "aggregator. ADR-0022 drops it. If you're re-adding it, "
            "you may be regressing the supersession."
        )

    def test_staged_file_does_not_carry_likely_pc_label(self) -> None:
        # The "Likely PC" / "Possible NPC" classification labels were
        # the user-visible surface of skim inference. They're gone.
        rendered = render_survey_pcs_md(
            [ExistingPC(slug="silas", canonical_name="Silas")]
        )
        assert "Likely PC" not in rendered
        assert "Possible NPC" not in rendered

    def test_staged_file_does_not_carry_frequency_annotations(self) -> None:
        # The "appears in N docs" frequency annotation was the other
        # user-visible surface of skim inference. Gone.
        rendered = render_survey_pcs_md(
            [ExistingPC(slug="silas", canonical_name="Silas")]
        )
        assert "appears in" not in rendered

    def test_reference_prose_documents_no_skim_inference(
        self, repo_root: Path
    ) -> None:
        # The reference's own prose must call out the drop explicitly,
        # so a contributor reading the file sees the supersession
        # rather than the v0.2 mechanism.
        ref = repo_root / "references" / "pc-roster-proposal.md"
        content = ref.read_text(encoding="utf-8")
        # The reference must cite ADR-0022.
        assert "0022-pc-roster-via-explicit-classification" in content, (
            "references/pc-roster-proposal.md must cite ADR-0022 — "
            "the supersession ADR. Without the citation, a contributor "
            "reading the reference may not realize the v0.2 mechanism "
            "was stepped back."
        )
        # The reference must NOT document the dropped heuristics as
        # active mechanism. "Likely PC" and "Possible NPC" labels were
        # ADR-0018's user-visible surface; they no longer appear.
        assert "Likely PC" not in content, (
            "references/pc-roster-proposal.md should not document "
            "'Likely PC' classification — that was ADR-0018's "
            "skim-inference mechanism, dropped under ADR-0022."
        )
        assert "Possible NPC" not in content, (
            "references/pc-roster-proposal.md should not document "
            "'Possible NPC' classification — that was ADR-0018's "
            "skim-inference mechanism, dropped under ADR-0022."
        )


class TestParseSurveyPcsMd:
    """Round-trip the staged file back into surviving entries."""

    def test_empty_roster_returns_no_entries(self) -> None:
        rendered = render_survey_pcs_md([])
        assert parse_survey_pcs_md(rendered) == []

    def test_pre_seeded_entries_parse_as_existing_source(self) -> None:
        existing = [
            ExistingPC(slug="silas", canonical_name="Silas"),
            ExistingPC(slug="rae", canonical_name="Rae"),
        ]
        rendered = render_survey_pcs_md(existing)
        parsed = parse_survey_pcs_md(rendered)
        assert [(e.slug, e.source) for e in parsed] == [
            ("silas", "existing"),
            ("rae", "existing"),
        ]

    def test_pre_seeded_entry_with_alias_parses_alias(self) -> None:
        existing = [
            ExistingPC(
                slug="helerel",
                canonical_name="Helerel",
                aliases=["Helly"],
            )
        ]
        rendered = render_survey_pcs_md(existing)
        [entry] = parse_survey_pcs_md(rendered)
        assert entry.slug == "helerel"
        assert entry.aliases == ["Helly"]
        assert entry.source == "existing"

    def test_pre_seeded_entry_dropped_by_gm_does_not_appear(self) -> None:
        # GM deleted the `silas` line from `## Existing PCs`. The
        # parser surfaces only the surviving line.
        existing = [
            ExistingPC(slug="silas", canonical_name="Silas"),
            ExistingPC(slug="rae", canonical_name="Rae"),
        ]
        rendered = render_survey_pcs_md(existing)
        # Strip the silas line.
        edited = "\n".join(
            line for line in rendered.splitlines() if not line.startswith("silas")
        )
        parsed = parse_survey_pcs_md(edited)
        assert [e.slug for e in parsed] == ["rae"]

    def test_gm_typed_add_in_add_zone_parses_as_gm_typed(self) -> None:
        # The reference's "GM-typed adds zone" — the GM appends entries
        # below the instructional body line in the `## Add other PCs
        # here` section.
        rendered = render_survey_pcs_md([])
        edited = rendered + "marisa\n"
        [entry] = parse_survey_pcs_md(edited)
        assert entry.slug == "marisa"
        assert entry.source == "gm_typed"

    def test_gm_typed_free_form_name_is_slugified(self) -> None:
        # Per the dedup-matching rule: "The Shadow" → "shadow".
        rendered = render_survey_pcs_md([])
        edited = rendered + "The Shadow\n"
        [entry] = parse_survey_pcs_md(edited)
        assert entry.slug == "shadow"
        assert entry.source == "gm_typed"

    def test_gm_typed_with_body_parses_body(self) -> None:
        rendered = render_survey_pcs_md([])
        edited = rendered + "marisa\tdwarven smith, late addition\n"
        [entry] = parse_survey_pcs_md(edited)
        assert entry.slug == "marisa"
        assert entry.body == "dwarven smith, late addition"

    def test_gm_typed_with_alias_parses_alias(self) -> None:
        rendered = render_survey_pcs_md([])
        edited = rendered + "marisa — alias: Mari, Marisa Stoneforge\n"
        [entry] = parse_survey_pcs_md(edited)
        assert entry.slug == "marisa"
        assert entry.aliases == ["Mari", "Marisa Stoneforge"]

    def test_gm_adds_zone_preserved_across_staging_file_edits(
        self,
    ) -> None:
        # Round-trip property: a rendered file with GM-typed adds in
        # the zone parses back to the same set of entries. The zone is
        # "preserved" in the sense that the section heading and the
        # GM's lines below it survive parse-and-render.
        existing = [ExistingPC(slug="silas", canonical_name="Silas")]
        rendered = render_survey_pcs_md(existing)
        edited = (
            rendered
            + "marisa\tlate addition\n"
            + "the-shadow — alias: Veiled One\n"
        )
        parsed = parse_survey_pcs_md(edited)
        assert [(e.slug, e.source) for e in parsed] == [
            ("silas", "existing"),
            ("marisa", "gm_typed"),
            ("shadow", "gm_typed"),
        ]

    def test_pre_seeded_and_gm_typed_are_distinguishable(self) -> None:
        # The source distinction is load-bearing: pre-seeded entries
        # do not re-stage; GM-typed entries do.
        existing = [ExistingPC(slug="silas", canonical_name="Silas")]
        rendered = render_survey_pcs_md(existing)
        edited = rendered + "marisa\n"
        parsed = parse_survey_pcs_md(edited)
        sources = {e.slug: e.source for e in parsed}
        assert sources["silas"] == "existing"
        assert sources["marisa"] == "gm_typed"

    def test_auto_added_empty_when_no_pc_source_docs(self) -> None:
        # H2 contract: when no input doc classified as `PC source:`,
        # the auto-added section renders its empty-state body and the
        # parser produces zero pc_source entries.
        existing = [ExistingPC(slug="silas", canonical_name="Silas")]
        rendered = render_survey_pcs_md(existing)
        parsed = parse_survey_pcs_md(rendered)
        assert all(e.source != "pc_source" for e in parsed)

    def test_auto_added_entry_parses_as_pc_source(self) -> None:
        # H2 primary path: a `PC source: <slug>` doc classification
        # auto-added to the staged roster parses back as a pc_source
        # entry.
        rendered = render_survey_pcs_md(
            [ExistingPC(slug="silas", canonical_name="Silas")],
            auto_added=[
                PcSourceAutoAdd(
                    slug="aldric", doc_name="aldric-backstory.md"
                )
            ],
        )
        parsed = parse_survey_pcs_md(rendered)
        sources = {e.slug: e.source for e in parsed}
        assert sources == {"silas": "existing", "aldric": "pc_source"}

    def test_auto_added_entry_with_gm_alias_edit_preserves_pc_source(
        self,
    ) -> None:
        # The GM may add a `— alias: <name>` suffix to an auto-added
        # entry without changing its source classification.
        rendered = render_survey_pcs_md(
            [],
            auto_added=[
                PcSourceAutoAdd(
                    slug="aldric", doc_name="aldric-backstory.md"
                )
            ],
        )
        # Simulate GM appending an alias suffix.
        edited = rendered.replace(
            "(PC source classification)",
            "(PC source classification) — alias: Al",
        )
        [entry] = parse_survey_pcs_md(edited)
        assert entry.slug == "aldric"
        assert entry.source == "pc_source"
        assert entry.aliases == ["Al"]

    def test_auto_added_gm_typed_typo_falls_through_to_gm_typed(self) -> None:
        # If the GM hand-types an entry into `## Auto-added from PC
        # source: docs` instead of `## Add other PCs here`, the parser
        # tolerates it as a gm_typed entry (no `auto-added from` marker
        # means "this line wasn't agent-authored").
        rendered = render_survey_pcs_md([])
        edited = rendered.replace(
            AUTO_ADDED_EMPTY_BODY, "marisa"
        )
        [entry] = parse_survey_pcs_md(edited)
        assert entry.slug == "marisa"
        assert entry.source == "gm_typed"

    def test_gm_deleted_auto_added_entry_does_not_appear(self) -> None:
        # GM deleted an auto-added line. The parser only surfaces the
        # entries that survived in the staged file.
        rendered = render_survey_pcs_md(
            [],
            auto_added=[
                PcSourceAutoAdd(slug="aldric", doc_name="aldric.md"),
                PcSourceAutoAdd(slug="vera", doc_name="vera.md"),
            ],
        )
        edited = "\n".join(
            line for line in rendered.splitlines()
            if not line.startswith("aldric")
        )
        parsed = parse_survey_pcs_md(edited)
        assert [e.slug for e in parsed] == ["vera"]


class TestStageAndPromoteStubs:
    """The Step 5 stub lifecycle under the refined mechanism."""

    def test_empty_roster_is_a_no_op(self, tmp_path: Path) -> None:
        result = stage_and_promote_stubs([], tmp_path)
        assert result.promoted == []
        assert result.collisions == []
        assert not (tmp_path / ".ttrpg-staging").exists()
        assert not (tmp_path / "pcs").exists()

    def test_pre_seeded_entries_do_not_restage(self, tmp_path: Path) -> None:
        # The existing `pcs/silas.md` was pre-seeded; the staged
        # roster surfaced it; the GM kept it. The promotion step must
        # not touch the file on disk.
        path = _write_pc_file(tmp_path, "silas", canonical="Silas")
        original_content = path.read_text(encoding="utf-8")

        entries = [
            ParsedRosterEntry(slug="silas", source="existing"),
        ]
        result = stage_and_promote_stubs(entries, tmp_path)

        # Nothing promoted (no new stubs); existing surfaced as skipped.
        assert result.promoted == []
        assert result.collisions == []
        assert "silas" in result.skipped_existing
        # Existing file untouched.
        assert path.read_text(encoding="utf-8") == original_content
        # No staging directory left behind.
        assert not (tmp_path / ".ttrpg-staging" / "pcs").exists()

    def test_promotes_gm_typed_stubs_when_no_collision(
        self, tmp_path: Path
    ) -> None:
        entries = [
            ParsedRosterEntry(slug="marisa", source="gm_typed"),
            ParsedRosterEntry(slug="rae", source="gm_typed"),
        ]
        result = stage_and_promote_stubs(entries, tmp_path)
        assert result.collisions == []
        assert sorted(result.promoted) == ["pcs/marisa.md", "pcs/rae.md"]
        assert not (tmp_path / ".ttrpg-staging" / "pcs").exists()
        assert (tmp_path / "pcs" / "marisa.md").is_file()
        assert (tmp_path / "pcs" / "rae.md").is_file()

    def test_mixed_existing_and_new_only_promotes_new(
        self, tmp_path: Path
    ) -> None:
        # Existing PC pre-seeded; GM typed a new one. Only the new one
        # stages and promotes; the existing file is untouched.
        existing_path = _write_pc_file(
            tmp_path, "silas", canonical="Silas", body="GM-authored."
        )
        original_existing = existing_path.read_text(encoding="utf-8")

        entries = [
            ParsedRosterEntry(slug="silas", source="existing"),
            ParsedRosterEntry(slug="marisa", source="gm_typed"),
        ]
        result = stage_and_promote_stubs(entries, tmp_path)

        assert result.promoted == ["pcs/marisa.md"]
        assert result.skipped_existing == ["silas"]
        assert result.collisions == []
        # Existing PC body preserved verbatim.
        assert existing_path.read_text(encoding="utf-8") == original_existing
        # New stub written.
        assert (tmp_path / "pcs" / "marisa.md").is_file()

    def test_stub_has_kind_pc_frontmatter(self, tmp_path: Path) -> None:
        stage_and_promote_stubs(
            [ParsedRosterEntry(slug="marisa", source="gm_typed")], tmp_path
        )
        content = (tmp_path / "pcs" / "marisa.md").read_text(encoding="utf-8")
        assert content.startswith("---\nkind: pc\n")
        assert "# Marisa" in content

    def test_stub_renders_aliases_when_present(self, tmp_path: Path) -> None:
        stage_and_promote_stubs(
            [
                ParsedRosterEntry(
                    slug="helerel",
                    aliases=["Helly"],
                    source="gm_typed",
                )
            ],
            tmp_path,
        )
        content = (tmp_path / "pcs" / "helerel.md").read_text(encoding="utf-8")
        assert "aliases: [Helly]" in content

    def test_stub_omits_aliases_key_when_none(self, tmp_path: Path) -> None:
        stage_and_promote_stubs(
            [ParsedRosterEntry(slug="marisa", source="gm_typed")], tmp_path
        )
        content = (tmp_path / "pcs" / "marisa.md").read_text(encoding="utf-8")
        assert "aliases:" not in content

    def test_stub_body_includes_gm_one_line_description(
        self, tmp_path: Path
    ) -> None:
        stage_and_promote_stubs(
            [
                ParsedRosterEntry(
                    slug="marisa",
                    body="dwarven smith, late addition",
                    source="gm_typed",
                )
            ],
            tmp_path,
        )
        content = (tmp_path / "pcs" / "marisa.md").read_text(encoding="utf-8")
        assert "dwarven smith, late addition" in content

    def test_collision_with_existing_pcs_file_stops_promotion(
        self, tmp_path: Path
    ) -> None:
        # GM typed a slug in the "Add other PCs here" zone that
        # collides with an existing file. The collision check fires.
        existing_path = _write_pc_file(
            tmp_path, "silas", canonical="Silas", body="GM-authored."
        )
        original_existing = existing_path.read_text(encoding="utf-8")

        entries = [
            ParsedRosterEntry(slug="silas", source="gm_typed"),
            ParsedRosterEntry(slug="rae", source="gm_typed"),
        ]
        result = stage_and_promote_stubs(entries, tmp_path)

        assert "silas" in result.collisions
        assert result.promoted == []
        # Existing GM-authored file untouched.
        assert existing_path.read_text(encoding="utf-8") == original_existing
        # `rae.md` was NOT promoted because the reference says "stage
        # every stub before promoting any" — collision blocks the
        # whole promotion. The staged stubs remain for GM inspection.
        assert not (tmp_path / "pcs" / "rae.md").exists()
        assert (
            tmp_path / ".ttrpg-staging" / "pcs" / "silas.md"
        ).is_file()
        assert (tmp_path / ".ttrpg-staging" / "pcs" / "rae.md").is_file()

    def test_pc_source_entry_stages_and_promotes_like_gm_typed(
        self, tmp_path: Path
    ) -> None:
        # H2: a `PC source: <slug>` doc auto-add yields a pc_source
        # entry that stages and promotes the same way gm_typed does.
        entries = [
            ParsedRosterEntry(slug="aldric", source="pc_source"),
        ]
        result = stage_and_promote_stubs(entries, tmp_path)
        assert result.promoted == ["pcs/aldric.md"]
        assert result.collisions == []
        assert (tmp_path / "pcs" / "aldric.md").is_file()

    def test_pc_source_stub_has_kind_pc(self, tmp_path: Path) -> None:
        # The stub Phase 2 promotes for a pc_source entry is the same
        # minimal H1-only stub as a gm_typed entry — backstory enrichment
        # happens during Phase 3 PC source extraction, not at stub
        # creation (per ADR-0023).
        stage_and_promote_stubs(
            [ParsedRosterEntry(slug="aldric", source="pc_source")], tmp_path
        )
        content = (tmp_path / "pcs" / "aldric.md").read_text(
            encoding="utf-8"
        )
        assert content.startswith("---\nkind: pc\n")
        assert "# Aldric" in content


class TestReferenceFileExistsAndCitesADR:
    """Spec-drift safety net: the reference itself must exist and cite the ADRs."""

    def test_reference_file_exists(self, repo_root: Path) -> None:
        ref = repo_root / "references" / "pc-roster-proposal.md"
        assert ref.is_file(), (
            "references/pc-roster-proposal.md is the shared spec consumed "
            "by /ingest and /init-campaign (docs mode); the reference impl "
            "in this test mirrors its prose. The file is missing."
        )

    def test_reference_cites_adr_0022(self, repo_root: Path) -> None:
        ref = repo_root / "references" / "pc-roster-proposal.md"
        content = ref.read_text(encoding="utf-8")
        assert "0022-pc-roster-via-explicit-classification" in content, (
            "references/pc-roster-proposal.md must cite ADR-0022 — it is "
            "the architectural decision the reference implements under v0.3."
        )

    def test_reference_still_cites_adr_0018_as_predecessor(
        self, repo_root: Path
    ) -> None:
        ref = repo_root / "references" / "pc-roster-proposal.md"
        content = ref.read_text(encoding="utf-8")
        # ADR-0022's policy claims (Phase 2 deliverable status, dual-file
        # batch, single-doc scope, etc.) are inherited from ADR-0018 by
        # narrow supersession. The reference cites both so a reader
        # tracing the lineage sees the full chain.
        assert "0018-pc-roster-as-survey-deliverable" in content, (
            "references/pc-roster-proposal.md must still cite ADR-0018 — "
            "ADR-0022 narrowly supersedes its candidate-source layer; "
            "the broader policy framing remains."
        )

    def test_adr_0022_exists(self, repo_root: Path) -> None:
        adr = (
            repo_root
            / "docs"
            / "adr"
            / "0022-pc-roster-via-explicit-classification.md"
        )
        assert adr.is_file(), (
            "ADR-0022 (PC roster via GM-explicit classification) is the "
            "supersession of ADR-0018. It must exist and be cited from "
            "the reference."
        )

    def test_adr_0018_has_superseded_status_line(
        self, repo_root: Path
    ) -> None:
        adr = (
            repo_root
            / "docs"
            / "adr"
            / "0018-pc-roster-as-survey-deliverable.md"
        )
        content = adr.read_text(encoding="utf-8")
        assert "superseded by" in content.lower(), (
            "ADR-0018 must carry a `Status: superseded by ADR-0022` line "
            "so contributors reading it see the supersession before the "
            "v0.2 mechanism prose."
        )
        assert "0022" in content, (
            "ADR-0018's supersession status must name ADR-0022 explicitly."
        )

    def test_ingest_skill_md_cites_reference(self, repo_root: Path) -> None:
        skill = repo_root / "skills" / "ingest" / "SKILL.md"
        content = skill.read_text(encoding="utf-8")
        assert "references/pc-roster-proposal.md" in content, (
            "skills/ingest/SKILL.md must cite references/pc-roster-proposal.md "
            "per slice B2 of the v0.3 modularization."
        )

    def test_adr_0023_exists(self, repo_root: Path) -> None:
        adr = (
            repo_root / "docs" / "adr" / "0023-pc-source-doc-ingestion.md"
        )
        assert adr.is_file(), (
            "ADR-0023 (PC source-doc ingestion) is the slice-H2 design "
            "ADR. It documents the `PC source:` classification, Phase 3 "
            "routing, body enrichment, cross-extraction, bidi-link "
            "extension, and the optional frontmatter slice."
        )

    def test_reference_cites_adr_0023_for_auto_add_mechanism(
        self, repo_root: Path
    ) -> None:
        # H2 fills in the placeholder ADR-0022 left in the reference.
        ref = repo_root / "references" / "pc-roster-proposal.md"
        content = ref.read_text(encoding="utf-8")
        assert "0023-pc-source-doc-ingestion" in content or "ADR-0023" in content, (
            "references/pc-roster-proposal.md must cite ADR-0023 for the "
            "PC source-doc auto-add mechanism."
        )

    def test_reference_documents_pc_source_auto_add(
        self, repo_root: Path
    ) -> None:
        # The reference must document the H2 mechanism in prose, not
        # leave the placeholder.
        ref = repo_root / "references" / "pc-roster-proposal.md"
        content = ref.read_text(encoding="utf-8")
        # H1's placeholder text is gone; H2's mechanism prose is in.
        assert (
            "PC source: <slug>" in content or "PC source:" in content
        ), (
            "references/pc-roster-proposal.md must document the "
            "`PC source: <slug>` classification mechanism."
        )
        # The H2 section "Auto-add from `PC source:` docs — mechanics"
        # exists somewhere in the reference.
        assert "Auto-add from" in content or "auto-add" in content.lower(), (
            "references/pc-roster-proposal.md must document the auto-add "
            "behavior into `## Auto-added from PC source: docs`."
        )
