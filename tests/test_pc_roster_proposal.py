"""Reference-Python coverage of the PC roster proposal spec.

This file follows the v0.1 test convention: the reference Python below
is a thin near-translation of the PC roster proposal algorithm that
`references/pc-roster-proposal.md` documents at runtime. The reference
impl is **not** a runtime helper — skills follow the prose in
`pc-roster-proposal.md` directly. The tests exist so the spec and the
per-skill prose can't silently drift apart: any change to the documented
algorithm must land in both the reference and this file, and the tests
catch mismatches.

Per [ADR-0018](../docs/adr/0018-pc-roster-as-survey-deliverable.md), the
PC roster is a Phase 2 (Survey) deliverable. The proposal aggregates
skim signals across the corpus, classifies candidates as "Likely PC" or
"Possible NPC", writes `.ttrpg-staging/survey-pcs.md` as the GM review
surface, parses the GM-edited roster back, and promotes surviving
entries to `pcs/<slug>.md` stubs (with a collision check against
existing PC files).

The four operations covered here mirror the four contract pieces of the
proposal:

  - **`classify_candidates`** — given per-doc skim signals (frequency,
    explicit-roster hits, party-pronoun hits, aliases captured), classify
    each candidate as "Likely PC" or "Possible NPC" per the rules.
  - **`render_survey_pcs_md`** — render the candidate set as the staged
    file shape documented in pc-roster-proposal.md, including the empty
    state.
  - **`parse_survey_pcs_md`** — parse a GM-edited staged file back into
    the surviving roster (slug, optional one-line body, aliases).
  - **`stage_and_promote_stubs`** — stage `.ttrpg-staging/pcs/<slug>.md`
    stubs, refuse promotion on collision with an existing `pcs/<slug>.md`,
    and promote successfully when no collision exists.

The reference impl mirrors what `references/pc-roster-proposal.md` and
`skills/ingest/SKILL.md` Phase 2 Step 2.5 + Step 5 document; if the prose
and this file diverge, one of them is wrong.

This slice (B2) is the structural extraction only — zero behavior
change. The current skim-based candidate detection is preserved
verbatim. The mechanism refinement (drop skim inference, add
existing-`pcs/` enumeration, GM-typed-adds zone) ships in slice H1 as
the ADR-0018 supersession.
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


@dataclass
class CandidateSignals:
    """Per-candidate aggregated skim signals for one input corpus.

    Aggregated across all docs in the input directory before
    classification, per pc-roster-proposal.md "Aggregation and candidate
    classification."
    """

    name: str
    doc_count: int = 0
    explicit_roster_hit: bool = False
    party_pronoun_hit: bool = False
    aliases: list[str] = field(default_factory=list)


@dataclass
class ClassifiedCandidate:
    """One candidate after classification — what gets rendered to the staged file."""

    slug: str
    canonical_name: str
    doc_count: int
    classification: str  # "Likely PC" or "Possible NPC"
    aliases: list[str] = field(default_factory=list)
    annotation_detail: str = ""  # e.g., "session logs 1, 3, 5, 7, 9"
    extra_label: str = ""  # e.g., "(one-off mention)" or "alias"


def classify_candidates(
    signals: list[CandidateSignals],
) -> list[ClassifiedCandidate]:
    """Aggregate skim signals and classify per pc-roster-proposal.md.

    Classification rule (verbatim from the reference):
      - "Likely PC" — appears in multiple docs as an actor, named under
        an explicit roster heading, or named in proximity to "the party"
        / "the PCs" patterns.
      - "Possible NPC" — appears once, in a one-off mention, or in a
        pattern that reads more like NPC framing than PC framing. The
        candidate is still surfaced; the label tells the GM where the
        agent leaned.
    """
    classified: list[ClassifiedCandidate] = []
    for sig in signals:
        if (
            sig.explicit_roster_hit
            or sig.doc_count >= 2
            or sig.party_pronoun_hit
        ):
            label = "Likely PC"
        else:
            label = "Possible NPC"
        classified.append(
            ClassifiedCandidate(
                slug=slugify(sig.name),
                canonical_name=sig.name,
                doc_count=sig.doc_count,
                classification=label,
                aliases=list(sig.aliases),
            )
        )
    return classified


# ---------------------------------------------------------------------------
# Staged file rendering and parsing.
# ---------------------------------------------------------------------------


SURVEY_PCS_HEADER = """# Survey: proposed PC roster

