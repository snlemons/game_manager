"""Behavioral tests for the `/init-campaign` skill (v0.3 slice D).

What these tests cover
----------------------
Issue #92 introduces `/init-campaign` as the bootstrapping front door for
net-new TTRPG campaigns per [ADR-0019](../docs/adr/0019-init-campaign-as-bootstrapping-front-door.md).
The slice-D scope is the from-scratch branch only:

  1. Steps 1-2 collect campaign name + system.
  2. Step 3 prompts the GM for from-scratch vs. docs; docs mode is
     deferred to slice E.
  3. Steps 4-6 are the from-scratch path: pitch elicitation via the
     shared conversational-refinement-loop, an optional PC roster step
     using the shared `pc-roster-proposal.md` reference's empty-roster
     skip path, and an optional first-Adventure sub-flow that composes
     `/init-adventure`'s in-campaign walkthrough as a continuation.
  4. Step 7 invokes the shared scaffolder reference.
  5. Step 8 promotes the pitch into `campaign.md` as a GM-authored
     opener block the composer preserves verbatim across regens, plus
     any PC stubs from Step 5.

The walkthrough itself (the conversational refinement loop) is LLM-
driven and not deterministic. These tests pin **structural shape**:

  * The SKILL.md exists at the conventional path with the right
    frontmatter.
  * The SKILL.md cites the shared references via relative paths (per
    #69's discipline; campaign-wide check in
    `test_plugin_manifest.py::TestRelativePathsInProse`; this file's
    check makes the failure mode local to `/init-campaign`).
  * The from-scratch branch's documented output layout (scaffolded
    campaign + opener-bracketed pitch in `campaign.md`) round-trips
    through a reference-impl writer + the composer-preservation rule
    documented in `references/campaign-overview-composer.md` under
    "GM-authored opener block preservation".
  * The empty-PC-roster skip path produces no `pcs/` directory per
    [ADR-0018](../docs/adr/0018-pc-roster-as-survey-deliverable.md).
  * The first-Adventure sub-flow composes structurally on top of the
    scaffolder + opener-block pitch, producing a campaign-shaped repo
    with one Adventure pre-populated (re-uses
    `test_init_adventure.write_initial_adventure_file` to model the
    sub-flow's Adventure-file output).
  * The composer's "GM-authored opener block preservation" rule:
    Given a `campaign.md` with a marker-bracketed opener block, the
    composer regen preserves the bytes between the markers verbatim
    while regenerating the agent-managed sections below.

These tests do not assert LLM-phrased text, specific pitch content, or
the conversational-refinement-loop's turn structure — those are
out-of-scope for reference-impl-style tests (per `tests/README.md`'s
"Why reference implementations, not real skill invocations?" section).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml


# Conventional path the skill ships at, per ADR-0013 (skills directory
# packaging) and the manifest auto-discovery contract.
SKILL_MD_PATH_RELATIVE: str = "skills/init-campaign/SKILL.md"


# The GM-authored opener block markers — load-bearing for the composer
# preservation rule documented in `references/campaign-overview-composer.md`.
# Exact byte-match strings; the composer's detection is literal-string
# based, not regex or fuzzy.
OPENER_START_MARKER: str = "<!-- gm-opener:start -->"
OPENER_END_MARKER: str = "<!-- gm-opener:end -->"


# --------------------------------------------------------------------------
# Helpers (mirror the helpers in sibling test modules for independence)
# --------------------------------------------------------------------------


def _split_frontmatter(text: str) -> tuple[dict, str]:
    """Split a markdown doc into (parsed-YAML-frontmatter, body).

    Mirrors the helper in `test_ingest_scaffolding.py` for independent
    test-file usability.
    """
    if not text.startswith("---\n"):
        return {}, text
    closing = text.find("\n---\n", 4)
    if closing == -1:
        return {}, text
    raw = text[4:closing]
    body = text[closing + len("\n---\n") :]
    parsed = yaml.safe_load(raw) or {}
    if not isinstance(parsed, dict):
        raise AssertionError(
            f"Frontmatter parsed to non-dict: {type(parsed).__name__}"
        )
    return parsed, body


def _slugify(name: str) -> str:
    """Slugify per `references/dedup-matching.md`'s normalization rule."""
    s = name.strip().lower()
    if s.startswith("the "):
        s = s[4:]
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = s.strip("-")
    return s


# --------------------------------------------------------------------------
# Reference-impl: insert the GM-authored opener into campaign.md.
# Mirrors SKILL.md Step 8 #1's Edit behavior.
# --------------------------------------------------------------------------


def insert_opener_block(
    *,
    campaign_md_path: Path,
    pitch_body: str,
) -> None:
    """Edit the GM-authored opener block into a scaffolded `campaign.md`.

    Mirrors `/init-campaign` SKILL.md Step 8 #1: read the scaffolder's
    placeholder, insert the marker-bracketed opener block between the
    `**System:**` header line and the first agent-managed section.

    The block uses the exact markers the composer recognizes:

        <!-- gm-opener:start -->

        <pitch body, no H1 — campaign.md's H1 is the header>

        <!-- gm-opener:end -->

    Per the composer reference's "GM-authored opener block preservation"
    section, the markers are detected by literal string match.
    """
    text = campaign_md_path.read_text(encoding="utf-8")
    # Anchor the insertion at the `**System:**` line's end (last header
    # bullet per `references/campaign-overview-composer.md` Header
    # section). Find the next blank line after it; the opener block
    # goes there.
    system_idx = text.find("- **System:**")
    if system_idx == -1:
        raise AssertionError(
            "Scaffolded campaign.md missing the `- **System:**` header "
            "line. Did the scaffolder run?"
        )
    eol = text.find("\n", system_idx)
    if eol == -1:
        raise AssertionError("Header line not terminated by a newline.")
    insertion_point = eol + 1  # after the newline of the System line

    block = (
        "\n"
        f"{OPENER_START_MARKER}\n"
        "\n"
        f"{pitch_body.strip()}\n"
        "\n"
        f"{OPENER_END_MARKER}\n"
    )

    new_text = text[:insertion_point] + block + text[insertion_point:]
    campaign_md_path.write_text(new_text, encoding="utf-8")


# --------------------------------------------------------------------------
# Reference-impl: composer regen that preserves the GM-authored opener.
# Mirrors `references/campaign-overview-composer.md` "GM-authored
# opener block preservation" section.
# --------------------------------------------------------------------------


