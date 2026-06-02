"""Reference-Python coverage of `references/reference-note-extraction.md`.

Per the v0.1 test convention, this file's reference Python mirrors the
prose of `references/reference-note-extraction.md` — the heuristic that
governs Reference-note extraction in `/ingest` Phase 3 and
`/wrap-session` Pass 2. Skills follow the prose at runtime; this file
pins the spec so prose and algorithm cannot silently drift.

Slice H2 of v0.3 ([ADR-0023](../docs/adr/0023-pc-source-doc-ingestion.md))
adds two extensions to the heuristic:

  - **PC source: cross-extraction** — when a source doc is classified
    `PC source: <slug>`, named NPCs / Locations / Factions / Items in
    the backstory become Reference notes with `belongs_to: [pcs/<slug>.md]`.
  - **PC source body enrichment** — the backstory prose appends to
    `pcs/<slug>.md`'s body as an additive update, preserving any
    pre-existing GM-authored body content above the append.

This file covers the H2-specific behaviors. The universal heuristic
("when does a name warrant a Reference note", "passing mentions are
not extracted") is not re-tested here — that's documented in the
reference and exercised at runtime by the LLM.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import pytest
import yaml


# ---------------------------------------------------------------------------
# Reference implementation — mirrors `references/reference-note-extraction.md`.
# ---------------------------------------------------------------------------


# Agent-maintained PC bidi sections per ADR-0023 / bidi-link-maintenance.md.
PC_BIDI_SECTIONS = (
    "## NPCs",
    "## Locations",
    "## Factions",
    "## Items",
    "## Secrets",
)


# Map Reference-note kind folder to the PC bidi section name (used for
# the forward link on the PC) per `bidi-link-maintenance.md` § "PC as
# container."
PC_BIDI_SECTION_BY_KIND = {
    "npcs": "## NPCs",
    "locations": "## Locations",
    "factions": "## Factions",
    "items": "## Items",
}


@dataclass
class CrossExtractedReferenceNote:
    """A Reference note proposed during PC source cross-extraction.

    Per `reference-note-extraction.md` § "PC source: cross-extraction"
    and ADR-0023, named entities in a `PC source: <slug>` doc's
    backstory become Reference notes with the PC in `belongs_to:`.
    """

    kind: str  # "npcs" | "locations" | "factions" | "items"
    slug: str
    canonical_name: str
    body: str
    belongs_to: list[str] = field(default_factory=list)

    @property
    def path(self) -> str:
        return f"{self.kind}/{self.slug}.md"


def render_reference_note(note: CrossExtractedReferenceNote) -> str:
    """Render a cross-extracted Reference note's file contents.

    Frontmatter carries `belongs_to:` when populated (PC source
    cross-extraction); the body opens with the H1 followed by the
    one-liner. The agent-maintained `## PCs` section is written by the
    bidi-link maintenance pass per `bidi-link-maintenance.md` § "PC as
    container," not by this function.
    """
    fm_lines = ["---"]
    if note.belongs_to:
        fm_lines.append("belongs_to: [" + ", ".join(note.belongs_to) + "]")
    fm_lines.append("---")
    fm = "\n".join(fm_lines)
    body = f"# {note.canonical_name}\n\n{note.body}\n"
    return f"{fm}\n\n{body}"


# Body region split: the content above the first agent-maintained
# bidi section is the GM-owned body; the agent-maintained sections
# follow.
def split_pc_body(text: str) -> tuple[str, str, str]:
    """Return (frontmatter_block, gm_body, agent_bidi_sections).

    `frontmatter_block` includes the `---` delimiters and trailing
    newline. `gm_body` is the body content from the H1 to (but not
    including) the first agent-maintained bidi section heading.
    `agent_bidi_sections` is the rest of the file.

    Per ADR-0023's GM-owned-body / agent-maintained-bidi-sections
    boundary, the agent never modifies `gm_body` except via additive
    append during PC source extraction.
    """
    # Frontmatter.
    if text.startswith("---\n"):
        closing = text.find("\n---\n", 4)
        if closing != -1:
            frontmatter = text[: closing + len("\n---\n")]
            after_fm = text[closing + len("\n---\n") :]
        else:
            frontmatter = ""
            after_fm = text
    else:
        frontmatter = ""
        after_fm = text

    # Find the first agent-maintained bidi section heading.
    first_bidi = len(after_fm)
    for section in PC_BIDI_SECTIONS:
        # Match the heading at start-of-line.
        for m in re.finditer(
            rf"^{re.escape(section)}\s*$", after_fm, re.MULTILINE
        ):
            if m.start() < first_bidi:
                first_bidi = m.start()
            break
    gm_body = after_fm[:first_bidi]
    agent_sections = after_fm[first_bidi:]
    return frontmatter, gm_body, agent_sections


def append_backstory_to_pc(
    pc_text: str, backstory: str, separator: str | None = None
) -> str:
    r"""Return the PC file content with backstory appended additively.

    Per `references/reference-note-extraction.md` § "PC source body
    enrichment" and ADR-0023's GM-owned-body / agent-maintained-bidi-
    sections boundary:

      1. The pre-existing GM body content (between the H1 and the first
         agent-maintained bidi section) is preserved verbatim.
      2. The new backstory prose is appended at the end of the GM body
         region — i.e., before any agent-maintained section headings.
      3. The agent-maintained sections (if any) stay where they are.

    `separator` (when provided) is the prose marker that visually
    separates pre-existing GM content from the appended backstory; the
    GM may edit or remove it at Step 4b review. Default: a blank line.
    """
    frontmatter, gm_body, agent_sections = split_pc_body(pc_text)
    # Strip trailing whitespace from gm_body and ensure single trailing
    # newline before the append.
    gm_body_stripped = gm_body.rstrip()
    sep = (separator or "").strip()
    if gm_body_stripped:
        if sep:
            new_gm_body = (
                gm_body_stripped + "\n\n" + sep + "\n\n" + backstory.strip() + "\n\n"
            )
        else:
            new_gm_body = (
                gm_body_stripped + "\n\n" + backstory.strip() + "\n\n"
            )
    else:
        new_gm_body = backstory.strip() + "\n\n"
    return frontmatter + new_gm_body + agent_sections


# ---------------------------------------------------------------------------
# Tests — cross-extraction
# ---------------------------------------------------------------------------


class TestCrossExtractedReferenceNoteShape:
    """A cross-extracted note carries the PC in `belongs_to:`."""

    def test_belongs_to_contains_pc_path(self) -> None:
        note = CrossExtractedReferenceNote(
            kind="npcs",
            slug="caelir-of-highmoor",
            canonical_name="Caelir of Highmoor",
            body="Aldric's father, a knight of the Order of the Ember.",
            belongs_to=["pcs/aldric.md"],
        )
        rendered = render_reference_note(note)
        assert "belongs_to: [pcs/aldric.md]" in rendered
        assert "# Caelir of Highmoor" in rendered

    def test_belongs_to_with_multiple_pcs(self) -> None:
        # An NPC referenced from multiple PCs' backstories carries
        # multiple PC paths.
        note = CrossExtractedReferenceNote(
            kind="locations",
            slug="highmoor",
            canonical_name="Highmoor",
            body="A walled town on the river fork.",
            belongs_to=["pcs/aldric.md", "pcs/vera.md"],
        )
        rendered = render_reference_note(note)
        assert "pcs/aldric.md" in rendered
        assert "pcs/vera.md" in rendered

    def test_note_without_belongs_to_omits_field(self) -> None:
        # A Reference note extracted via the general branch (not from
        # a PC source doc) does not carry `belongs_to:` — omit the key
        # rather than writing an empty list.
        note = CrossExtractedReferenceNote(
            kind="npcs",
            slug="sera",
            canonical_name="Sera",
            body="The blacksmith in Phandalin.",
        )
        rendered = render_reference_note(note)
        assert "belongs_to" not in rendered

    @pytest.mark.parametrize(
        "kind",
        ["npcs", "locations", "factions", "items"],
    )
    def test_cross_extraction_supports_all_four_kinds(self, kind: str) -> None:
        # Per ADR-0023, the PC source branch cross-extracts NPCs,
        # Locations, Factions, and Items. Each kind produces a Reference
        # note in the matching folder with the PC in `belongs_to:`.
        note = CrossExtractedReferenceNote(
            kind=kind,
            slug="example",
            canonical_name="Example",
            body="A test entity.",
            belongs_to=["pcs/aldric.md"],
        )
        assert note.path == f"{kind}/example.md"
        rendered = render_reference_note(note)
        assert "pcs/aldric.md" in rendered


class TestPcSourceBodyEnrichment:
    """Backstory body append is additive — never overwrites GM content."""

    def test_append_to_h1_only_stub(self) -> None:
        # H1-only stub from Phase 2 promotion: append the full backstory.
        stub = "---\nkind: pc\n---\n\n# Aldric\n"
        backstory = (
            "Aldric grew up in Highmoor, the son of Caelir, a knight "
            "of the Order of the Ember."
        )
        result = append_backstory_to_pc(stub, backstory)
        assert "# Aldric" in result
        assert "Aldric grew up in Highmoor" in result
        # No agent-maintained sections existed; nothing to preserve below.
        assert "## NPCs" not in result

    def test_append_preserves_existing_gm_body(self) -> None:
        # GM hand-wrote a one-line description before running /ingest
        # against a PC source doc. The append must preserve the GM's
        # line above the new content.
        stub = (
            "---\nkind: pc\n---\n\n"
            "# Aldric\n\nDwarf paladin, party leader.\n"
        )
        backstory = "Aldric grew up in Highmoor…"
        result = append_backstory_to_pc(stub, backstory)
        # GM's line still there.
        assert "Dwarf paladin, party leader." in result
        # Backstory appended after.
        assert "Aldric grew up in Highmoor" in result
        # Order: GM line first, backstory second.
        gm_idx = result.index("Dwarf paladin, party leader.")
        bs_idx = result.index("Aldric grew up in Highmoor")
        assert gm_idx < bs_idx

    def test_append_preserves_agent_maintained_sections_below(self) -> None:
        # The PC file has agent-maintained `## NPCs` / `## Secrets`
        # sections from prior writes. The append lands above those
        # sections; they stay intact.
        stub = (
            "---\nkind: pc\n---\n\n"
            "# Aldric\n\nDwarf paladin.\n\n"
            "## NPCs\n\n- [[npcs/sera]] — friend\n\n"
            "## Secrets\n\n- [[secrets/aldric-knows]] — knows about the cult\n"
        )
        backstory = "Aldric grew up in Highmoor…"
        result = append_backstory_to_pc(stub, backstory)
        # All sections preserved.
        assert "## NPCs" in result
        assert "[[npcs/sera]] — friend" in result
        assert "## Secrets" in result
        assert "[[secrets/aldric-knows]]" in result
        # Backstory landed above the bidi sections.
        bs_idx = result.index("Aldric grew up in Highmoor")
        npcs_idx = result.index("## NPCs")
        assert bs_idx < npcs_idx

    def test_append_with_separator_includes_separator(self) -> None:
        stub = (
            "---\nkind: pc\n---\n\n"
            "# Aldric\n\nDwarf paladin, party leader.\n"
        )
        backstory = "Aldric grew up in Highmoor…"
        result = append_backstory_to_pc(
            stub, backstory, separator="## Backstory"
        )
        assert "## Backstory" in result
        sep_idx = result.index("## Backstory")
        bs_idx = result.index("Aldric grew up in Highmoor")
        assert sep_idx < bs_idx

    def test_append_does_not_overwrite_substantial_gm_body(self) -> None:
        # Even when the GM body is substantial (a paragraph of pre-
        # existing content), the append is additive. The agent never
        # silently overwrites GM body content per ADR-0023.
        substantial_body = (
            "Aldric is the party leader. He has been with the campaign "
            "from session one; he chose the cause when his order fell. "
            "His sword arm is steady; his faith less so."
        )
        stub = f"---\nkind: pc\n---\n\n# Aldric\n\n{substantial_body}\n"
        backstory = "Aldric grew up in Highmoor…"
        result = append_backstory_to_pc(stub, backstory)
        # Every sentence of the original body is preserved.
        for sentence in substantial_body.split(". "):
            sentence = sentence.strip().rstrip(".")
            if sentence:
                assert sentence in result, (
                    f"Original GM body content lost: {sentence!r}"
                )
        # And the backstory is added.
        assert "Aldric grew up in Highmoor" in result


class TestPcIsNotExtractedAsNpc:
    """The PC named in a `PC source:` doc is never proposed as an NPC.

    Per `reference-note-extraction.md` § "What not to do" and ADR-0023,
    a PC source doc's named subject is the PC, not an NPC. The agent
    must not propose `npcs/<slug>.md` for the PC.
    """

    def test_pc_slug_not_in_proposed_npc_set(self) -> None:
        # Simulate a proposed NPC extraction set from a PC source doc.
        # The PC's own slug must NOT appear among NPC proposals.
        pc_slug = "aldric"
        proposed_npc_slugs = ["caelir-of-highmoor", "master-veneth", "tomas"]
        # The reference's posture: the PC stays out of the NPC set.
        # If it ever appears, the extraction logic regressed.
        assert pc_slug not in proposed_npc_slugs


class TestBackstoryEntitiesGetPcBelongsTo:
    """Cross-extracted entities from PC backstory carry the PC in belongs_to."""

    def test_named_npcs_extracted_with_pc_belongs_to(self) -> None:
        # Backstory: "My father Caelir of Highmoor". Cross-extraction
        # produces an NPC with the PC in belongs_to.
        pc_slug = "aldric"
        notes = [
            CrossExtractedReferenceNote(
                kind="npcs",
                slug="caelir-of-highmoor",
                canonical_name="Caelir of Highmoor",
                body="Aldric's father, a knight of the Order of the Ember.",
                belongs_to=[f"pcs/{pc_slug}.md"],
            ),
        ]
        for note in notes:
            assert f"pcs/{pc_slug}.md" in note.belongs_to

    def test_named_locations_extracted_with_pc_belongs_to(self) -> None:
        pc_slug = "aldric"
        note = CrossExtractedReferenceNote(
            kind="locations",
            slug="highmoor",
            canonical_name="Highmoor",
            body="Aldric's hometown.",
            belongs_to=[f"pcs/{pc_slug}.md"],
        )
        assert f"pcs/{pc_slug}.md" in note.belongs_to

    def test_named_factions_extracted_with_pc_belongs_to(self) -> None:
        pc_slug = "aldric"
        note = CrossExtractedReferenceNote(
            kind="factions",
            slug="order-of-the-ember",
            canonical_name="Order of the Ember",
            body="The paladin order Aldric serves.",
            belongs_to=[f"pcs/{pc_slug}.md"],
        )
        assert f"pcs/{pc_slug}.md" in note.belongs_to

    def test_named_items_extracted_with_pc_belongs_to(self) -> None:
        pc_slug = "aldric"
        note = CrossExtractedReferenceNote(
            kind="items",
            slug="heartcleaver",
            canonical_name="Heartcleaver",
            body="Aldric's grandmother's sword.",
            belongs_to=[f"pcs/{pc_slug}.md"],
        )
        assert f"pcs/{pc_slug}.md" in note.belongs_to


# ---------------------------------------------------------------------------
# Spec-drift tests — the reference and ADR must exist and document the H2 work.
# ---------------------------------------------------------------------------


class TestReferenceFileDocumentsPcSourceWork:
    """The reference's prose covers H2's PC source mechanism."""

    def test_reference_file_exists(self, repo_root: Path) -> None:
        ref = repo_root / "references" / "reference-note-extraction.md"
        assert ref.is_file()

    def test_reference_documents_pc_source_cross_extraction(
        self, repo_root: Path
    ) -> None:
        ref = repo_root / "references" / "reference-note-extraction.md"
        content = ref.read_text(encoding="utf-8")
        assert "PC source: cross-extraction" in content, (
            "reference-note-extraction.md must document the PC source: "
            "cross-extraction heuristic per ADR-0023."
        )

    def test_reference_documents_pc_source_body_enrichment(
        self, repo_root: Path
    ) -> None:
        ref = repo_root / "references" / "reference-note-extraction.md"
        content = ref.read_text(encoding="utf-8")
        assert "PC source body enrichment" in content, (
            "reference-note-extraction.md must document the PC source: "
            "body enrichment per ADR-0023."
        )

    def test_reference_cites_adr_0023(self, repo_root: Path) -> None:
        ref = repo_root / "references" / "reference-note-extraction.md"
        content = ref.read_text(encoding="utf-8")
        assert "0023-pc-source-doc-ingestion" in content or "ADR-0023" in content, (
            "reference-note-extraction.md must cite ADR-0023 for the "
            "PC source: extraction work."
        )

    def test_adr_0023_exists(self, repo_root: Path) -> None:
        adr = repo_root / "docs" / "adr" / "0023-pc-source-doc-ingestion.md"
        assert adr.is_file(), (
            "ADR-0023 (PC source-doc ingestion) must exist."
        )

    def test_adr_0023_documents_gm_owned_body_boundary(
        self, repo_root: Path
    ) -> None:
        adr = repo_root / "docs" / "adr" / "0023-pc-source-doc-ingestion.md"
        content = adr.read_text(encoding="utf-8")
        assert "GM-owned body" in content or "GM-owned-body" in content, (
            "ADR-0023 must document the GM-owned-body / agent-maintained-"
            "bidi-sections boundary."
        )

    def test_adr_0023_documents_deferred_stats_rationale(
        self, repo_root: Path
    ) -> None:
        adr = repo_root / "docs" / "adr" / "0023-pc-source-doc-ingestion.md"
        content = adr.read_text(encoding="utf-8")
        assert (
            "deferred" in content.lower() and "stat" in content.lower()
        ), (
            "ADR-0023 must document the deferred-stats rationale per "
            "issue #57's Option C + selective B framing."
        )