Edit this list — confirm, rename, remove, or add. Names not in this list will
be treated as NPC candidates in Phase 3 (with a safety-net ASK at per-doc
review for any unknown named character). Empty the list if you have no PCs to
add yet — you can add them later by re-running `/ingest` against a PC-roster
doc or by hand-editing `pcs/`.

To add a PC: add a new line with the slug. Optional one-line description
after a tab or two spaces becomes the stub file's body. Nicknames go in
`— alias: <name>` suffixes (multiple aliases comma-separated).

"""


SURVEY_PCS_EMPTY_BODY = (
    "(No PC candidates surfaced from the skim. Add PC slugs here as needed — one\n"
    "per line, optional `— alias: <nickname>` suffix — or leave empty and add PCs\n"
    "later by hand-editing `pcs/` or running `/ingest` against a PC-roster doc.)\n"
)


def render_survey_pcs_md(candidates: list[ClassifiedCandidate]) -> str:
    """Render `.ttrpg-staging/survey-pcs.md` per pc-roster-proposal.md.

    The header is fixed prose; each candidate is one line with the slug,
    a frequency annotation, classification, and any `— alias:` suffix.
    Empty rosters render the empty-state body instead of the candidate
    block.
    """
    if not candidates:
        return SURVEY_PCS_HEADER.rstrip() + "\n\n" + SURVEY_PCS_EMPTY_BODY
    lines: list[str] = []
    for c in candidates:
        # Frequency annotation: "appears in N docs" with an optional
        # detail (e.g., "session logs 1, 3, 5") if the agent captured one.
        if c.doc_count == 1:
            freq = "appears in 1 doc"
        else:
            freq = f"appears in {c.doc_count} docs"
        if c.annotation_detail:
            freq = f"{freq} ({c.annotation_detail})"
        # Classification suffix.
        cls = c.classification
        if c.extra_label:
            cls = f"{cls} ({c.extra_label})"
        line = f"{c.slug}         — {freq}. {cls}."
        if c.aliases:
            line += f" — alias: {', '.join(c.aliases)}"
        lines.append(line)
    return SURVEY_PCS_HEADER + "\n".join(lines) + "\n"


@dataclass
class ParsedRosterEntry:
    """A surviving PC entry after the GM's review.

    Per pc-roster-proposal.md "Parsing the GM-edited roster," each
    non-comment, non-header line yields one entry with the slug, an
    optional one-line body, and aliases parsed from any `— alias:` suffix.
    """

    slug: str
    body: str = ""
    aliases: list[str] = field(default_factory=list)


# Lines starting with `#` are headers/comments per the staged-file
# convention. The empty-state line starts with `(No PC candidates ...`
# and must also be ignored on parse.
_HEADER_PREFIX = "#"
_EMPTY_STATE_PREFIX = "(No PC candidates"
# A line that contains "appears in" is one the agent rendered — the
# "frequency annotation" prefix marks an agent-authored entry, where
# anything after a dash-separated annotation is metadata, not body.
_FREQ_ANNOTATION_MARKER = re.compile(r"\s+—\s+appears in\s+\d+\s+doc")
# `— alias:` suffix can carry one or more comma-separated aliases.
_ALIAS_SUFFIX = re.compile(r"—\s*alias:\s*(.+?)\s*$", re.IGNORECASE)


def parse_survey_pcs_md(content: str) -> list[ParsedRosterEntry]:
    """Parse the GM-edited `.ttrpg-staging/survey-pcs.md` back to entries.

    The staged file has a fixed structure: an `# H1` header line, then
    fixed instructional contract prose, then a blank line, then the
    entry block (one entry per line) or the empty-state body line.

    The parser strips the known header prefix (everything up to and
    including the final blank line that follows the contract prose),
    then walks the remaining body line by line. Each non-empty
    non-empty-state line is an entry; parse slug + body + aliases per
    the reference.

    Returns [] when the roster is empty (no entries after the header).
    """
    body = _strip_header_prefix(content)

    entries: list[ParsedRosterEntry] = []
    in_empty_state = False
    for raw in body.splitlines():
        stripped = raw.strip()
        if not stripped:
            # A blank line ends the empty-state block; subsequent lines
            # (if any) are GM-added entries.
            in_empty_state = False
            continue
        if in_empty_state:
            # Inside the multi-line empty-state parenthetical; skip.
            continue
        if stripped.startswith(_HEADER_PREFIX):
            # Defensive: stray header line in the body shouldn't happen.
            continue
        if stripped.startswith(_EMPTY_STATE_PREFIX):
            # Empty-state body line; skip this and the rest of the
            # parenthetical block until a blank line.
            in_empty_state = True
            continue

        line_to_parse = stripped

        # Extract aliases from the `— alias: ...` suffix if present.
        aliases: list[str] = []
        alias_match = _ALIAS_SUFFIX.search(line_to_parse)
        if alias_match:
            alias_str = alias_match.group(1)
            aliases = [a.strip() for a in alias_str.split(",") if a.strip()]
            # Strip the alias suffix off the line for further parsing.
            line_to_parse = line_to_parse[: alias_match.start()].rstrip(" —")

        # Strip the frequency/classification annotation if the agent
        # rendered one. The annotation begins at " — appears in N docs"
        # and runs to the end of the line.
        freq_match = _FREQ_ANNOTATION_MARKER.search(line_to_parse)
        if freq_match:
            line_before_annotation = line_to_parse[: freq_match.start()].rstrip()
        else:
            line_before_annotation = line_to_parse

        # The remaining content is "<slug>[<whitespace><optional body>]"
        # or just "<slug or name>" (a bare GM addition that may be a
        # plain name with spaces).
        parts = re.split(r"[\t ]{2,}|\t", line_before_annotation, maxsplit=1)
        slug_token = parts[0].strip()
        body_text = parts[1].strip() if len(parts) > 1 else ""

        # Slugify the slug token per the dedup-matching rule. A GM-typed
        # plain name (e.g., "The Shadow") slugifies to "shadow"; an
        # agent-rendered slug (e.g., "silas") slugifies to itself.
        slug = slugify(slug_token)

        if not slug:
            # Defensive: the line had no slug content (shouldn't happen
            # but skip rather than emit a bad entry).
            continue

        entries.append(
            ParsedRosterEntry(slug=slug, body=body_text, aliases=aliases)
        )
    return entries


def _strip_header_prefix(content: str) -> str:
    """Return the entry block — everything after the contract prose.

    The header is the fixed prose `SURVEY_PCS_HEADER` defined above. If
    the file's content starts with that exact prefix (the agent wrote
    it, the GM may have edited the entries below it but normally
    doesn't touch the contract prose), strip it. If the prefix is not
    an exact match (GM edited the contract prose, or the file is
    malformed), fall back to a structural strip: drop the `# H1`, drop
    any lines that look like contract prose (long lines containing
    backticks, parentheses, or terminal punctuation), keep entry-shaped
    lines.
    """
    if content.startswith(SURVEY_PCS_HEADER):
        return content[len(SURVEY_PCS_HEADER):]

    # Fallback: drop the `# H1` line and any prose paragraphs.
    lines = content.splitlines(keepends=True)
    body_start = 0
    seen_blank_after_prose = False
    saw_any_prose = False
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            if saw_any_prose:
                # Mark the first blank after prose as the boundary.
                seen_blank_after_prose = True
                body_start = i + 1
            else:
                body_start = i + 1
            continue
        if stripped.startswith(_HEADER_PREFIX):
            body_start = i + 1
            continue
        if _is_contract_prose_line(stripped):
            saw_any_prose = True
            seen_blank_after_prose = False
            body_start = i + 1
            continue
        # First non-prose, non-header, non-blank line: this is the start
        # of the entry block.
        break
    return "".join(lines[body_start:])


def _is_contract_prose_line(line: str) -> bool:
    """Heuristic: a contract prose line wraps English text.

    The reference's header contains backticks, parentheses, English
    sentences. Entry lines don't.
    """
    # Backticks and parentheses appear only in contract prose, never in
    # an entry line.
    if "`" in line or "(" in line or ")" in line:
        return True
    # An entry line either contains the " — appears in N doc" annotation
    # or is a short bare slug/name. Long prose lines (more than ~6
    # tokens with no em-dash slug-prefix) are contract prose.
    if "—" in line:
        # If it's the agent-rendered entry shape, the first token is a
        # slug. Otherwise it's contract prose using em-dash punctuation.
        first = line.split()[0]
        return not bool(re.fullmatch(r"[a-z0-9][a-z0-9\-]*", first))
    tokens = line.split()
    if len(tokens) > 6:
        return True
    return False


# ---------------------------------------------------------------------------
# Stub staging and promotion to `pcs/<slug>.md`.
# ---------------------------------------------------------------------------


@dataclass
class StubPromotionResult:
    """What happened during staging + promotion."""

    promoted: list[str] = field(default_factory=list)  # final paths
    collisions: list[str] = field(default_factory=list)  # blocked slugs


def render_pc_stub(entry: ParsedRosterEntry) -> str:
    """Render a `pcs/<slug>.md` stub per pc-roster-proposal.md.

    Frontmatter:
      kind: pc
      aliases: [...]   (omitted entirely if none)

    Body: H1 (canonical-name form of the slug, or GM-supplied name) plus
    optional one-line description body if the GM enriched the annotation.
    """
    fm_lines = ["---", "kind: pc"]
    if entry.aliases:
        # Inline list shape matches the example in the reference.
        fm_lines.append(f"aliases: [{', '.join(entry.aliases)}]")
    fm_lines.append("---")
    fm = "\n".join(fm_lines)

    # Canonical name from the slug: title-case each hyphen-separated
    # token. (`silas` → `Silas`, `the-shadow` → `The Shadow`.) This is
    # what the reference calls "the prose-readable form of the slug" for
    # the default case where the GM didn't supply an explicit canonical.
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

    Per pc-roster-proposal.md "Collision check before promotion":
      - Stage every stub before promoting any.
      - If any slug collides with an existing `pcs/<slug>.md`, STOP and
        record the collision. Don't silently overwrite.
      - On clean staging, promote each stub to `pcs/<slug>.md`, delete
        the staged copy, and remove `.ttrpg-staging/pcs/` if it's empty.

    If the roster is empty, this is a no-op — no stubs to write, no
    directories to create.
    """
    result = StubPromotionResult()
    if not entries:
        return result

    staging_dir = campaign_root / ".ttrpg-staging" / "pcs"
    pcs_dir = campaign_root / "pcs"

    # Stage every stub first.
    staging_dir.mkdir(parents=True, exist_ok=True)
    staged_paths: list[Path] = []
    for entry in entries:
        staged_path = staging_dir / f"{entry.slug}.md"
        staged_path.write_text(render_pc_stub(entry), encoding="utf-8")
        staged_paths.append(staged_path)

    # Collision check: any slug whose live `pcs/<slug>.md` already
    # exists blocks promotion. STOP — leave staged stubs in place so the
    # GM can inspect them.
    for entry in entries:
        live_path = pcs_dir / f"{entry.slug}.md"
        if live_path.exists():
            result.collisions.append(entry.slug)

    if result.collisions:
        return result

    # Promote each staged stub to `pcs/<slug>.md`, deleting the staged
    # copy after each move.
    pcs_dir.mkdir(parents=True, exist_ok=True)
    for staged_path in staged_paths:
        live_path = pcs_dir / staged_path.name
        live_path.write_text(staged_path.read_text(encoding="utf-8"), encoding="utf-8")
        staged_path.unlink()
        result.promoted.append(str(live_path.relative_to(campaign_root)))

    # Remove `.ttrpg-staging/pcs/` if it's now empty.
    try:
        staging_dir.rmdir()
    except OSError:
        # Not empty — leave it alone (the staging-pattern reference says
        # other staging content may coexist).
        pass

    return result


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSlugify:
    """The slug rule borrowed from dedup-matching.md."""

    def test_lowercases_and_hyphenates(self) -> None:
        assert slugify("Silas Stoneforge") == "silas-stoneforge"

    def test_strips_leading_the(self) -> None:
        assert slugify("The Shadow") == "shadow"

    def test_collapses_runs_of_non_alnum(self) -> None:
        assert slugify("Café  du   Monde!") == "cafe-du-monde"


