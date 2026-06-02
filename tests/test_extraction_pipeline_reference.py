"""Spec-conformance tests for `references/extraction-pipeline.md` (slice B, refs #82).

What this test covers
---------------------
v0.3 slice B lifts `/ingest` Phases 2 + 3 + 4 prose into a shared reference
at `references/extraction-pipeline.md` so the same canonical workflow is
consumed by `/ingest` and (in slice E) `/init-campaign`'s docs-mode branch,
per ADR-0020. The reference is a markdown spec, not runtime code; these
tests pin the structural contracts the consumers depend on:

  (a) Section structure. The reference has the three top-level Phase
      headings (`## Phase 2: Survey`, `## Phase 3: Per-doc extraction
      loop`, `## Phase 4: Wrap-up`), the Phase 3 step headings the LLM
      navigates (Step 0, 0b, 0c, 1, 2, 3, 3b, 4, 4a, 4b, 5, 5b, 6), and
      the Phase 4 step headings (Step 0, 1, 2, 3 with sub-steps 3a/3b/3c,
      Step 4).
  (b) Pre-approval gate seam. The reference documents a structural
      "before opening any staging file" boundary so a future #27 gate
      can slot in without restructuring the per-doc loop. This test
      pins the seam's presence and the invariants the future gate has
      to preserve.
  (c) Phase 2 survey contract. Single-doc stripped, zero-doc skipped,
      both staged files in the same review batch, verbal refinement via
      Edit per ADR-0015.
  (d) Per-doc commit format. The reference shows the
      `/ingest doc <N>/<total>: <doc-name> (<summary>)` subject template
      and the documented examples; scoped staging rule (`git add` with
      explicit paths over `git add -A`) is documented; the lifecycle
      folders are enumerated.
  (e) Refined cancel-mid-Phase-3 prompt. All three responses (Keep all
      / Reset to before doc K / Abandon entirely) are present with the
      `git reset --hard` mechanism and the lessons-drop rule.
  (f) Recovery pre-flight (Step 0c). The reference documents the
      `git log --grep '^/ingest doc '` detection and the resume /
      abandon-and-rescaffold prompt.
  (g) Phase 4 wrap-up. The narrowed commit subject format
      `/ingest wrap-up (<short summary>)` and the canonical example
      `/ingest wrap-up (campaign.md regen, 3 Adventures backfilled with
      order: 1/2/3)` appear in the reference; the campaign.md composer
      citation is intact; the ingest-only variants from the composer
      (Status / Last event header lines, full Adventures history, no
      Consequence truncation) are documented.
  (h) SKILL.md citations. The /ingest SKILL.md cites the reference at
      Phase 2, Phase 3, and Phase 4 sections so the LLM is routed to
      the reference rather than re-inlining the same prose.
  (i) Survey staging files. The expected `.ttrpg-staging/` file names
      (`survey-descriptions.md`, `survey-pcs.md`, `survey-order.md` for
      multi-doc; `adventure-order.md` for Phase 4) are documented in
      the reference.

What is **not** tested here is the LLM agent's compliance with the
prompt. The skill is implemented as a prompt; without a headless-LLM
harness in CI, an integration-level test of agent compliance is
impractical. These tests exercise the *spec* the skill encodes — the
same pattern `tests/test_ingest_per_doc_commits.py::TestSpecConformance`
uses for the v0.2-era spec checks.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Fixtures: paths to the reference and the consuming SKILL.md
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def extraction_pipeline_path(repo_root: Path) -> Path:
    """Absolute path to the v0.3 extraction-pipeline reference."""
    return repo_root / "references" / "extraction-pipeline.md"


@pytest.fixture(scope="module")
def extraction_pipeline_text(extraction_pipeline_path: Path) -> str:
    """Full text of the extraction-pipeline reference, read once per module."""
    return extraction_pipeline_path.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def ingest_skill_text(repo_root: Path) -> str:
    """Full text of `/ingest`'s SKILL.md, read once per module."""
    return (repo_root / "skills" / "ingest" / "SKILL.md").read_text(
        encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# (a) Section structure
# ---------------------------------------------------------------------------


class TestReferenceExists:
    """The reference exists at the canonical path and is non-trivial."""

    def test_file_exists(self, extraction_pipeline_path: Path) -> None:
        assert extraction_pipeline_path.is_file(), (
            f"Expected the extraction-pipeline reference at "
            f"{extraction_pipeline_path}. v0.3 slice B (refs #82) lifts "
            "the canonical /ingest Phases 2/3/4 prose into this file."
        )

    def test_file_is_substantive(self, extraction_pipeline_text: str) -> None:
        """The reference is a multi-section spec, not a one-line stub."""
        assert len(extraction_pipeline_text.splitlines()) >= 200, (
            "The extraction-pipeline reference looks too short to be the "
            "full Phase 2/3/4 lift. Expected hundreds of lines."
        )


class TestSectionStructure:
    """Top-level Phase headings and Phase-internal Step headings exist."""

    @pytest.mark.parametrize(
        "heading",
        [
            "## Phase 2: Survey",
            "## Phase 3: Per-doc extraction loop",
            "## Phase 4: Wrap-up",
        ],
    )
    def test_phase_heading_present(
        self, extraction_pipeline_text: str, heading: str
    ) -> None:
        assert heading in extraction_pipeline_text, (
            f"Reference missing top-level heading {heading!r}. The three "
            "Phase headings (2 Survey, 3 Per-doc loop, 4 Wrap-up) are the "
            "structural anchors the consuming SKILL.md cites."
        )

    @pytest.mark.parametrize(
        "step_heading",
        [
            # Phase 2 survey
            "### Step 0: Pre-flight checks",
            "### Step 1: Bounded skim of every discovered doc",
            "### Step 2: Propose a one-line description per doc",
            "### Step 2.5: Propose a PC roster",
            "### Step 4: Propose a processing order",
            # Phase 3 per-doc loop
            "### Step 0b: Multi-doc loop setup",
            "### Step 0c: Recovery pre-flight (resume-after-crash)",
            "### Step 1: Bounded skim and proposed description",
            "### Step 2: Full read with description as context",
            "### Step 3: Draft the proposed changes",
            "### Step 3b: Cross-doc dedup",
            "### Step 4: Per-doc review via staging directory",
            "### Step 5: Move approved items from staging to final locations",
            "### Step 5b: Capture cross-doc learning",
            "### Step 6: Closing summary",
            # Phase 4 wrap-up
            "### Step 1: Order prompt for missing `order:` values",
            "### Step 2: `campaign.md` composer",
            "### Step 3: Wrap-up commit",
            "### Step 4: Closing summary",
        ],
    )
    def test_step_heading_present(
        self, extraction_pipeline_text: str, step_heading: str
    ) -> None:
        assert step_heading in extraction_pipeline_text, (
            f"Reference missing step heading {step_heading!r}. The Phase "
            "step headings are how the consuming SKILL.md routes the LLM "
            "into specific sub-steps."
        )


# ---------------------------------------------------------------------------
# (b) Pre-approval gate seam (structural presence)
# ---------------------------------------------------------------------------


class TestPreApprovalGateSeam:
    """A documented structural boundary before any staging file is opened.

    The seam is a hook for the future #27 pre-approval staging gate. v0.3
    does not implement the gate; this test pins the seam's documentation
    so future work has a clearly-marked place to slot in.
    """

    def test_top_level_section_present(
        self, extraction_pipeline_text: str
    ) -> None:
        """A top-level `## Pre-approval gate seam` section sets the contract."""
        assert "## Pre-approval gate seam" in extraction_pipeline_text, (
            "Reference is missing the top-level `## Pre-approval gate seam` "
            "section. Slice B documents this as a future-compatibility "
            "structural boundary per ADR-0020 § 'Design seams for future "
            "composability'."
        )

    def test_per_doc_boundary_section_present(
        self, extraction_pipeline_text: str
    ) -> None:
        """A Phase 3 sub-section pins the seam to the per-doc loop boundary."""
        assert (
            "### Pre-approval gate seam — per-doc boundary"
            in extraction_pipeline_text
        ), (
            "Reference is missing the Phase 3 per-doc-boundary sub-section "
            "for the gate seam. The seam needs to be located in the per-doc "
            "loop's structure so a future #27 implementation has an "
            "unambiguous slot."
        )

    def test_seam_references_issue_27(
        self, extraction_pipeline_text: str
    ) -> None:
        """The seam documents its motivation: future #27 work."""
        assert "#27" in extraction_pipeline_text, (
            "The pre-approval gate seam should cite issue #27 (the future "
            "pre-approval staging gate) so the seam's motivation is "
            "self-documenting."
        )

    @pytest.mark.parametrize(
        "invariant_phrase",
        [
            # The four invariants documented in the reference's seam section.
            "No staging file has been opened yet for this doc",
            "No campaign-tree file has been modified yet for this doc",
            "Carried-forward lessons are read-only at the seam",
            "Cancellation at the seam is the cheapest cancel point",
        ],
    )
    def test_seam_invariant_documented(
        self, extraction_pipeline_text: str, invariant_phrase: str
    ) -> None:
        """The seam's invariants pin what a future gate must preserve.

        Without these invariants documented, a future gate implementation
        could accidentally violate them (e.g., open a staging file before
        the gate, modify carried-forward lessons, leave the campaign tree
        in a half-state on cancel).
        """
        assert invariant_phrase in extraction_pipeline_text, (
            f"The pre-approval gate seam invariant {invariant_phrase!r} is "
            "not documented. The seam's value to a future implementer comes "
            "from the invariants the gate must preserve being visible at "
            "the seam location."
        )

    def test_seam_no_gate_logic_in_v03(
        self, extraction_pipeline_text: str
    ) -> None:
        """Slice B is documentation-only; the seam is a no-op in v0.3."""
        assert (
            "no-op pass-through" in extraction_pipeline_text
            or "no gate logic" in extraction_pipeline_text
            or "no-op" in extraction_pipeline_text
        ), (
            "The reference should explicitly say the v0.3 seam carries no "
            "gate logic (it's a no-op pass-through). Without that "
            "marker, the reader could assume the seam already has behavior."
        )


# ---------------------------------------------------------------------------
# (c) Phase 2 survey contract
# ---------------------------------------------------------------------------


class TestPhase2SurveyContract:
    """The survey's stripped/skipped doc-count rules and review batching."""

    @pytest.mark.parametrize(
        "phrase",
        [
            # Single-doc stripped vs zero-doc skipped — load-bearing for the
            # consumer (slice B2's PC roster spec also defers based on these
            # cases).
            "stripped",
            # Zero-doc scaffold-only skips survey entirely.
            "Zero-doc scaffold-only invocations skip survey entirely",
        ],
    )
    def test_doc_count_branch_documented(
        self, extraction_pipeline_text: str, phrase: str
    ) -> None:
        assert phrase in extraction_pipeline_text, (
            f"Phase 2 survey contract is missing the phrase {phrase!r}. The "
            "single-doc stripped / zero-doc skipped distinction is a "
            "load-bearing behavior the consuming SKILL.md depends on."
        )

    def test_both_staged_files_in_same_review_batch(
        self, extraction_pipeline_text: str
    ) -> None:
        """The survey's description and roster files share one continue/cancel ask."""
        # Two staging files, one ask.
        assert (
            "same review batch" in extraction_pipeline_text
            or "single review batch" in extraction_pipeline_text
        ), (
            "Phase 2 survey should document that survey-descriptions.md "
            "and survey-pcs.md present in the same review batch (one "
            "continue/cancel ask covers both)."
        )

    def test_verbal_refinement_uses_edit_per_adr_0015(
        self, extraction_pipeline_text: str
    ) -> None:
        """The verbal-refinement loop uses Edit, not Write — ADR-0015 contract."""
        assert (
            "ADR-0015" in extraction_pipeline_text
            or "0015-conversational-refinement-loop-in-prep-session"
            in extraction_pipeline_text
        ), (
            "Phase 2 survey should cite ADR-0015 for the verbal-refinement "
            "Edit-tool discipline. Without that contract, the refinement "
            "loop's bulk-rewrite anti-pattern can re-emerge."
        )

    @pytest.mark.parametrize(
        "staging_file",
        [
            ".ttrpg-staging/survey-descriptions.md",
            ".ttrpg-staging/survey-pcs.md",
            ".ttrpg-staging/survey-order.md",
        ],
    )
    def test_survey_staging_file_documented(
        self, extraction_pipeline_text: str, staging_file: str
    ) -> None:
        """The three survey staging file paths are documented."""
        assert staging_file in extraction_pipeline_text, (
            f"Phase 2 survey should document the staging file path "
            f"{staging_file!r} so the consuming SKILL.md doesn't need to "
            "duplicate the path discipline."
        )


# ---------------------------------------------------------------------------
# (d) Per-doc commit format
# ---------------------------------------------------------------------------


class TestPerDocCommitFormat:
    """The Step 5.8 commit subject and scoped-staging rule live in the reference."""

    def test_subject_template_documented(
        self, extraction_pipeline_text: str
    ) -> None:
        """The `/ingest doc <N>/<total>: <doc-name> (<summary>)` shape."""
        assert (
            "/ingest doc <N>/<total>: <doc-name> "
            "(<one-line summary of what was extracted>)"
        ) in extraction_pipeline_text, (
            "Reference must show the per-doc commit subject template "
            "verbatim — it's the load-bearing string the LLM follows when "
            "writing per-doc commits."
        )

    @pytest.mark.parametrize(
        "example_subject",
        [
            "/ingest doc 1/12: faerun-gods.md (5 Reference notes, 2 Secrets)",
            "/ingest doc 2/12: lost-mines.md "
            "(Adventure, 12 Reference notes, 4 Beats)",
            "/ingest doc 12/12: session-1-notes.md "
            "(3 Threads, 2 Consequences)",
        ],
    )
    def test_documented_examples_present(
        self, extraction_pipeline_text: str, example_subject: str
    ) -> None:
        """Each example subject from the v0.2 spec round-trips into the reference."""
        assert example_subject in extraction_pipeline_text, (
            f"Reference is missing the example subject {example_subject!r}. "
            "The examples anchor the LLM's pattern-matching for the "
            "kind-count shorthand."
        )

    def test_scoped_staging_rule_documented(
        self, extraction_pipeline_text: str
    ) -> None:
        """Stage explicit paths, never `git add -A`-sweep."""
        assert "never sweep in unrelated GM edits" in extraction_pipeline_text, (
            "Reference should document the scoped-staging discipline "
            "(`git add <paths>` over `git add -A`) so cross-tool GM edits "
            "don't accidentally end up in the per-doc commit."
        )

    @pytest.mark.parametrize(
        "lifecycle_folder",
        ["npcs/", "pcs/", "locations/", "factions/", "items/",
         "adventures/", "threads/", "consequences/", "beats/", "secrets/"],
    )
    def test_lifecycle_folder_enumerated(
        self, extraction_pipeline_text: str, lifecycle_folder: str
    ) -> None:
        """All ten lifecycle/reference folders are enumerated.

        The scoped-staging rule is only enforceable when the LLM knows
        which folders count as "in-scope." The enumeration is the
        canonical list the per-doc commit's `git add` argument list
        derives from.
        """
        assert lifecycle_folder in extraction_pipeline_text, (
            f"Reference is missing the lifecycle folder {lifecycle_folder!r}. "
            "The Phase 3 staging-scope rule enumerates these so the LLM "
            "has an authoritative scope list."
        )


# ---------------------------------------------------------------------------
# (e) Refined cancel-mid-Phase-3 prompt
# ---------------------------------------------------------------------------


class TestCancelPrompt:
    """The three cancel responses + git mechanism + lessons-drop rule."""

    @pytest.mark.parametrize(
        "phrase",
        ["Keep all", "Reset to before doc", "Abandon entirely"],
    )
    def test_three_response_choices_documented(
        self, extraction_pipeline_text: str, phrase: str
    ) -> None:
        """Each of the three cancel branches is named verbatim."""
        assert phrase in extraction_pipeline_text, (
            f"Reference is missing the cancel-prompt branch {phrase!r}. "
            "Without all three named, the LLM can't surface the prompt "
            "shape the GM expects."
        )

    def test_git_reset_hard_mechanism(
        self, extraction_pipeline_text: str
    ) -> None:
        """The reset branches use `git reset --hard`, not a softer reset."""
        assert "git reset --hard" in extraction_pipeline_text, (
            "Reference should specify `git reset --hard` for the Reset/"
            "Abandon branches. A softer reset would leave the working "
            "tree in a half-state."
        )

    def test_lessons_drop_rule_documented(
        self, extraction_pipeline_text: str
    ) -> None:
        """Reset-to-before-doc-K drops lessons with source-doc index ≥ K."""
        assert (
            "Drop every carried-forward lesson whose source-doc index is ≥ K"
            in extraction_pipeline_text
            or "drop every carried-forward lesson whose source-doc index is ≥ K"
            in extraction_pipeline_text
        ), (
            "Reference should document the lessons-drop rule for the "
            "reset-to-before-doc-K branch. Lessons accumulated by docs "
            "≥ K go with their reverted commits; lessons from docs < K "
            "survive (their work is still in the tree)."
        )


# ---------------------------------------------------------------------------
# (f) Recovery pre-flight (Step 0c)
# ---------------------------------------------------------------------------


class TestRecoveryPreflight:
    """Step 0c detects the per-doc-committed-but-no-wrap-up state."""

    def test_detection_command_documented(
        self, extraction_pipeline_text: str
    ) -> None:
        """The `git log --grep '^/ingest doc '` detection mechanism."""
        assert (
            "git log --grep '^/ingest doc '" in extraction_pipeline_text
        ), (
            "Reference's Step 0c should specify the `git log --grep` "
            "command verbatim — it's the detection mechanism the resume "
            "prompt's branching depends on."
        )

    def test_resume_branch_documented(
        self, extraction_pipeline_text: str
    ) -> None:
        """The resume-at-doc-N+1 prompt is documented."""
        assert (
            "Resume at doc N+1" in extraction_pipeline_text
            or "Resume" in extraction_pipeline_text
        ), (
            "Reference's Step 0c should document the resume prompt's "
            "Resume / Abandon-and-rescaffold choice shape."
        )

    def test_abandon_and_rescaffold_branch_documented(
        self, extraction_pipeline_text: str
    ) -> None:
        """The abandon-and-rescaffold branch's `git reset --hard` is documented."""
        assert (
            "Abandon and re-scaffold" in extraction_pipeline_text
            or "abandon and re-scaffold" in extraction_pipeline_text
        ), (
            "Reference's Step 0c should document the abandon branch so the "
            "GM has a clean exit when they don't want to resume."
        )


# ---------------------------------------------------------------------------
# (g) Phase 4 wrap-up
# ---------------------------------------------------------------------------


class TestPhase4WrapUp:
    """The narrowed wrap-up commit subject, composer citation, ingest variants."""

    def test_subject_shape_documented(
        self, extraction_pipeline_text: str
    ) -> None:
        """The narrowed `/ingest wrap-up (<short summary>)` shape."""
        assert (
            "/ingest wrap-up (<short summary>)" in extraction_pipeline_text
            or "`/ingest wrap-up (<short summary>)`"
            in extraction_pipeline_text
        ), (
            "Reference should document the wrap-up commit subject shape "
            "verbatim — it's how the LLM constructs the wrap-up commit."
        )

    def test_canonical_example_documented(
        self, extraction_pipeline_text: str
    ) -> None:
        """The canonical example from the v0.2 spec round-trips."""
        assert (
            "/ingest wrap-up (campaign.md regen, 3 Adventures "
            "backfilled with order: 1/2/3)"
            in extraction_pipeline_text
        ), (
            "Reference should show the canonical wrap-up example so the "
            "LLM has a pattern to mirror."
        )

    def test_no_adventures_backfilled_collapse_documented(
        self, extraction_pipeline_text: str
    ) -> None:
        """When no Adventures need backfilling, the summary collapses."""
        assert (
            "/ingest wrap-up (campaign.md regen)"
            in extraction_pipeline_text
        ), (
            "Reference should show the collapsed wrap-up form for the "
            "case where no Adventures need order: backfilling."
        )

    def test_campaign_overview_composer_cited(
        self, extraction_pipeline_text: str
    ) -> None:
        """Phase 4 Step 2 routes to the shared composer reference."""
        assert (
            "campaign-overview-composer.md" in extraction_pipeline_text
        ), (
            "Reference's Phase 4 Step 2 should cite "
            "campaign-overview-composer.md (the shared composer spec). "
            "Without the citation, the composer's deterministic rendering "
            "rules drift into the per-skill prose."
        )

    def test_ingest_only_variants_named(
        self, extraction_pipeline_text: str
    ) -> None:
        """The three ingest-only composer variants are documented."""
        # Two header lines, full Adventures history, no Consequence truncation.
        assert "Status:** active" in extraction_pipeline_text
        assert "Last event:" in extraction_pipeline_text
        assert (
            "Renders the full `## Adventures` history" in extraction_pipeline_text
            or "full `## Adventures` history" in extraction_pipeline_text
        )
        assert (
            "no top-N truncation" in extraction_pipeline_text
            or "no truncation" in extraction_pipeline_text.lower()
        )

    def test_adventure_order_staging_path(
        self, extraction_pipeline_text: str
    ) -> None:
        """The Phase 4 Step 1 bulk-order-prompt staging path is documented."""
        assert (
            ".ttrpg-staging/adventure-order.md" in extraction_pipeline_text
        ), (
            "Reference's Phase 4 Step 1 should name the staging file "
            "`.ttrpg-staging/adventure-order.md` so the consumer knows "
            "where the bulk-order prompt lives."
        )


# ---------------------------------------------------------------------------
# (h) SKILL.md citations
# ---------------------------------------------------------------------------


class TestSkillCitations:
    """The /ingest SKILL.md cites the reference at Phases 2, 3, and 4."""

    def test_skill_cites_extraction_pipeline(
        self, ingest_skill_text: str
    ) -> None:
        """SKILL.md cites `../../references/extraction-pipeline.md`."""
        assert (
            "../../references/extraction-pipeline.md" in ingest_skill_text
        ), (
            "SKILL.md should cite the extraction-pipeline reference (the "
            "v0.3 lift's whole point). Without the citation, the LLM "
            "doesn't know to read the reference."
        )

    def test_skill_cites_reference_in_phase_2(
        self, ingest_skill_text: str
    ) -> None:
        """Phase 2 section in SKILL.md cites the reference."""
        # Find the Phase 2 section and check the citation appears within it.
        phase_2_idx = ingest_skill_text.find("## Phase 2: Survey")
        phase_3_idx = ingest_skill_text.find(
            "## Phase 3: Per-doc extraction loop"
        )
        assert phase_2_idx >= 0 and phase_3_idx > phase_2_idx
        phase_2_section = ingest_skill_text[phase_2_idx:phase_3_idx]
        assert "extraction-pipeline.md" in phase_2_section, (
            "Phase 2 section in SKILL.md should cite extraction-pipeline.md "
            "(rather than re-inlining the survey prose)."
        )

    def test_skill_cites_reference_in_phase_3(
        self, ingest_skill_text: str
    ) -> None:
        """Phase 3 section in SKILL.md cites the reference."""
        phase_3_idx = ingest_skill_text.find(
            "## Phase 3: Per-doc extraction loop"
        )
        phase_4_idx = ingest_skill_text.find("## Phase 4: Wrap-up")
        assert phase_3_idx >= 0 and phase_4_idx > phase_3_idx
        phase_3_section = ingest_skill_text[phase_3_idx:phase_4_idx]
        assert "extraction-pipeline.md" in phase_3_section, (
            "Phase 3 section in SKILL.md should cite extraction-pipeline.md "
            "(rather than re-inlining the per-doc-loop prose)."
        )

    def test_skill_cites_reference_in_phase_4(
        self, ingest_skill_text: str
    ) -> None:
        """Phase 4 section in SKILL.md cites the reference."""
        phase_4_idx = ingest_skill_text.find("## Phase 4: Wrap-up")
        # Phase 4 runs until "What to avoid" (the next top-level section).
        what_to_avoid_idx = ingest_skill_text.find("## What to avoid")
        assert phase_4_idx >= 0 and what_to_avoid_idx > phase_4_idx
        phase_4_section = ingest_skill_text[phase_4_idx:what_to_avoid_idx]
        assert "extraction-pipeline.md" in phase_4_section, (
            "Phase 4 section in SKILL.md should cite extraction-pipeline.md "
            "(rather than re-inlining the wrap-up prose)."
        )

    def test_skill_phase_2_step_2_5_preserved(
        self, ingest_skill_text: str
    ) -> None:
        """Phase 2 Step 2.5 (PC roster) remains in SKILL.md.

        Slice B2 owns Step 2.5 (the PC roster proposal). Slice B's SKILL.md
        edits must leave Step 2.5 intact so B2 can keep evolving it
        independently. This test pins that the section header is still
        present in SKILL.md after slice B's lift.
        """
        assert (
            "### Step 2.5: Propose a PC roster from skim signals"
            in ingest_skill_text
        ), (
            "SKILL.md should still contain Phase 2 Step 2.5 (PC roster) — "
            "that section is slice B2's domain, not slice B's. Slice B "
            "lifts Phases 2/3/4 *minus Step 2.5* into the reference."
        )

    def test_skill_phase_1_cites_scaffolder_reference(
        self, ingest_skill_text: str
    ) -> None:
        """Phase 1 (Scaffold) cites the scaffolder reference per slice A.

        Phase 1 is slice A's scope. Slice B's edits must not touch the
        Phase 1 section. After slice A merged, the Phase 1 step prose was
        lifted to ``references/scaffolder.md`` and SKILL.md now cites that
        reference. This test guards that B's edits left Phase 1's citation
        shape intact.
        """
        assert "## Phase 1: Scaffold" in ingest_skill_text
        assert "../../references/scaffolder.md" in ingest_skill_text, (
            "Phase 1 in SKILL.md must cite ../../references/scaffolder.md "
            "(the scaffolder reference established by slice A). "
            "Slice B does not modify Phase 1."
        )


# ---------------------------------------------------------------------------
# (i) Cross-doc dedup, carried-forward lessons, staging-pattern citation
# ---------------------------------------------------------------------------


class TestSharedReferenceCitations:
    """The reference cites the other shared references it depends on."""

    @pytest.mark.parametrize(
        "cited_reference",
        [
            # The cross-doc dedup rule lives in dedup-matching.md.
            "dedup-matching.md",
            # The staging-file review pattern lives in staging-pattern.md.
            "staging-pattern.md",
            # The campaign.md composer lives in campaign-overview-composer.md.
            "campaign-overview-composer.md",
            # Schema fields for lifecycle objects live in frontmatter-schemas.md.
            "frontmatter-schemas.md",
            # Reference-note extraction rules.
            "reference-note-extraction.md",
            # Secret extraction rules.
            "secret-extraction.md",
            # Secret validation rules.
            "secret-store.md",
            # Beat kind classification.
            "beat-kind-classification.md",
            # Bidi link maintenance.
            "bidi-link-maintenance.md",
            # PC roster proposal (slice B2's domain).
            "pc-roster-proposal.md",
        ],
    )
    def test_shared_reference_cited(
        self, extraction_pipeline_text: str, cited_reference: str
    ) -> None:
        """Each shared reference the extraction pipeline depends on is cited."""
        assert cited_reference in extraction_pipeline_text, (
            f"Reference should cite {cited_reference!r} — the extraction "
            "pipeline depends on the rules / schemas / matching procedure "
            "the cited reference defines. Without the citation, the "
            "consumer would have to read multiple SKILL.md files to "
            "reconstruct the cross-reference graph."
        )


class TestCarriedForwardLessons:
    """The cross-doc learning structure is documented."""

    def test_carried_forward_lessons_structure_present(
        self, extraction_pipeline_text: str
    ) -> None:
        """The `carried-forward lessons` term is used consistently."""
        # The phrase appears multiple times across Phase 3's Step 0b, Step 2,
        # Step 4a, Step 5b, the cancel-prompt branch, etc.
        count = extraction_pipeline_text.count("carried-forward lesson")
        assert count >= 5, (
            "The 'carried-forward lessons' structure should be mentioned "
            f"in multiple sections of the reference; found {count} matches. "
            "It's the load-bearing structure tying cross-doc dedup, Step 5b "
            "learning capture, and the reset-to-before-doc-K cancel branch "
            "together."
        )

    def test_source_doc_index_tagging(
        self, extraction_pipeline_text: str
    ) -> None:
        """Lessons are tagged with their source-doc index for reset-K dropping."""
        assert (
            "source-doc index" in extraction_pipeline_text
            or "source_doc_index" in extraction_pipeline_text
        ), (
            "The reference should document that each carried-forward lesson "
            "is tagged with its source-doc index. Without that tag, the "
            "reset-to-before-doc-K branch can't drop the right subset of "
            "lessons deterministically."
        )


# ---------------------------------------------------------------------------
# (j) Relative-path discipline (per #69 / ADR-0020 / PR #79)
# ---------------------------------------------------------------------------


class TestRelativePathDiscipline:
    """The reference uses relative paths (no absolute install paths).

    Per `tests/test_plugin_manifest.py::TestRelativePathsInProse`, markdown
    prose under `skills/` and `references/` must use relative paths because
    `${CLAUDE_PLUGIN_ROOT}` only resolves in JSON, not markdown
    (anthropics/claude-code#9354). The plugin manifest test enforces this
    globally; this test repeats the check inside the extraction-pipeline
    reference so a future edit can't accidentally re-introduce the
    absolute form.
    """

    ABSOLUTE_INSTALL_PREFIX: str = "~/.claude/skills/ttrpg-gm"

    def test_no_absolute_install_path(
        self, extraction_pipeline_text: str
    ) -> None:
        assert (
            self.ABSOLUTE_INSTALL_PREFIX not in extraction_pipeline_text
        ), (
            f"The extraction-pipeline reference contains the absolute "
            f"install path `{self.ABSOLUTE_INSTALL_PREFIX}`. Per #69, "
            "markdown prose must use relative paths only."
        )

    def test_no_skill_md_double_dot_prefix_within_references_dir(
        self, extraction_pipeline_text: str
    ) -> None:
        """Citations from references/ to references/ use bare filenames.

        Sibling references in `references/` are reachable as bare
        filenames (e.g., `dedup-matching.md`, not `./dedup-matching.md`
        or `../references/dedup-matching.md`). This is the convention
        the other refs follow.
        """
        # Check that the citations don't have a "../references/" or
        # "./" prefix when citing sibling references.
        for line in extraction_pipeline_text.splitlines():
            assert "../references/" not in line, (
                "extraction-pipeline.md is itself in references/; sibling "
                "references should be cited as bare filenames "
                "(e.g., `dedup-matching.md`), not `../references/...`. "
                f"Offending line: {line!r}"
            )


# ---------------------------------------------------------------------------
# (k) Survey-stage flow checks at a smoke-test level
# ---------------------------------------------------------------------------


class TestSurveyStageFlow:
    """Smoke test the survey staging file flow described in the reference.

    This is a reference-implementation-style test that mirrors what
    `test_ingest_per_doc_commits.py` does for the per-doc commit shape —
    encode the documented file lifecycle as Python and verify it round-
    trips against the spec.
    """

    def _spec_says(self, text: str, *needles: str) -> None:
        for n in needles:
            assert n in text, (
                f"Reference is missing the marker phrase {n!r}; the "
                "survey flow smoke test depends on it."
            )

    def test_survey_descriptions_format_documented(
        self, extraction_pipeline_text: str
    ) -> None:
        """Description list: header line, path lines, description lines."""
        self._spec_says(
            extraction_pipeline_text,
            ".ttrpg-staging/survey-descriptions.md",
            "edit contract",
        )

    def test_survey_pcs_defers_to_pc_roster_reference(
        self, extraction_pipeline_text: str
    ) -> None:
        """Step 3b for the PC roster defers entirely to pc-roster-proposal.md."""
        # Step 3b's content is just `Per `pc-roster-proposal.md`.`. Confirm
        # the deferral is visible.
        assert "pc-roster-proposal.md" in extraction_pipeline_text

    def test_survey_order_format_documented(
        self, extraction_pipeline_text: str
    ) -> None:
        """Processing order: world-info → adventures → session-shaped default."""
        self._spec_says(
            extraction_pipeline_text,
            ".ttrpg-staging/survey-order.md",
            "world info first, adventures next, session-shaped docs last",
        )

    def test_survey_cleanup_at_step_5c(
        self, extraction_pipeline_text: str
    ) -> None:
        """All three survey staging files are deleted at handoff."""
        # The Step 5c cleanup names each file by path.
        self._spec_says(
            extraction_pipeline_text,
            ".ttrpg-staging/survey-descriptions.md",
            ".ttrpg-staging/survey-pcs.md",
            ".ttrpg-staging/survey-order.md",
        )


# ---------------------------------------------------------------------------
# (l) Phase 4 deterministic regen of campaign.md
# ---------------------------------------------------------------------------


class TestPhase4DeterministicRegen:
    """Phase 4's campaign.md regen is a deterministic function of state.

    The composer at `campaign-overview-composer.md` carries the determinism
    contract (pinned by `test_wrap_session_idempotency.py`'s
    TestCampaignMdRegenerationIsDeterministic). The extraction-pipeline
    reference should make the determinism property explicit so the LLM
    knows not to inject non-deterministic content (e.g., current time, a
    sample dice roll for flavor) into the regen.
    """

    def test_determinism_property_documented(
        self, extraction_pipeline_text: str
    ) -> None:
        """The composer's determinism contract is surfaced in the reference."""
        # The reference's "Determinism and idempotence" section pins this.
        assert (
            "## Determinism and idempotence" in extraction_pipeline_text
            or "deterministic function" in extraction_pipeline_text
        ), (
            "Reference should document the campaign.md regen's determinism "
            "property — given identical campaign state, two runs produce "
            "byte-identical output (per the campaign-overview-composer.md "
            "contract)."
        )

    def test_idempotence_of_recovery_preflight(
        self, extraction_pipeline_text: str
    ) -> None:
        """The recovery pre-flight is idempotent across invocations."""
        assert (
            "idempotent" in extraction_pipeline_text
        ), (
            "Reference should note the recovery pre-flight's idempotence — "
            "running on an already-completed campaign (per-doc commits + "
            "wrap-up) detects the wrap-up and proceeds without prompting."
        )