def extract_opener_block(campaign_md_path: Path) -> str | None:
    """Extract the bytes between the GM-authored opener markers.

    Returns `None` if no opener block is present. Returns the bytes
    from the start marker through the end marker (inclusive) when both
    markers are present in the correct order.

    Per the composer reference: detection is literal-string based, not
    parser-driven. If only one marker is present, or the markers are
    out of order, this function returns `None` so the composer's
    malformation surface fires.
    """
    text = campaign_md_path.read_text(encoding="utf-8")
    start_idx = text.find(OPENER_START_MARKER)
    end_idx = text.find(OPENER_END_MARKER)
    if start_idx == -1 and end_idx == -1:
        return None
    if start_idx == -1 or end_idx == -1 or end_idx < start_idx:
        # Malformed — the composer's contract is to surface this to the
        # GM and stop, not to silently recover. The reference impl
        # returns None to signal "no preserved block"; the test for the
        # malformation case asserts the composer's stop behavior
        # separately.
        return None
    return text[start_idx : end_idx + len(OPENER_END_MARKER)]


def compose_campaign_md_preserving_opener(
    *,
    campaign_md_path: Path,
    campaign_name: str,
    system: str,
    party_section_body: str = "_None._\n",
) -> str:
    """Reference composer regen that preserves the GM-authored opener block.

    Mirrors `references/campaign-overview-composer.md` end-to-end with
    the opener-preservation rule. Given a `campaign.md` with a marker-
    bracketed opener, this returns the regenerated content with the
    opener block preserved byte-for-byte between the header and the
    first agent-managed section.

    Deliberately reduced to the sections needed to verify opener
    preservation. The full menu-led "Where the party might go" surface
    and downstream sections are exercised in
    `test_wrap_session_idempotency.py::compose_campaign_md`; here we
    only need a stable downstream marker (the `## Party` heading and
    a body placeholder) so the opener-preservation property is
    unambiguous.
    """
    opener = extract_opener_block(campaign_md_path)

    lines: list[str] = []
    lines.append(f"# {campaign_name} — Campaign Overview")
    lines.append("")
    lines.append(
        "*This file is agent-maintained. It snapshots the campaign's "
        "current state in glance-readable form and is rewritten by "
        "`/wrap-session` and `/ingest`. Manual edits will be reconciled "
        "(or overwritten with warning) at the next regeneration. For "
        "editorial campaign notes (themes, pitch, house rules), use a "
        "separate file the agent doesn't touch.*"
    )
    lines.append("")
    lines.append(f"- **Campaign:** {campaign_name}")
    lines.append(f"- **System:** {system}")
    lines.append("")

    if opener is not None:
        lines.append(opener)
        lines.append("")

    lines.append("## Party")
    lines.append("")
    lines.append(party_section_body.rstrip("\n"))
    lines.append("")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# Tests — SKILL.md presence and shape
# --------------------------------------------------------------------------


class TestSkillMdExistsAndIsWellFormed:
    """The SKILL.md is present at the conventional path with valid frontmatter."""

    def test_skill_md_file_exists(self, repo_root: Path) -> None:
        path = repo_root / SKILL_MD_PATH_RELATIVE
        assert path.is_file(), (
            f"Expected `/init-campaign` SKILL.md at {SKILL_MD_PATH_RELATIVE}; "
            "the plugin manifest auto-discovers skills from the `skills/` "
            "directory, so the file's absence on disk is the same as the "
            "skill not existing."
        )

    def test_skill_md_frontmatter_has_name_and_description(
        self,
        repo_root: Path,
    ) -> None:
        text = (repo_root / SKILL_MD_PATH_RELATIVE).read_text(encoding="utf-8")
        fm, body = _split_frontmatter(text)
        assert fm.get("name") == "init-campaign", (
            "SKILL.md frontmatter must have `name: init-campaign` so "
            "Claude Code's auto-discovery picks up the right slash-command "
            f"binding. Current value: {fm.get('name')!r}."
        )
        description = fm.get("description")
        assert isinstance(description, str) and description.strip(), (
            "SKILL.md frontmatter must have a non-empty `description:` field "
            "(the convention shared with the other skills in this repo); "
            "Claude Code surfaces it as the skill's tooltip."
        )
        assert body.strip(), "SKILL.md body must not be empty."

    def test_skill_md_documents_from_scratch_mode(
        self,
        repo_root: Path,
    ) -> None:
        """The from-scratch branch is the slice-D deliverable.

        Token-presence check: the SKILL.md must document a from-scratch
        mode (the slice-D scope) and acknowledge a docs mode exists
        (now slice E's deliverable — the docs branch is implemented).
        """
        text = (repo_root / SKILL_MD_PATH_RELATIVE).read_text(encoding="utf-8")
        lower = text.lower()
        assert "from-scratch" in lower or "from scratch" in lower, (
            "SKILL.md must document the from-scratch branch by name "
            "(token `from-scratch` or `from scratch`)."
        )
        # Docs mode lands in slice E (#93). The token check is intentionally
        # loose so this test stays insensitive to prose-level rewording.
        assert "docs" in lower, (
            "SKILL.md must document the docs branch — slice E's "
            "deliverable adds the docs-mode implementation."
        )


class TestSkillMdCitesSharedReferences:
    """Per ADR-0020, the skill consumes shared references via relative paths."""

    EXPECTED_REFERENCE_CITATIONS: tuple[str, ...] = (
        # The scaffolder reference — consumed at Step 7 (from-scratch)
        # and Step D1 (docs mode).
        "../../references/scaffolder.md",
        # The conversational-refinement-loop reference — drives Step 4's
        # pitch elicitation (from-scratch only; skipped in docs mode).
        "../../references/conversational-refinement-loop.md",
        # The PC roster proposal reference — consumed at Step 5
        # (from-scratch) and via the extraction pipeline's Phase 2
        # Step 2.5 in docs mode.
        "../../references/pc-roster-proposal.md",
        # The campaign-overview composer — extended by slice D with the
        # GM-authored opener block preservation rule, used by docs mode's
        # Phase 4 regen via the extraction pipeline.
        "../../references/campaign-overview-composer.md",
        # The first-Adventure sub-flow — composes /init-adventure's
        # in-campaign walkthrough at Step 6 (from-scratch only).
        "../init-adventure/SKILL.md",
        # The extraction pipeline reference — consumed at Step D2 of
        # docs mode (slice E). Phases 2 + 3 + 4 of the shared spec.
        "../../references/extraction-pipeline.md",
    )

    def test_skill_md_cites_each_shared_reference(
        self,
        repo_root: Path,
    ) -> None:
        text = (repo_root / SKILL_MD_PATH_RELATIVE).read_text(encoding="utf-8")
        missing: list[str] = []
        for ref_path in self.EXPECTED_REFERENCE_CITATIONS:
            if ref_path not in text:
                missing.append(ref_path)
        assert not missing, (
            "SKILL.md is missing relative-path citations of these shared "
            f"references: {missing}. Per ADR-0020 (modularization via "
            "shared references), the skill must cite each one via the "
            "relative path from its own location so Claude Code's "
            "markdown-link resolution and the marketplace-install path "
            "both work (#69)."
        )

    def test_skill_md_does_not_use_absolute_install_paths(
        self,
        repo_root: Path,
    ) -> None:
        """Belt-and-suspenders against PR #50/#51/#67's pre-#69 pattern.

        `test_plugin_manifest.py::TestRelativePathsInProse` checks all
        skills' prose at once; this test makes the failure mode local
        to `/init-campaign` so a failure message points at the right
        file.
        """
        text = (repo_root / SKILL_MD_PATH_RELATIVE).read_text(encoding="utf-8")
        bad_prefix = "~/.claude/skills/ttrpg-gm"
        assert bad_prefix not in text, (
            f"SKILL.md contains the pre-#69 absolute-install-path prefix "
            f"`{bad_prefix}`. Use relative paths (e.g., "
            "`../../references/foo.md`) — the absolute form breaks "
            "marketplace install."
        )