class TestClassifyCandidates:
    """Aggregation and Likely-PC / Possible-NPC classification."""

    def test_multi_doc_actor_is_likely_pc(self) -> None:
        sig = CandidateSignals(name="Silas", doc_count=5)
        [c] = classify_candidates([sig])
        assert c.classification == "Likely PC"
        assert c.slug == "silas"
        assert c.canonical_name == "Silas"

    def test_explicit_roster_hit_promotes_to_likely_pc_regardless_of_frequency(
        self,
    ) -> None:
        # Even a once-mentioned candidate is a Likely PC if the agent
        # caught them under an explicit roster heading.
        sig = CandidateSignals(
            name="Marisa", doc_count=1, explicit_roster_hit=True
        )
        [c] = classify_candidates([sig])
        assert c.classification == "Likely PC"

    def test_party_pronoun_proximity_is_likely_pc(self) -> None:
        # "the party — Marisa entered..." even on a single doc.
        sig = CandidateSignals(
            name="Marisa", doc_count=1, party_pronoun_hit=True
        )
        [c] = classify_candidates([sig])
        assert c.classification == "Likely PC"

    def test_single_doc_one_off_is_possible_npc(self) -> None:
        sig = CandidateSignals(name="Maren", doc_count=1)
        [c] = classify_candidates([sig])
        assert c.classification == "Possible NPC"

    def test_aliases_carry_through(self) -> None:
        sig = CandidateSignals(
            name="Helerel", doc_count=3, aliases=["Helly"]
        )
        [c] = classify_candidates([sig])
        assert c.aliases == ["Helly"]


