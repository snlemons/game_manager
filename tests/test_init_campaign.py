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
        (slice E placeholder; the prose can describe it as deferred).
        """
        text = (repo_root / SKILL_MD_PATH_RELATIVE).read_text(encoding="utf-8")
        lower = text.lower()
        assert "from-scratch" in lower or "from scratch" in lower, (
            "SKILL.md must document the from-scratch branch by name "
            "(token `from-scratch` or `from scratch`)."
        )
        # docs mode is slice E; the SKILL.md may describe it as
        # deferred / TODO. We don't enforce the exact framing, only
        # that the docs branch is acknowledged somewhere in prose so
        # the GM-facing Step 3 prompt has somewhere to route docs
        # cases until slice E lands.
        assert "docs" in lower, (
            "SKILL.md must acknowledge the docs branch (even as a TODO "
            "/ slice E placeholder) so Step 3's mode prompt has a "
            "documented route for the docs case."
        )


class TestSkillMdCitesSharedReferences:
    """Per ADR-0020, the skill consumes shared references via relative paths."""

    EXPECTED_REFERENCE_CITATIONS: tuple[str, ...] = (
        # The scaffolder reference — consumed at Step 7.
        "../../references/scaffolder.md",
        # The conversational-refinement-loop reference — drives Step 4's
        # pitch elicitation.
        "../../references/conversational-refinement-loop.md",
        # The PC roster proposal reference — consumed at Step 5.
        "../../references/pc-roster-proposal.md",
        # The campaign-overview composer — extended by this slice with
        # the GM-authored opener block preservation rule.
        "../../references/campaign-overview-composer.md",
        # The first-Adventure sub-flow — composes /init-adventure's
        # in-campaign walkthrough at Step 6.
        "../init-adventure/SKILL.md",
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