# --------------------------------------------------------------------------
# Tests — scaffolded output structural correctness
# --------------------------------------------------------------------------


class TestFromScratchProducesScaffoldedCampaignShape:
    """The from-scratch branch produces a campaign-shaped repo via the scaffolder.

    Per SKILL.md Step 7, the from-scratch branch invokes the shared
    scaffolder reference at `../../references/scaffolder.md`. The
    resulting repo must structurally match the scaffolder's contract
    — same six files, same initial commit. We re-use the scaffolder
    reference impl from `test_ingest_scaffolding.py` rather than
    duplicating it.
    """

    def test_from_scratch_scaffold_produces_the_six_documented_files(
        self,
        tmp_path: Path,
        templates_dir: Path,
    ) -> None:
        from test_ingest_scaffolding import (
            EXPECTED_SCAFFOLDED_FILES,
            scaffold_campaign,
        )

        target = tmp_path / "fresh-campaign"
        scaffold_campaign(
            templates_dir=templates_dir,
            target=target,
            campaign_name="Faerûn Campaign",
            campaign_system="D&D 5e",
        )

        for _, dest_rel in EXPECTED_SCAFFOLDED_FILES:
            assert (target / dest_rel).is_file(), (
                f"From-scratch scaffold did not write {dest_rel}; per "
                "SKILL.md Step 7 the from-scratch branch produces the "
                "same campaign-shaped repo any other consumer of the "
                "scaffolder reference produces."
            )


class TestFromScratchEmptyPcRosterSkipPath:
    """Empty roster skip path leaves `pcs/` absent per ADR-0018."""

    def test_empty_pc_roster_does_not_create_pcs_dir(
        self,
        tmp_path: Path,
        templates_dir: Path,
    ) -> None:
        from test_ingest_scaffolding import scaffold_campaign

        target = tmp_path / "fresh-campaign"
        scaffold_campaign(
            templates_dir=templates_dir,
            target=target,
            campaign_name="Faerûn Campaign",
            campaign_system="D&D 5e",
        )
        # SKILL.md Step 5 explicitly: "GM skips → no PC stubs staged.
        # Proceed to Step 6." And SKILL.md Step 8 #2: "If the roster
        # was empty (the GM skipped Step 5), no PC promotion happens
        # and `pcs/` stays absent (per ADR-0018)."
        assert not (target / "pcs").exists(), (
            "Empty PC roster skip path must leave `pcs/` absent per "
            "ADR-0018. The scaffolder does not pre-create `pcs/`, and "
            "the empty-roster path in /init-campaign Step 5+8 must not "
            "create it either."
        )


# --------------------------------------------------------------------------
# Tests — GM-authored opener block landing + preservation across regen
# --------------------------------------------------------------------------


class TestOpenerBlockLandsBetweenHeaderAndAgentSections:
    """SKILL.md Step 8 #1 inserts the opener between header and `## Party`."""

    def test_opener_block_sits_between_header_and_first_agent_section(
        self,
        tmp_path: Path,
        templates_dir: Path,
    ) -> None:
        from test_ingest_scaffolding import scaffold_campaign

        target = tmp_path / "fresh-campaign"
        scaffold_campaign(
            templates_dir=templates_dir,
            target=target,
            campaign_name="Faerûn Campaign",
            campaign_system="D&D 5e",
        )
        pitch = (
            "A grim political campaign in the Sword Coast, two months after "
            "the Spellplague's local aftershock. Tone: noir with a thread of "
            "dark comedy."
        )
        insert_opener_block(
            campaign_md_path=target / "campaign.md",
            pitch_body=pitch,
        )

        text = (target / "campaign.md").read_text(encoding="utf-8")
        # The opener must sit after the System line and before any
        # agent-managed section heading (`## Party`, `## Where the
        # party might go next session`, etc.).
        system_idx = text.find("- **System:**")
        start_idx = text.find(OPENER_START_MARKER)
        end_idx = text.find(OPENER_END_MARKER)
        assert (
            -1 < system_idx < start_idx < end_idx
        ), (
            "Opener block markers must sit after the `- **System:**` "
            "header line, in order (start before end). "
            f"system={system_idx} start={start_idx} end={end_idx}."
        )

        # All `## ` headings in the rendered file must appear AFTER the
        # end marker — the opener block sits above every agent-managed
        # section per the composer reference's section ordering.
        for match in re.finditer(r"^## ", text, flags=re.MULTILINE):
            assert match.start() > end_idx, (
                "Opener block must sit above every `## ` agent-managed "
                "section heading per the composer reference's section "
                "ordering. Found a `## ` heading at byte "
                f"{match.start()} which is at or before the end marker "
                f"at {end_idx}."
            )

    def test_opener_block_contains_the_pitch_body(
        self,
        tmp_path: Path,
        templates_dir: Path,
    ) -> None:
        from test_ingest_scaffolding import scaffold_campaign

        target = tmp_path / "fresh-campaign"
        scaffold_campaign(
            templates_dir=templates_dir,
            target=target,
            campaign_name="Faerûn Campaign",
            campaign_system="D&D 5e",
        )
        pitch = (
            "A grim political campaign in the Sword Coast. Tone: noir."
        )
        insert_opener_block(
            campaign_md_path=target / "campaign.md",
            pitch_body=pitch,
        )

        extracted = extract_opener_block(target / "campaign.md")
        assert extracted is not None, (
            "Extracted opener block was None — markers were not "
            "detected after insertion."
        )
        assert pitch in extracted, (
            "The pitch body must appear inside the extracted opener "
            f"block bytes. Pitch: {pitch!r}. Extracted: {extracted!r}."
        )