class TestRenderSurveyPcsMd:
    """The `.ttrpg-staging/survey-pcs.md` shape."""

    def test_header_is_present(self) -> None:
        rendered = render_survey_pcs_md([])
        assert rendered.startswith("# Survey: proposed PC roster")

    def test_empty_roster_renders_empty_state_body(self) -> None:
        rendered = render_survey_pcs_md([])
        assert "(No PC candidates surfaced from the skim." in rendered

    def test_candidate_line_includes_slug_freq_and_classification(self) -> None:
        candidates = [
            ClassifiedCandidate(
                slug="silas",
                canonical_name="Silas",
                doc_count=5,
                classification="Likely PC",
            )
        ]
        rendered = render_survey_pcs_md(candidates)
        assert "silas" in rendered
        assert "appears in 5 docs" in rendered
        assert "Likely PC" in rendered

    def test_alias_renders_as_em_dash_suffix(self) -> None:
        candidates = [
            ClassifiedCandidate(
                slug="helerel",
                canonical_name="Helerel",
                doc_count=3,
                classification="Likely PC",
                aliases=["Helly"],
            )
        ]
        rendered = render_survey_pcs_md(candidates)
        assert "— alias: Helly" in rendered

    def test_singular_doc_count_uses_singular_noun(self) -> None:
        candidates = [
            ClassifiedCandidate(
                slug="maren",
                canonical_name="Maren",
                doc_count=1,
                classification="Possible NPC",
            )
        ]
        rendered = render_survey_pcs_md(candidates)
        assert "appears in 1 doc" in rendered