class TestComposerPreservesOpenerAcrossRegen:
    """Per the composer reference, the opener block is preserved byte-for-byte across regens."""

    def test_opener_block_survives_one_regen(
        self,
        tmp_path: Path,
        templates_dir: Path,
    ) -> None:
        from test_ingest_scaffolding import scaffold_campaign

        target = tmp_path / "fresh-campaign"
        scaffold_campaign(
            templates_dir=templates_dir,
            target=target,
            campaign_name="Faerûn Campaign",
            campaign_system="D&D 5e",
        )
        pitch = (
            "A grim political campaign in the Sword Coast. "
            "Tone: noir.\n\n"
            "Stakes: a [[wiki link]] reference and a `code span` survive."
        )
        insert_opener_block(
            campaign_md_path=target / "campaign.md",
            pitch_body=pitch,
        )
        original_opener = extract_opener_block(target / "campaign.md")
        assert original_opener is not None

        # Run a composer regen against the populated campaign.md.
        regenerated = compose_campaign_md_preserving_opener(
            campaign_md_path=target / "campaign.md",
            campaign_name="Faerûn Campaign",
            system="D&D 5e",
        )
        # Write the regen back, then re-extract to verify the opener
        # survives the round trip.
        (target / "campaign.md").write_text(regenerated, encoding="utf-8")
        regen_opener = extract_opener_block(target / "campaign.md")
        assert regen_opener == original_opener, (
            "Opener block bytes must be preserved byte-for-byte across "
            "a composer regen. Got a mismatch — the composer is "
            "modifying the GM-authored content, violating the "
            "preservation rule."
        )

    def test_opener_block_survives_two_regens(
        self,
        tmp_path: Path,
        templates_dir: Path,
    ) -> None:
        """Idempotency: the opener block is stable across N regens.

        The composer's determinism contract (per the reference) says
        regenerating from the same state produces byte-identical output.
        The opener block is part of that state — N regens against the
        same `campaign.md` (no other campaign state changes) must
        produce a byte-identical file at the end.
        """
        from test_ingest_scaffolding import scaffold_campaign

        target = tmp_path / "fresh-campaign"
        scaffold_campaign(
            templates_dir=templates_dir,
            target=target,
            campaign_name="Faerûn Campaign",
            campaign_system="D&D 5e",
        )
        pitch = "A heist campaign in the Free Cities. Tone: capers."
        insert_opener_block(
            campaign_md_path=target / "campaign.md",
            pitch_body=pitch,
        )

        # First regen.
        first = compose_campaign_md_preserving_opener(
            campaign_md_path=target / "campaign.md",
            campaign_name="Faerûn Campaign",
            system="D&D 5e",
        )
        (target / "campaign.md").write_text(first, encoding="utf-8")
        # Second regen against the post-first state.
        second = compose_campaign_md_preserving_opener(
            campaign_md_path=target / "campaign.md",
            campaign_name="Faerûn Campaign",
            system="D&D 5e",
        )
        assert first == second, (
            "Two consecutive composer regens must produce byte-identical "
            "output (determinism contract). The opener block, being "
            "preserved verbatim, contributes to this property."
        )

    def test_back_compat_no_opener_block_present_yields_no_opener_in_regen(
        self,
        tmp_path: Path,
        templates_dir: Path,
    ) -> None:
        """Per the composer reference: "If neither marker is present:
        the file has no opener block — render the regen with no opener
        (the section is optional). This is the back-compat path."

        Campaigns scaffolded before this rule shipped don't have an
        opener block; their regens must continue to work and produce
        no opener.
        """
        from test_ingest_scaffolding import scaffold_campaign

        target = tmp_path / "fresh-campaign"
        scaffold_campaign(
            templates_dir=templates_dir,
            target=target,
            campaign_name="Faerûn Campaign",
            campaign_system="D&D 5e",
        )
        # Don't insert any opener block — simulate a pre-rule campaign.
        regenerated = compose_campaign_md_preserving_opener(
            campaign_md_path=target / "campaign.md",
            campaign_name="Faerûn Campaign",
            system="D&D 5e",
        )
        assert OPENER_START_MARKER not in regenerated, (
            "Back-compat: a campaign with no opener block must regen "
            "with no opener block — the composer never introduces "
            "markers itself."
        )
        assert OPENER_END_MARKER not in regenerated, (
            "Back-compat: a campaign with no opener block must regen "
            "with no opener block — the composer never introduces "
            "markers itself."
        )


# --------------------------------------------------------------------------
# Tests — first-Adventure sub-flow composition
# --------------------------------------------------------------------------


class TestFirstAdventureSubFlowComposesOnTopOfScaffold:
    """Step 6's first-Adventure sub-flow composes /init-adventure's in-campaign walkthrough.

    Per SKILL.md Step 6, when the GM opts in to a first Adventure, the
    workflow scaffolds first (Step 7), promotes the pitch (Step 8), then
    hands off to `/init-adventure`'s in-campaign Step 2 walkthrough.
    Output: a campaign-shaped repo with the opener-block pitch in
    `campaign.md` AND one Adventure pre-populated under
    `adventures/<slug>/adventure.md`.

    The composition contract is what this test pins. The Adventure
    walkthrough itself is exercised by `test_init_adventure.py`; this
    test only verifies the two structures land together correctly.
    """

    def test_pitch_plus_first_adventure_compose_into_one_campaign_shape(
        self,
        tmp_path: Path,
        templates_dir: Path,
    ) -> None:
        from test_ingest_scaffolding import scaffold_campaign
        from test_init_adventure import write_initial_adventure_file

        target = tmp_path / "bootstrap-with-first-adventure"
        scaffold_campaign(
            templates_dir=templates_dir,
            target=target,
            campaign_name="Faerûn Campaign",
            campaign_system="D&D 5e",
        )
        # Step 8 #1: pitch lands in campaign.md.
        insert_opener_block(
            campaign_md_path=target / "campaign.md",
            pitch_body="A grim political campaign in the Sword Coast.",
        )
        # Step 6 -> /init-adventure in-campaign mode -> Adventure file.
        adventure_path = write_initial_adventure_file(
            campaign_root=target,
            adventure_name="The Whitebridge Job",
            premise="A heist at the merchant Whitebridge's manor.",
        )

        # Campaign-shape commitments:
        # 1) CLAUDE.md and campaign.md present (scaffolder).
        assert (target / "CLAUDE.md").is_file()
        assert (target / "campaign.md").is_file()
        # 2) The opener block is present in campaign.md.
        assert extract_opener_block(target / "campaign.md") is not None
        # 3) Exactly one Adventure under `adventures/`.
        adventures_root = target / "adventures"
        assert adventures_root.is_dir()
        adventures = [p for p in adventures_root.iterdir() if p.is_dir()]
        assert len(adventures) == 1, (
            "First-Adventure sub-flow should produce exactly one "
            f"Adventure directory; got {len(adventures)}: "
            f"{[p.name for p in adventures]}."
        )
        # 4) The Adventure file at the documented path validates.
        assert adventure_path.is_file()
        fm, _ = _split_frontmatter(adventure_path.read_text(encoding="utf-8"))
        assert fm["status"] == "introduced", (
            "First-Adventure must start at `status: introduced` per the "
            "Adventure schema's defaults-at-creation rule."
        )

    def test_skip_first_adventure_leaves_adventures_dir_absent(
        self,
        tmp_path: Path,
        templates_dir: Path,
    ) -> None:
        """Skip path: the scaffolder does not create `adventures/`, and
        the from-scratch branch without a first-Adventure opt-in must
        not create it either.
        """
        from test_ingest_scaffolding import scaffold_campaign

        target = tmp_path / "bootstrap-no-first-adventure"
        scaffold_campaign(
            templates_dir=templates_dir,
            target=target,
            campaign_name="Faerûn Campaign",
            campaign_system="D&D 5e",
        )
        insert_opener_block(
            campaign_md_path=target / "campaign.md",
            pitch_body="A pitch with no first Adventure yet.",
        )
        # No Adventure file written; the GM-skip path means no
        # `adventures/` directory exists.
        assert not (target / "adventures").exists(), (
            "Skip path: the scaffolder does not create `adventures/`, "
            "and the from-scratch branch without a first-Adventure "
            "opt-in must not create it either. The GM adds adventures "
            "later via /init-adventure or /ingest."
        )


# --------------------------------------------------------------------------
# Tests — composer reference itself documents the rule
# --------------------------------------------------------------------------


class TestComposerReferenceDocumentsOpenerRule:
    """Spec-drift safety net: the composer reference must document the rule.

    The reference impl above mirrors `references/campaign-overview-composer.md`
    section "GM-authored opener block preservation". If the reference
    drops the section or renames the markers, this test catches it
    before the rule silently diverges.
    """

    def test_composer_reference_documents_opener_preservation_section(
        self,
        repo_root: Path,
    ) -> None:
        ref = repo_root / "references" / "campaign-overview-composer.md"
        content = ref.read_text(encoding="utf-8")
        assert "GM-authored opener block preservation" in content, (
            "references/campaign-overview-composer.md must contain a "
            "section heading documenting the opener preservation rule. "
            "This is the spec the reference impl in this test file "
            "mirrors; without the doc, the rule is undocumented."
        )

    def test_composer_reference_documents_exact_marker_strings(
        self,
        repo_root: Path,
    ) -> None:
        ref = repo_root / "references" / "campaign-overview-composer.md"
        content = ref.read_text(encoding="utf-8")
        # The reference must mention the exact marker bytes the
        # composer detects. Test asserts presence of both markers
        # verbatim — drift on either string breaks the consumers'
        # ability to find their opener blocks.
        assert OPENER_START_MARKER in content, (
            "references/campaign-overview-composer.md must document the "
            f"exact start marker string `{OPENER_START_MARKER}`; the "
            "composer detects this by literal byte match."
        )
        assert OPENER_END_MARKER in content, (
            "references/campaign-overview-composer.md must document the "
            f"exact end marker string `{OPENER_END_MARKER}`; the "
            "composer detects this by literal byte match."
        )

    def test_composer_reference_cites_adr_0019(self, repo_root: Path) -> None:
        """The opener-preservation rule originates with /init-campaign;
        the reference should mention either /init-campaign or ADR-0019
        somewhere to ground the rule in the v0.3 design.
        """
        ref = repo_root / "references" / "campaign-overview-composer.md"
        content = ref.read_text(encoding="utf-8")
        assert "init-campaign" in content, (
            "The opener-preservation rule originates with /init-campaign "
            "(slice D of v0.3). The reference should mention "
            "/init-campaign so a reader can trace why the rule exists."
        )


class TestSkillMdCitesAdrs:
    """The SKILL.md cites the relevant ADRs for traceability."""

    def test_skill_md_cites_adr_0019(self, repo_root: Path) -> None:
        text = (repo_root / SKILL_MD_PATH_RELATIVE).read_text(encoding="utf-8")
        assert "0019" in text, (
            "SKILL.md must cite ADR-0019 (the architectural decision "
            "that introduces /init-campaign as the bootstrapping front "
            "door). Trace lineage is load-bearing for the slice's "
            "rationale."
        )

    def test_skill_md_cites_adr_0018_for_pc_roster(
        self,
        repo_root: Path,
    ) -> None:
        text = (repo_root / SKILL_MD_PATH_RELATIVE).read_text(encoding="utf-8")
        assert "0018" in text, (
            "SKILL.md's PC roster step (Step 5) must cite ADR-0018 "
            "(PC roster as a survey deliverable, with empty-roster skip "
            "path) — the ADR is the source of the skip-path rule the "
            "step honors."
        )


# --------------------------------------------------------------------------
# Tests — docs-mode branch (slice E, refs #93)
#
# Docs mode of `/init-campaign` runs the shared scaffolder reference at
# Step D1 (same as the from-scratch branch's Step 7), then composes the
# shared extraction pipeline reference at Step D2 (the same workflow
# `/ingest` runs in Phases 2-4). Pitch elicitation, the optional PC
# roster step (Step 5 of from-scratch), and the optional first-Adventure
# sub-flow (Step 6) are all skipped — the docs themselves supply the
# campaign content.
#
# These tests pin the structural shape:
#
#   * Docs mode is documented as an implemented branch (not a TODO).
#   * Docs mode does NOT auto-create the GM-authored opener block —
#     the pitch persistence rule still applies if the GM hand-authors
#     it later, but `/init-campaign` docs mode itself never writes one.
#   * Docs mode produces a scaffolded campaign repo with extracted
#     content from the input docs (modelled via the per-doc + wrap-up
#     commit chain from `test_ingest_per_doc_commits.py`).
#   * The pipeline's commit-subject prefixes (`/ingest doc …`,
#     `/ingest wrap-up …`) carry through even when the pipeline runs
#     from `/init-campaign` — the prefix identifies the *workflow*,
#     not the invoking skill.
# --------------------------------------------------------------------------