class TestParseSurveyPcsMd:
    """Round-trip the staged file back into surviving entries."""

    def test_skips_header_and_empty_state(self) -> None:
        empty = render_survey_pcs_md([])
        assert parse_survey_pcs_md(empty) == []

    def test_parses_agent_rendered_entry(self) -> None:
        rendered = render_survey_pcs_md(
            [
                ClassifiedCandidate(
                    slug="silas",
                    canonical_name="Silas",
                    doc_count=5,
                    classification="Likely PC",
                )
            ]
        )
        [entry] = parse_survey_pcs_md(rendered)
        assert entry.slug == "silas"
        assert entry.aliases == []

    def test_parses_alias_suffix(self) -> None:
        rendered = render_survey_pcs_md(
            [
                ClassifiedCandidate(
                    slug="helerel",
                    canonical_name="Helerel",
                    doc_count=3,
                    classification="Likely PC",
                    aliases=["Helly"],
                )
            ]
        )
        [entry] = parse_survey_pcs_md(rendered)
        assert entry.slug == "helerel"
        assert entry.aliases == ["Helly"]

    def test_parses_multiple_comma_separated_aliases(self) -> None:
        # Hand-crafted GM-edited line per the reference's "(multiple
        # aliases comma-separated)" rule.
        content = (
            SURVEY_PCS_HEADER
            + "rae — appears in 5 docs. Likely PC. — alias: Raelyn, Rae the Sharp\n"
        )
        [entry] = parse_survey_pcs_md(content)
        assert entry.slug == "rae"
        assert entry.aliases == ["Raelyn", "Rae the Sharp"]

    def test_parses_bare_gm_typed_slug_with_no_annotation(self) -> None:
        # The GM hand-added a PC with just a slug, no annotation. The
        # reference's GM-typed-adds rule: slugify and accept.
        content = SURVEY_PCS_HEADER + "marisa\n"
        [entry] = parse_survey_pcs_md(content)
        assert entry.slug == "marisa"

    def test_slugifies_gm_typed_name_with_spaces(self) -> None:
        # GM types "Marisa" or some other free-form name; the reference
        # says "slugify the GM-supplied name per the dedup-matching rule
        # before recording."
        content = SURVEY_PCS_HEADER + "The Shadow\n"
        [entry] = parse_survey_pcs_md(content)
        assert entry.slug == "shadow"

    def test_empty_roster_after_gm_deletion_returns_no_entries(self) -> None:
        # GM emptied the roster — header survives, no entry lines.
        content = SURVEY_PCS_HEADER + "\n"
        assert parse_survey_pcs_md(content) == []