class TestDocsModeIsDocumentedAsImplemented:
    """Docs mode is an implemented branch, not a deferred TODO.

    Slice D shipped with the docs branch as a *TODO slice E* placeholder.
    Slice E (this slice) implements the branch — the SKILL.md must
    surface the implementation clearly so the LLM doesn't route docs
    requests back to `/ingest` against an unscaffolded directory (the
    failure mode the placeholder explicitly warned against).
    """

    def test_docs_mode_is_no_longer_a_todo_placeholder(
        self,
        repo_root: Path,
    ) -> None:
        """The SKILL.md does not describe docs mode as a TODO / slice E placeholder.

        Slice D's prose contained the phrase `TODO slice E` describing
        the unimplemented docs branch. Slice E removes that placeholder.
        This test catches the failure mode where the slice E
        implementation lands but the TODO marker is left in place by
        accident.
        """
        text = (repo_root / SKILL_MD_PATH_RELATIVE).read_text(encoding="utf-8")
        # The exact slice-D marker phrasing. If slice E re-uses the
        # phrase to describe something else, this test will need to be
        # tightened against the surrounding context — but the marker
        # phrase as-is implies an unimplemented branch.
        forbidden_phrases: tuple[str, ...] = (
            "TODO slice E",
            "docs mode is not yet implemented",
            "docs branch is not implemented",
            "docs mode isn't ready yet",
        )
        offenders = [p for p in forbidden_phrases if p in text]
        assert not offenders, (
            "SKILL.md still contains slice-D TODO placeholder phrasing "
            "for docs mode: "
            f"{offenders}. Slice E implements the branch; the prose "
            "should describe the docs-mode flow as a concrete pipeline "
            "(scaffold → extraction pipeline), not a deferred TODO."
        )

    def test_docs_mode_step_is_named_in_prose(
        self,
        repo_root: Path,
    ) -> None:
        """Docs-mode steps are named visibly in the SKILL.md prose.

        The from-scratch branch documents its steps as Step 4 … Step 9
        (the slice-D shape); the docs-mode branch needs an analogous
        named step sequence so the LLM has a structural anchor for
        each phase. The exact step labels (Step D1 / Step D2 / Step D3,
        or similar) are an implementation choice — we only assert the
        SKILL.md mentions scaffolding *first* and the extraction
        pipeline *second*.
        """
        text = (repo_root / SKILL_MD_PATH_RELATIVE).read_text(encoding="utf-8")
        # The two anchor references docs mode composes. Per the
        # citations-test above, both are cited at least once; here we
        # confirm they both appear in docs-mode-coded prose.
        assert "scaffolder.md" in text, (
            "Docs-mode prose must name the scaffolder reference — "
            "Step D1 (the scaffold step) routes to it."
        )
        assert "extraction-pipeline.md" in text, (
            "Docs-mode prose must name the extraction-pipeline "
            "reference — Step D2 (the survey + per-doc + wrap-up step) "
            "routes to it."
        )

    def test_docs_mode_skips_pitch_elicitation_in_prose(
        self,
        repo_root: Path,
    ) -> None:
        """The SKILL.md says docs mode skips pitch elicitation.

        Pitch elicitation is the from-scratch branch's Step 4. In docs
        mode the docs supply the campaign content directly, so pitch
        elicitation is bypassed. The skill must say so explicitly so
        the LLM doesn't compose the from-scratch flow on top of the
        docs flow (over-prompting the GM).
        """
        text = (repo_root / SKILL_MD_PATH_RELATIVE).read_text(encoding="utf-8")
        lower = text.lower()
        # The skip is documented as either "pitch elicitation is
        # skipped in docs mode" / "pitch elicitation skipped" / etc.
        # We accept any phrasing that pairs "pitch" with "skip" in a
        # docs-mode-adjacent sentence.
        assert "pitch" in lower
        # The literal pairing — looser than a regex on full prose, but
        # tight enough to catch the omission case.
        assert "skip" in lower
        assert (
            "pitch elicitation is skipped" in lower
            or "pitch elicitation skipped" in lower
            or "skips pitch elicitation" in lower
            or "skips step 4" in lower
            or "skipped in docs mode" in lower
        ), (
            "SKILL.md must surface that pitch elicitation is skipped "
            "in docs mode (the docs supply the campaign content, so "
            "the Step 4 pitch loop doesn't run). Without this the LLM "
            "could compose the pitch loop on top of the extraction "
            "pipeline, over-prompting the GM."
        )


class TestDocsModeProducesScaffoldedCampaignWithExtractedContent:
    """Docs mode produces a scaffolded campaign repo + extracted content.

    The docs-mode flow is mechanically: scaffolder (Step D1) →
    extraction pipeline (Step D2). The scaffolder produces the six
    documented committed files + the initial scaffold commit; the
    pipeline produces per-doc commits (one per input doc) and a
    wrap-up commit. We model the per-doc + wrap-up commits using the
    reference helpers from `test_ingest_per_doc_commits.py` and assert
    the resulting commit chain matches the documented shape.
    """

    def test_docs_mode_commit_chain_is_scaffold_then_per_doc_then_wrap_up(
        self,
        tmp_path: Path,
        templates_dir: Path,
    ) -> None:
        """The end-state commit chain matches the spec.

        Sequence: `Scaffold campaign repo via ttrpg-gm /ingest` → one
        `/ingest doc <N>/<total>: …` commit per input doc → one final
        `/ingest wrap-up (…)` commit. The pipeline's commit-subject
        prefixes are preserved when run from `/init-campaign` — they
        identify the *workflow* (the extraction pipeline), not the
        invoking skill.
        """
        from test_ingest_scaffolding import scaffold_campaign
        from test_ingest_per_doc_commits import (
            _run_git,
            commit_doc,
            commit_wrap_up,
            per_doc_commit_count,
            wrap_up_commit_exists,
        )

        # Step D1: scaffolder.
        target = tmp_path / "docs-mode-campaign"
        scaffold_campaign(
            templates_dir=templates_dir,
            target=target,
            campaign_name="Faerûn Campaign",
            campaign_system="D&D 5e",
        )

        # Step D2: extraction pipeline. Model two input docs producing
        # per-doc lifecycle writes + commits, then a wrap-up commit.
        # The reference helpers `commit_doc` / `commit_wrap_up` mirror
        # SKILL.md (or, here, the extraction pipeline reference's) Step
        # 5.8 and Phase 4 Step 3c.
        (target / "npcs").mkdir(parents=True, exist_ok=True)
        (target / "npcs" / "sera.md").write_text(
            "# Sera\n\nThe blacksmith.\n", encoding="utf-8"
        )
        (target / "npcs" / "maren.md").write_text(
            "# Maren\n\nThe innkeeper.\n", encoding="utf-8"
        )
        commit_doc(
            campaign=target,
            doc_index=1,
            doc_total=2,
            doc_name="phandalin-gazetteer.md",
            summary="2 NPCs",
            paths_written=["npcs/sera.md", "npcs/maren.md"],
        )
        (target / "adventures" / "lost-mines").mkdir(parents=True)
        (target / "adventures" / "lost-mines" / "adventure.md").write_text(
            "---\nstatus: introduced\norder: ~\n---\n\n# Lost Mines\n",
            encoding="utf-8",
        )
        commit_doc(
            campaign=target,
            doc_index=2,
            doc_total=2,
            doc_name="lost-mines.md",
            summary="Adventure",
            paths_written=["adventures/lost-mines/adventure.md"],
        )
        # Phase 4 wrap-up: campaign.md regen + Adventure backfill.
        # The commit_wrap_up helper does `git add <paths>` then commits,
        # so both files must have on-disk modifications relative to the
        # last per-doc commit. Simulate Phase 4 Step 1 (Adventure
        # order backfill — `order: ~` becomes `order: 1`) and Phase 4
        # Step 2 (campaign.md regen).
        (target / "adventures" / "lost-mines" / "adventure.md").write_text(
            "---\nstatus: introduced\norder: 1\n---\n\n# Lost Mines\n",
            encoding="utf-8",
        )
        (target / "campaign.md").write_text(
            "# Faerûn Campaign — Campaign Overview\n\n"
            "- **Campaign:** Faerûn Campaign\n"
            "- **System:** D&D 5e\n"
            "- **Status:** active\n"
            "- **Last event:** 2026-06-02 (ingest)\n\n"
            "## Adventures\n\n- [[lost-mines]]\n",
            encoding="utf-8",
        )
        commit_wrap_up(
            campaign=target,
            summary="campaign.md regen, 1 Adventure backfilled with order: 1",
            paths_written=[
                "campaign.md",
                "adventures/lost-mines/adventure.md",
            ],
        )

        # Assertions on the commit chain.
        assert per_doc_commit_count(target) == 2, (
            "Two input docs should produce two `/ingest doc N/2: …` "
            "per-doc commits."
        )
        assert wrap_up_commit_exists(target), (
            "Phase 4 wrap-up commit should exist after all per-doc "
            "commits land. Without it, the recovery pre-flight would "
            "treat the campaign as crashed mid-Phase-3."
        )
        # The commit count: scaffold + 2 per-doc + wrap-up = 4.
        commits = _run_git(
            "log", "--format=%s", cwd=target
        ).stdout.strip().splitlines()
        assert len(commits) == 4, (
            f"Expected 4 commits (scaffold + 2 per-doc + wrap-up); "
            f"got {len(commits)}: {commits}"
        )
        # Order is most-recent first; the scaffold commit is last.
        assert commits[-1] == "Scaffold campaign repo via ttrpg-gm /ingest"
        assert commits[0].startswith("/ingest wrap-up "), (
            "Most recent commit should be the wrap-up commit (slice E "
            "spec: docs mode ends with Phase 4 wrap-up)."
        )

    def test_docs_mode_target_is_a_campaign_shape(
        self,
        tmp_path: Path,
        templates_dir: Path,
    ) -> None:
        """The scaffolded target is structurally a campaign repo.

        Re-uses the scaffolder reference impl: the same six documented
        files land regardless of which consumer (`/ingest`,
        `/init-adventure` standalone, `/init-campaign` from-scratch,
        `/init-campaign` docs mode) invoked the scaffolder. The
        docs-mode path doesn't customize the scaffolder output.
        """
        from test_ingest_scaffolding import (
            EXPECTED_SCAFFOLDED_FILES,
            scaffold_campaign,
        )

        target = tmp_path / "docs-mode-campaign"
        scaffold_campaign(
            templates_dir=templates_dir,
            target=target,
            campaign_name="Faerûn Campaign",
            campaign_system="D&D 5e",
        )

        for _, dest_rel in EXPECTED_SCAFFOLDED_FILES:
            assert (target / dest_rel).is_file(), (
                f"Docs-mode scaffold did not write {dest_rel}; per "
                "SKILL.md Step D1 the docs branch produces the same "
                "campaign-shaped repo any other consumer of the "
                "scaffolder reference produces."
            )