class TestStageAndPromoteStubs:
    """The Step 5a → 5b stub lifecycle."""

    def test_empty_roster_is_a_no_op(self, tmp_path: Path) -> None:
        result = stage_and_promote_stubs([], tmp_path)
        assert result.promoted == []
        assert result.collisions == []
        assert not (tmp_path / ".ttrpg-staging").exists()
        assert not (tmp_path / "pcs").exists()

    def test_promotes_stubs_when_no_collision(self, tmp_path: Path) -> None:
        entries = [
            ParsedRosterEntry(slug="silas"),
            ParsedRosterEntry(slug="rae"),
        ]
        result = stage_and_promote_stubs(entries, tmp_path)
        assert result.collisions == []
        assert sorted(result.promoted) == ["pcs/rae.md", "pcs/silas.md"]
        # Staged stubs deleted; staging dir gone if empty.
        assert not (tmp_path / ".ttrpg-staging" / "pcs").exists()
        # Live files present.
        assert (tmp_path / "pcs" / "silas.md").is_file()
        assert (tmp_path / "pcs" / "rae.md").is_file()

    def test_stub_has_kind_pc_frontmatter(self, tmp_path: Path) -> None:
        stage_and_promote_stubs(
            [ParsedRosterEntry(slug="silas")], tmp_path
        )
        content = (tmp_path / "pcs" / "silas.md").read_text(encoding="utf-8")
        # Frontmatter block.
        assert content.startswith("---\nkind: pc\n")
        # H1 title-cased from the slug.
        assert "# Silas" in content

    def test_stub_renders_aliases_when_present(self, tmp_path: Path) -> None:
        stage_and_promote_stubs(
            [ParsedRosterEntry(slug="helerel", aliases=["Helly"])], tmp_path
        )
        content = (tmp_path / "pcs" / "helerel.md").read_text(encoding="utf-8")
        assert "aliases: [Helly]" in content

    def test_stub_omits_aliases_key_when_none(self, tmp_path: Path) -> None:
        # Per the reference: "If there are no aliases, omit the key
        # entirely."
        stage_and_promote_stubs(
            [ParsedRosterEntry(slug="silas")], tmp_path
        )
        content = (tmp_path / "pcs" / "silas.md").read_text(encoding="utf-8")
        assert "aliases:" not in content

    def test_stub_body_includes_gm_one_line_description(
        self, tmp_path: Path
    ) -> None:
        stage_and_promote_stubs(
            [
                ParsedRosterEntry(
                    slug="silas",
                    body="dwarven blacksmith turned reluctant adventurer",
                )
            ],
            tmp_path,
        )
        content = (tmp_path / "pcs" / "silas.md").read_text(encoding="utf-8")
        assert "dwarven blacksmith turned reluctant adventurer" in content

    def test_collision_with_existing_pcs_file_stops_promotion(
        self, tmp_path: Path
    ) -> None:
        # Pre-existing PC file in the campaign repo. The reference says:
        # "STOP and surface the collision."
        pcs_dir = tmp_path / "pcs"
        pcs_dir.mkdir()
        existing = pcs_dir / "silas.md"
        existing.write_text("---\nkind: pc\n---\n\n# Silas\n\nGM-authored.\n")
        existing_content = existing.read_text(encoding="utf-8")

        entries = [
            ParsedRosterEntry(slug="silas"),
            ParsedRosterEntry(slug="rae"),
        ]
        result = stage_and_promote_stubs(entries, tmp_path)

        # Collision recorded; nothing promoted.
        assert "silas" in result.collisions
        assert result.promoted == []
        # Existing GM-authored file untouched.
        assert existing.read_text(encoding="utf-8") == existing_content
        # `rae.md` was NOT promoted because the reference says "stage
        # every stub before promoting any" — collision blocks the whole
        # promotion. The staged stubs remain for GM inspection.
        assert not (pcs_dir / "rae.md").exists()
        assert (tmp_path / ".ttrpg-staging" / "pcs" / "silas.md").is_file()
        assert (tmp_path / ".ttrpg-staging" / "pcs" / "rae.md").is_file()