class TestDocsModeDoesNotAutoCreateOpenerBlock:
    """Docs mode skips pitch elicitation, so no opener block is auto-created.

    The from-scratch branch's Step 8 #1 writes the GM-authored opener
    block (the pitch elicited at Step 4 lands between markers). Docs
    mode skips Step 4 entirely — there's no pitch to land. The
    composer's back-compat path (regenerating with no opener when
    neither marker is present) is the relevant rule for docs-mode
    `campaign.md` regens, and is already pinned by
    `TestComposerPreservesOpenerAcrossRegen.test_back_compat_…`.

    This test pins the docs-mode-specific commitment: after Steps D1
    and D2, no opener markers appear in `campaign.md`.
    """

    def test_docs_mode_campaign_md_has_no_opener_markers_after_scaffold(
        self,
        tmp_path: Path,
        templates_dir: Path,
    ) -> None:
        """After the scaffolder runs (Step D1), there's no opener block.

        Docs mode never invokes the pitch loop. The scaffolder's
        `campaign.md` template doesn't contain the opener markers; the
        only path that adds them is Step 8 #1 of the from-scratch
        branch. Confirm the docs-mode shape leaves them absent.
        """
        from test_ingest_scaffolding import scaffold_campaign

        target = tmp_path / "docs-mode-campaign"
        scaffold_campaign(
            templates_dir=templates_dir,
            target=target,
            campaign_name="Faerûn Campaign",
            campaign_system="D&D 5e",
        )
        text = (target / "campaign.md").read_text(encoding="utf-8")
        assert OPENER_START_MARKER not in text, (
            "Docs mode does not run the pitch loop, so the opener-block "
            "start marker should never appear in the scaffolded "
            "`campaign.md`. If it does, the scaffolder template has "
            "drifted or docs mode is wrongly invoking Step 8."
        )
        assert OPENER_END_MARKER not in text, (
            "Docs mode does not run the pitch loop, so the opener-block "
            "end marker should never appear in the scaffolded "
            "`campaign.md`. If it does, the scaffolder template has "
            "drifted or docs mode is wrongly invoking Step 8."
        )

    def test_docs_mode_supports_late_gm_authored_opener_via_composer_rule(
        self,
        tmp_path: Path,
        templates_dir: Path,
    ) -> None:
        """If the GM later hand-authors an opener, the composer preserves it.

        The pitch persistence rule from slice D applies independent of
        which mode created the campaign — the composer reads the
        markers literally, so a GM who hand-edits `campaign.md` post-
        docs-mode-run gets the same byte-for-byte preservation across
        future regens.

        This test mirrors the from-scratch
        `test_opener_block_survives_one_regen` from
        `TestComposerPreservesOpenerAcrossRegen` but starts from a
        scaffolded-without-pitch campaign (the docs-mode end state)
        and verifies the hand-authored opener still survives.
        """
        from test_ingest_scaffolding import scaffold_campaign

        target = tmp_path / "docs-mode-campaign"
        scaffold_campaign(
            templates_dir=templates_dir,
            target=target,
            campaign_name="Faerûn Campaign",
            campaign_system="D&D 5e",
        )
        # No Step 8 — the docs-mode run ends without writing an opener.
        # The GM later hand-authors one (modelled by the same
        # `insert_opener_block` helper since the operation is identical
        # whether the agent or the GM does it).
        late_pitch = (
            "Added after docs-mode run: a curated pitch reframing the "
            "ingested setting as a noir caper across the Sword Coast."
        )
        insert_opener_block(
            campaign_md_path=target / "campaign.md",
            pitch_body=late_pitch,
        )
        original = extract_opener_block(target / "campaign.md")
        assert original is not None, (
            "Hand-authored opener block should be detectable by the "
            "extractor after the GM inserts it."
        )

        regenerated = compose_campaign_md_preserving_opener(
            campaign_md_path=target / "campaign.md",
            campaign_name="Faerûn Campaign",
            system="D&D 5e",
        )
        (target / "campaign.md").write_text(regenerated, encoding="utf-8")
        after_regen = extract_opener_block(target / "campaign.md")
        assert after_regen == original, (
            "Hand-authored opener block (post-docs-mode-run) must be "
            "preserved byte-for-byte across composer regens — the "
            "preservation rule is independent of which mode created "
            "the campaign."
        )


class TestDocsModeReusesExtractionPipelineReference:
    """Docs mode composes the same extraction-pipeline.md reference `/ingest` uses.

    Slice B lifted Phases 2-4 of `/ingest` into the shared
    `references/extraction-pipeline.md`. Slice E composes that
    reference from `/init-campaign` docs mode, so the same canonical
    workflow drives both skills. These tests guard the citation and
    the shape (no docs-mode-specific re-inlining of pipeline prose).
    """

    def test_extraction_pipeline_reference_is_cited_relative(
        self,
        repo_root: Path,
    ) -> None:
        """The extraction-pipeline citation uses the relative-path form.

        Per ADR-0020 and #69, references are cited as relative paths
        from the SKILL.md's location. From `skills/init-campaign/SKILL.md`,
        the extraction pipeline at `references/extraction-pipeline.md`
        resolves to `../../references/extraction-pipeline.md`.
        """
        text = (repo_root / SKILL_MD_PATH_RELATIVE).read_text(encoding="utf-8")
        assert "../../references/extraction-pipeline.md" in text, (
            "Docs mode must cite the extraction-pipeline reference at "
            "`../../references/extraction-pipeline.md` (relative path "
            "from the SKILL.md). Per slice B's lift, this is the "
            "canonical spec for Phases 2-4."
        )

    def test_extraction_pipeline_reference_documents_init_campaign_consumer(
        self,
        repo_root: Path,
    ) -> None:
        """The reference acknowledges /init-campaign as a consumer.

        Slice B's reference prose names `/init-campaign`'s docs-mode
        branch as a consumer alongside `/ingest`. This test guards that
        the reference doesn't silently drop the mention (which would
        leave the docs-mode consumer un-documented from the reference's
        perspective).
        """
        ref = repo_root / "references" / "extraction-pipeline.md"
        content = ref.read_text(encoding="utf-8")
        assert "init-campaign" in content, (
            "The extraction-pipeline reference should mention "
            "`/init-campaign` as a consumer — slice B (the lift) "
            "named it explicitly, and slice E (this slice) implements "
            "the consumer. Dropping the mention from the reference "
            "would leave the consumer un-grounded in the spec."
        )


class TestDocsModeFromScratchRegressionsStillHold:
    """Slice D's from-scratch invariants must survive the slice E edit.

    Slice E's docs-mode addition must not regress the from-scratch
    branch. These tests are a structural belt-and-suspenders: the
    existing `TestFromScratchProducesScaffoldedCampaignShape` and
    `TestFirstAdventureSubFlowComposesOnTopOfScaffold` already cover
    the from-scratch produce-a-campaign shape, but this test set asserts
    the from-scratch branch's Steps 4-9 *labels* survive the slice-E
    edit (we don't move Step 7 to Step D1 by accident, etc.).
    """

    def test_from_scratch_step_4_pitch_loop_label_preserved(
        self,
        repo_root: Path,
    ) -> None:
        """Step 4 (pitch elicitation) is still named `Step 4`."""
        text = (repo_root / SKILL_MD_PATH_RELATIVE).read_text(encoding="utf-8")
        assert "Step 4 — Collect and refine the pitch" in text, (
            "Slice E edits must preserve the from-scratch branch's "
            "Step 4 label. If you renamed it, update the from-scratch "
            "tests too."
        )

    def test_from_scratch_step_7_scaffolder_label_preserved(
        self,
        repo_root: Path,
    ) -> None:
        """Step 7 (scaffolder) is still named `Step 7`."""
        text = (repo_root / SKILL_MD_PATH_RELATIVE).read_text(encoding="utf-8")
        assert "Step 7 — Scaffold the campaign repo" in text, (
            "Slice E edits must preserve the from-scratch branch's "
            "Step 7 label. The Step 7 scaffolder call is the from-"
            "scratch analog of docs mode's Step D1, but the label "
            "stays."
        )

    def test_from_scratch_step_8_pitch_promotion_label_preserved(
        self,
        repo_root: Path,
    ) -> None:
        """Step 8 (promote staging to scaffolded campaign) is still named `Step 8`."""
        text = (repo_root / SKILL_MD_PATH_RELATIVE).read_text(encoding="utf-8")
        assert "Step 8 — Promote staging to the scaffolded campaign" in text, (
            "Slice E edits must preserve the from-scratch branch's "
            "Step 8 label — the pitch-promotion-into-opener-block step "
            "is load-bearing for the composer's preservation rule."
        )