class TestReferenceFileExistsAndCitesADR:
    """Spec-drift safety net: the reference itself must exist and cite ADR-0018."""

    def test_reference_file_exists(self, repo_root: Path) -> None:
        ref = repo_root / "references" / "pc-roster-proposal.md"
        assert ref.is_file(), (
            "references/pc-roster-proposal.md is the shared spec consumed "
            "by /ingest and /init-campaign (docs mode); the reference impl "
            "in this test mirrors its prose. The file is missing."
        )

    def test_reference_cites_adr_0018(self, repo_root: Path) -> None:
        ref = repo_root / "references" / "pc-roster-proposal.md"
        content = ref.read_text(encoding="utf-8")
        assert "0018-pc-roster-as-survey-deliverable" in content, (
            "references/pc-roster-proposal.md must cite ADR-0018 — it is "
            "the architectural decision the reference implements."
        )

    def test_ingest_skill_md_cites_reference(self, repo_root: Path) -> None:
        skill = repo_root / "skills" / "ingest" / "SKILL.md"
        content = skill.read_text(encoding="utf-8")
        assert "references/pc-roster-proposal.md" in content, (
            "skills/ingest/SKILL.md must cite references/pc-roster-proposal.md "
            "from Phase 2 Step 2.5 per slice B2 of the v0.3 modularization."
        )
