"""Behavioral tests for the shared campaign-repo location pattern.

Per issue #111 and [ADR-0020](../docs/adr/0020-modularization-via-shared-references.md),
the marker check that decides "is this a scaffolded campaign repo?" is
lifted into `references/campaign-locate.md` as a single source of
truth consumed by four orchestration shapes:

- **Hard-stop** — `/ingest`'s precondition: missing markers → hard-stop
  with the verbatim message naming `/init-campaign` and `/ingest`.
- **Locate-or-ask** — `/prep-session` and `/wrap-session` Step 0: check
  cwd; on miss, ask the GM for the campaign path; re-check there.
- **Auto-detect mode** — `/init-adventure`: markers present →
  in-campaign mode; markers absent (and cwd empty) → standalone mode;
  partial → ask the GM; non-campaign content → ask the GM.
- **Already-scaffolded?** — `/init-campaign`: markers present → bail;
  markers absent → invoke the scaffolder reference.

These tests embed a small **reference marker check** in Python — a
faithful translation of `references/campaign-locate.md`'s four-marker
list — and exercise the four orchestration shapes against `tmp_path`
directories.

The central pinned invariant is that **all four shapes consult the
same marker set** even though their routing decisions differ. A
future change to the marker set (adding a fifth required file,
dropping one) must update the shared reference once, not four
SKILL.md files individually.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import pytest


# --------------------------------------------------------------------------
# The canonical four-marker list from `references/campaign-locate.md`.
# Pinned here so any drift between the test and the reference surfaces
# as a failure.
# --------------------------------------------------------------------------

CAMPAIGN_LOCATE_MARKERS: tuple[str, ...] = (
    "CLAUDE.md",
    ".claude/rules/sessions.md",
    ".claude/rules/adventures.md",
    "campaign.md",
)


# --------------------------------------------------------------------------
# Reference marker-check implementation — `is_file()`-equivalent
# presence test, no content validation. Mirrors the canonical check
# documented in `references/campaign-locate.md`'s "The four-marker set"
# section.
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class MarkerCheckResult:
    """Outcome of running the marker check against a target directory.

    `present` lists the markers that are present. `missing` lists the
    ones that are absent. `all_present` is True iff every marker is
    present (the "scaffolded" condition).
    """

    present: tuple[str, ...]
    missing: tuple[str, ...]

    @property
    def all_present(self) -> bool:
        return not self.missing

    @property
    def all_absent(self) -> bool:
        return not self.present


def check_markers(target: Path) -> MarkerCheckResult:
    """Run the four-marker check against `target`.

    Returns which markers are present and which are missing. Read-only
    inspection — no writes. Content is not validated; presence is the
    sole criterion per `references/campaign-locate.md`.
    """
    present = []
    missing = []
    for marker in CAMPAIGN_LOCATE_MARKERS:
        if (target / marker).is_file():
            present.append(marker)
        else:
            missing.append(marker)
    return MarkerCheckResult(
        present=tuple(present),
        missing=tuple(missing),
    )


# --------------------------------------------------------------------------
# Shape A — Hard-stop (`/ingest` precondition)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class HardStopResult:
    """Outcome of `/ingest`'s precondition check.

    `proceed` is True when every marker is present (the silent-success
    case). `proceed` is False when any marker is missing — the skill
    surfaces the verbatim hard-stop message and exits without any
    filesystem write.
    """

    proceed: bool
    missing: tuple[str, ...]


def shape_a_hard_stop(target: Path) -> HardStopResult:
    """Apply the Hard-stop shape from `references/campaign-locate.md`.

    `/ingest`'s precondition: read-only inspection, no fallback, no
    conversational recovery. Missing markers route the GM to
    `/init-campaign` via a verbatim hard-stop message; the message
    text is owned by the consuming SKILL.md per the reference's
    "skill-specific phrasing" carve-out, not by this Python.
    """
    result = check_markers(target)
    return HardStopResult(
        proceed=result.all_present,
        missing=result.missing,
    )


# --------------------------------------------------------------------------
# Shape B — Locate-or-ask (`/prep-session`, `/wrap-session` Step 0)
# --------------------------------------------------------------------------


class LocateOrAskOutcome(Enum):
    """The three terminal outcomes of the Locate-or-ask shape.

    USE_CWD — cwd's markers all pass; use cwd as the campaign root.
    USE_GM_PATH — cwd missed but a GM-supplied path passed; use that.
    STOP_NOT_SCAFFOLDED — cwd missed and the GM-supplied path also
        missed (or the GM gave none); surface what was missing and stop.
    """

    USE_CWD = "use_cwd"
    USE_GM_PATH = "use_gm_path"
    STOP_NOT_SCAFFOLDED = "stop_not_scaffolded"


@dataclass(frozen=True)
class LocateOrAskResult:
    outcome: LocateOrAskOutcome
    campaign_root: Path | None
    missing_at_terminal: tuple[str, ...]


def shape_b_locate_or_ask(
    cwd: Path,
    gm_supplied_path: Path | None = None,
) -> LocateOrAskResult:
    """Apply the Locate-or-ask shape from `references/campaign-locate.md`.

    Used by `/prep-session` Step 0 and `/wrap-session` Step 0. Check
    cwd first; if any marker is missing and the GM has been asked for
    an alternative path, re-check there. The GM-facing prompt phrasing
    lives in the consuming SKILL.md.

    `gm_supplied_path` simulates the GM's answer to the
    "Where is the campaign repo?" question. None means the GM was not
    asked yet (we're at the cwd-only stage); pass a path to model the
    re-check on the GM's answer.
    """
    cwd_result = check_markers(cwd)
    if cwd_result.all_present:
        return LocateOrAskResult(
            outcome=LocateOrAskOutcome.USE_CWD,
            campaign_root=cwd,
            missing_at_terminal=(),
        )

    # cwd missed — Locate-or-ask now asks the GM. If no GM path was
    # supplied for the model run, the terminal state is
    # STOP_NOT_SCAFFOLDED reporting cwd's missing markers.
    if gm_supplied_path is None:
        return LocateOrAskResult(
            outcome=LocateOrAskOutcome.STOP_NOT_SCAFFOLDED,
            campaign_root=None,
            missing_at_terminal=cwd_result.missing,
        )

    gm_result = check_markers(gm_supplied_path)
    if gm_result.all_present:
        return LocateOrAskResult(
            outcome=LocateOrAskOutcome.USE_GM_PATH,
            campaign_root=gm_supplied_path,
            missing_at_terminal=(),
        )

    return LocateOrAskResult(
        outcome=LocateOrAskOutcome.STOP_NOT_SCAFFOLDED,
        campaign_root=None,
        missing_at_terminal=gm_result.missing,
    )


# --------------------------------------------------------------------------
# Shape C — Auto-detect mode (`/init-adventure` Step 0a)
# --------------------------------------------------------------------------


class AutoDetectMode(Enum):
    """The four routing outcomes of the Auto-detect mode shape."""

    IN_CAMPAIGN = "in_campaign"
    STANDALONE = "standalone"
    ASK_PARTIAL_SCAFFOLD = "ask_partial_scaffold"
    ASK_NON_CAMPAIGN_CONTENT = "ask_non_campaign_content"


@dataclass(frozen=True)
class AutoDetectResult:
    mode: AutoDetectMode
    missing: tuple[str, ...]
    present: tuple[str, ...]


def shape_c_auto_detect(
    cwd: Path,
    cwd_has_non_campaign_content: bool = False,
) -> AutoDetectResult:
    """Apply the Auto-detect mode shape from `references/campaign-locate.md`.

    Used by `/init-adventure` Step 0a. The shape never writes; the
    GM confirmation prompt before any filesystem write lives in
    Step 0b of the consuming SKILL.md.

    `cwd_has_non_campaign_content` models the case where the GM has
    not yet confirmed loose files are safe to scaffold alongside —
    when True and no markers are present, the shape asks rather than
    routes silently to standalone.
    """
    result = check_markers(cwd)

    if result.all_present:
        return AutoDetectResult(
            mode=AutoDetectMode.IN_CAMPAIGN,
            missing=result.missing,
            present=result.present,
        )

    if result.all_absent:
        if cwd_has_non_campaign_content:
            return AutoDetectResult(
                mode=AutoDetectMode.ASK_NON_CAMPAIGN_CONTENT,
                missing=result.missing,
                present=result.present,
            )
        return AutoDetectResult(
            mode=AutoDetectMode.STANDALONE,
            missing=result.missing,
            present=result.present,
        )

    # Partial — some markers present, others absent. Always ask.
    return AutoDetectResult(
        mode=AutoDetectMode.ASK_PARTIAL_SCAFFOLD,
        missing=result.missing,
        present=result.present,
    )


# --------------------------------------------------------------------------
# Shape D — Already-scaffolded? (`/init-campaign` Step 7 / D1)
# --------------------------------------------------------------------------


class AlreadyScaffoldedRouting(Enum):
    """The three routing outcomes of the Already-scaffolded? shape."""

    REFUSE_TO_CLOBBER = "refuse_to_clobber"
    PROCEED_WITH_SCAFFOLD = "proceed_with_scaffold"
    ASK_NON_CAMPAIGN_CONTENT = "ask_non_campaign_content"


@dataclass(frozen=True)
class AlreadyScaffoldedResult:
    routing: AlreadyScaffoldedRouting
    present: tuple[str, ...]
    missing: tuple[str, ...]


def shape_d_already_scaffolded(
    target: Path,
    target_has_non_campaign_content: bool = False,
) -> AlreadyScaffoldedResult:
    """Apply the Already-scaffolded? shape from `references/campaign-locate.md`.

    Used by `/init-campaign` Steps 7 and D1 via delegation to the
    scaffolder reference. If any campaign-content marker is present
    the scaffolder refuses to clobber; if none are present and the
    directory is empty / nonexistent, the scaffolder proceeds. The
    `.git/`-as-marker case the scaffolder additionally consults is
    out of scope here — the campaign-locate reference's marker set is
    the campaign-content subset.
    """
    result = check_markers(target)

    if not result.all_absent:
        return AlreadyScaffoldedResult(
            routing=AlreadyScaffoldedRouting.REFUSE_TO_CLOBBER,
            present=result.present,
            missing=result.missing,
        )

    if target_has_non_campaign_content:
        return AlreadyScaffoldedResult(
            routing=AlreadyScaffoldedRouting.ASK_NON_CAMPAIGN_CONTENT,
            present=result.present,
            missing=result.missing,
        )

    return AlreadyScaffoldedResult(
        routing=AlreadyScaffoldedRouting.PROCEED_WITH_SCAFFOLD,
        present=result.present,
        missing=result.missing,
    )


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------


@pytest.fixture
def scaffolded_target(tmp_path: Path) -> Path:
    """Create a target directory with all four markers present."""
    target = tmp_path / "scaffolded"
    target.mkdir()
    for marker in CAMPAIGN_LOCATE_MARKERS:
        path = target / marker
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
    return target


@pytest.fixture
def empty_target(tmp_path: Path) -> Path:
    """Create an empty target directory."""
    target = tmp_path / "empty"
    target.mkdir()
    return target


@pytest.fixture
def partial_target(tmp_path: Path) -> Path:
    """Create a partially-scaffolded directory (only 2 of 4 markers)."""
    target = tmp_path / "partial"
    target.mkdir()
    for marker in (CAMPAIGN_LOCATE_MARKERS[0], CAMPAIGN_LOCATE_MARKERS[3]):
        path = target / marker
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
    return target


# --------------------------------------------------------------------------
# Tests — marker-set consistency across the four shapes
# --------------------------------------------------------------------------


class TestMarkerSetIsCanonical:
    """The marker set is shared across all four shapes.

    The whole point of lifting the marker check to a shared reference
    is single source of truth. These tests pin the marker list and
    verify each shape consults the same set.
    """

    def test_marker_list_is_exactly_four_files(self) -> None:
        """Per `references/campaign-locate.md`, the marker set is exactly four."""
        assert len(CAMPAIGN_LOCATE_MARKERS) == 4, (
            "campaign-locate.md documents exactly four markers; the "
            f"reference test sees {len(CAMPAIGN_LOCATE_MARKERS)}."
        )

    def test_marker_list_contains_claude_md(self) -> None:
        assert "CLAUDE.md" in CAMPAIGN_LOCATE_MARKERS

    def test_marker_list_contains_sessions_rule(self) -> None:
        assert ".claude/rules/sessions.md" in CAMPAIGN_LOCATE_MARKERS

    def test_marker_list_contains_adventures_rule(self) -> None:
        assert ".claude/rules/adventures.md" in CAMPAIGN_LOCATE_MARKERS

    def test_marker_list_contains_campaign_md(self) -> None:
        assert "campaign.md" in CAMPAIGN_LOCATE_MARKERS


class TestMarkerSetConsistencyAcrossShapes:
    """Every shape consults the same four-marker set.

    The central invariant the lift-to-shared-reference cleanup pins:
    Hard-stop, Locate-or-ask, Auto-detect mode, and Already-scaffolded?
    all consult the same marker list, even though they route on the
    result differently. A future change that drifts the marker set in
    one shape but not the others is exactly the duplicate-and-drift
    failure mode the reference is preventing.
    """

    def test_shape_a_consults_canonical_markers(
        self, scaffolded_target: Path
    ) -> None:
        """Hard-stop passes when every canonical marker is present."""
        result = shape_a_hard_stop(scaffolded_target)
        assert result.proceed

    def test_shape_b_consults_canonical_markers(
        self, scaffolded_target: Path
    ) -> None:
        """Locate-or-ask uses cwd when every canonical marker is present."""
        result = shape_b_locate_or_ask(scaffolded_target)
        assert result.outcome == LocateOrAskOutcome.USE_CWD

    def test_shape_c_consults_canonical_markers(
        self, scaffolded_target: Path
    ) -> None:
        """Auto-detect mode picks in-campaign when every canonical marker is present."""
        result = shape_c_auto_detect(scaffolded_target)
        assert result.mode == AutoDetectMode.IN_CAMPAIGN

    def test_shape_d_consults_canonical_markers(
        self, scaffolded_target: Path
    ) -> None:
        """Already-scaffolded? refuses to clobber when every canonical marker is present."""
        result = shape_d_already_scaffolded(scaffolded_target)
        assert result.routing == AlreadyScaffoldedRouting.REFUSE_TO_CLOBBER

    @pytest.mark.parametrize("missing_marker", CAMPAIGN_LOCATE_MARKERS)
    def test_every_marker_is_load_bearing_in_shape_a(
        self,
        scaffolded_target: Path,
        missing_marker: str,
    ) -> None:
        """Deleting any single marker makes Hard-stop fail.

        Parametrized over every marker individually so the test
        surfaces which markers Hard-stop treats as load-bearing —
        every one of them. A shape that ignored any single marker
        would route differently than the reference spec.
        """
        (scaffolded_target / missing_marker).unlink()
        result = shape_a_hard_stop(scaffolded_target)
        assert not result.proceed, (
            f"Shape A should fail when {missing_marker} is missing."
        )
        assert missing_marker in result.missing

    @pytest.mark.parametrize("missing_marker", CAMPAIGN_LOCATE_MARKERS)
    def test_every_marker_is_load_bearing_in_shape_b(
        self,
        scaffolded_target: Path,
        missing_marker: str,
    ) -> None:
        """Deleting any single marker makes Locate-or-ask fall through to the ask branch."""
        (scaffolded_target / missing_marker).unlink()
        result = shape_b_locate_or_ask(scaffolded_target)
        # With no GM path supplied we hit STOP_NOT_SCAFFOLDED.
        assert result.outcome == LocateOrAskOutcome.STOP_NOT_SCAFFOLDED
        assert missing_marker in result.missing_at_terminal

    @pytest.mark.parametrize("missing_marker", CAMPAIGN_LOCATE_MARKERS)
    def test_every_marker_is_load_bearing_in_shape_c(
        self,
        scaffolded_target: Path,
        missing_marker: str,
    ) -> None:
        """Deleting any single marker makes Auto-detect mode drop out of in-campaign."""
        (scaffolded_target / missing_marker).unlink()
        result = shape_c_auto_detect(scaffolded_target)
        # With three of four markers present we hit the partial branch
        # (ASK_PARTIAL_SCAFFOLD) — not in-campaign.
        assert result.mode != AutoDetectMode.IN_CAMPAIGN
        assert missing_marker in result.missing

    @pytest.mark.parametrize("missing_marker", CAMPAIGN_LOCATE_MARKERS)
    def test_every_marker_is_load_bearing_in_shape_d(
        self,
        scaffolded_target: Path,
        missing_marker: str,
    ) -> None:
        """Deleting any single marker still trips Already-scaffolded?'s refuse-to-clobber.

        Already-scaffolded? refuses to clobber if **any** marker is
        present — even one alone is enough to signal "something
        campaign-shaped lives here." The shape is asymmetric with the
        others: every other shape requires *all four* present to
        proceed silently; Shape D requires *all four absent* to
        proceed with the scaffold.
        """
        (scaffolded_target / missing_marker).unlink()
        result = shape_d_already_scaffolded(scaffolded_target)
        # 3 of 4 markers remaining is still enough to refuse the scaffold.
        assert result.routing == AlreadyScaffoldedRouting.REFUSE_TO_CLOBBER


# --------------------------------------------------------------------------
# Shape-A specific tests
# --------------------------------------------------------------------------


class TestShapeAHardStop:
    """`/ingest`'s precondition routing."""

    def test_passes_when_all_markers_present(
        self, scaffolded_target: Path
    ) -> None:
        result = shape_a_hard_stop(scaffolded_target)
        assert result.proceed
        assert result.missing == ()

    def test_fails_on_empty_directory(self, empty_target: Path) -> None:
        result = shape_a_hard_stop(empty_target)
        assert not result.proceed
        assert set(result.missing) == set(CAMPAIGN_LOCATE_MARKERS)

    def test_fails_on_partial_scaffold(self, partial_target: Path) -> None:
        result = shape_a_hard_stop(partial_target)
        assert not result.proceed
        # Two markers were missing in the fixture.
        assert len(result.missing) == 2

    def test_fails_on_source_doc_directory(self, tmp_path: Path) -> None:
        """Source-doc-only directory — the v0.1/v0.2 GM muscle-memory case."""
        target = tmp_path / "source-docs"
        target.mkdir()
        (target / "lost-mines.md").write_text("# Lost Mines\n")
        result = shape_a_hard_stop(target)
        assert not result.proceed
        assert set(result.missing) == set(CAMPAIGN_LOCATE_MARKERS)


# --------------------------------------------------------------------------
# Shape-B specific tests
# --------------------------------------------------------------------------


class TestShapeBLocateOrAsk:
    """`/prep-session` and `/wrap-session` Step 0 routing."""

    def test_use_cwd_when_cwd_passes(
        self, scaffolded_target: Path
    ) -> None:
        result = shape_b_locate_or_ask(scaffolded_target)
        assert result.outcome == LocateOrAskOutcome.USE_CWD
        assert result.campaign_root == scaffolded_target

    def test_stop_when_cwd_misses_and_no_gm_path(
        self, empty_target: Path
    ) -> None:
        result = shape_b_locate_or_ask(empty_target)
        assert result.outcome == LocateOrAskOutcome.STOP_NOT_SCAFFOLDED
        assert result.campaign_root is None

    def test_use_gm_path_when_gm_path_passes(
        self, scaffolded_target: Path, empty_target: Path
    ) -> None:
        """cwd misses, but GM supplies a path that has all markers."""
        result = shape_b_locate_or_ask(
            cwd=empty_target,
            gm_supplied_path=scaffolded_target,
        )
        assert result.outcome == LocateOrAskOutcome.USE_GM_PATH
        assert result.campaign_root == scaffolded_target

    def test_stop_when_both_cwd_and_gm_path_miss(
        self, empty_target: Path, tmp_path: Path
    ) -> None:
        """cwd misses; GM supplies a path that also misses."""
        other_empty = tmp_path / "also-empty"
        other_empty.mkdir()
        result = shape_b_locate_or_ask(
            cwd=empty_target,
            gm_supplied_path=other_empty,
        )
        assert result.outcome == LocateOrAskOutcome.STOP_NOT_SCAFFOLDED
        assert result.campaign_root is None
        assert set(result.missing_at_terminal) == set(CAMPAIGN_LOCATE_MARKERS)


# --------------------------------------------------------------------------
# Shape-C specific tests
# --------------------------------------------------------------------------


class TestShapeCAutoDetect:
    """`/init-adventure` Step 0a routing."""

    def test_in_campaign_when_all_markers_present(
        self, scaffolded_target: Path
    ) -> None:
        result = shape_c_auto_detect(scaffolded_target)
        assert result.mode == AutoDetectMode.IN_CAMPAIGN

    def test_standalone_when_directory_is_empty(
        self, empty_target: Path
    ) -> None:
        result = shape_c_auto_detect(empty_target)
        assert result.mode == AutoDetectMode.STANDALONE

    def test_ask_partial_when_some_markers_present(
        self, partial_target: Path
    ) -> None:
        """Some markers present, others absent — never silently route."""
        result = shape_c_auto_detect(partial_target)
        assert result.mode == AutoDetectMode.ASK_PARTIAL_SCAFFOLD
        # The reported present/missing lists reflect the partial state.
        assert len(result.present) == 2
        assert len(result.missing) == 2

    def test_ask_when_non_campaign_content_unconfirmed(
        self, empty_target: Path
    ) -> None:
        """Loose files present and not GM-confirmed safe — ask before routing."""
        result = shape_c_auto_detect(
            cwd=empty_target,
            cwd_has_non_campaign_content=True,
        )
        assert result.mode == AutoDetectMode.ASK_NON_CAMPAIGN_CONTENT


# --------------------------------------------------------------------------
# Shape-D specific tests
# --------------------------------------------------------------------------


class TestShapeDAlreadyScaffolded:
    """`/init-campaign` Steps 7 / D1 routing via the scaffolder."""

    def test_refuse_when_all_markers_present(
        self, scaffolded_target: Path
    ) -> None:
        result = shape_d_already_scaffolded(scaffolded_target)
        assert result.routing == AlreadyScaffoldedRouting.REFUSE_TO_CLOBBER

    def test_refuse_when_any_marker_present(
        self, partial_target: Path
    ) -> None:
        """Even a single marker present is enough to refuse to clobber.

        This is Shape D's asymmetric behavior versus Shapes A/B/C —
        the scaffolder's idempotency contract is "destructive of an
        empty target, protective of a populated one." A directory
        with *any* marker is treated as populated.
        """
        result = shape_d_already_scaffolded(partial_target)
        assert result.routing == AlreadyScaffoldedRouting.REFUSE_TO_CLOBBER

    def test_proceed_when_directory_is_empty(
        self, empty_target: Path
    ) -> None:
        result = shape_d_already_scaffolded(empty_target)
        assert result.routing == AlreadyScaffoldedRouting.PROCEED_WITH_SCAFFOLD

    def test_ask_when_non_campaign_content_present(
        self, empty_target: Path
    ) -> None:
        """Loose files present — scaffolder Step 1.4 asks the GM."""
        result = shape_d_already_scaffolded(
            target=empty_target,
            target_has_non_campaign_content=True,
        )
        assert result.routing == AlreadyScaffoldedRouting.ASK_NON_CAMPAIGN_CONTENT


# --------------------------------------------------------------------------
# SKILL.md surface drift detection
# --------------------------------------------------------------------------


class TestReferenceCitationsInSkillMd:
    """Every consuming SKILL.md cites `references/campaign-locate.md`.

    The whole point of the modularization is that each SKILL.md
    points at the shared reference instead of inlining the marker
    list. These tests pin that the citation is present so a future
    SKILL.md edit that re-inlines the marker list surfaces as a
    failure.
    """

    SKILL_PATHS_THAT_MUST_CITE = (
        "skills/ingest/SKILL.md",
        "skills/prep-session/SKILL.md",
        "skills/wrap-session/SKILL.md",
        "skills/init-adventure/SKILL.md",
        "skills/init-campaign/SKILL.md",
    )

    @pytest.mark.parametrize("skill_path", SKILL_PATHS_THAT_MUST_CITE)
    def test_skill_md_cites_campaign_locate_reference(
        self,
        repo_root: Path,
        skill_path: str,
    ) -> None:
        """The SKILL.md must reference `campaign-locate.md` by relative path.

        The relative path from a `skills/<name>/SKILL.md` to a
        `references/<name>.md` is `../../references/<name>.md`.
        """
        text = (repo_root / skill_path).read_text(encoding="utf-8")
        assert "campaign-locate.md" in text, (
            f"{skill_path} does not cite `campaign-locate.md`. "
            "The shared marker check was lifted to a reference; the "
            "SKILL.md must cite it rather than re-inlining the marker "
            "list."
        )

    def test_reference_file_exists(self, repo_root: Path) -> None:
        """The reference file itself exists at the expected path."""
        reference_path = repo_root / "references" / "campaign-locate.md"
        assert reference_path.is_file(), (
            "`references/campaign-locate.md` is missing. Every consuming "
            "SKILL.md cites it; without the file, the citations dangle."
        )

    def test_reference_documents_four_markers(self, repo_root: Path) -> None:
        """The reference's prose names all four markers verbatim."""
        text = (
            repo_root / "references" / "campaign-locate.md"
        ).read_text(encoding="utf-8")
        for marker in CAMPAIGN_LOCATE_MARKERS:
            # The marker can appear in inline code, as a list bullet,
            # or in prose. We pin presence by substring; the formatting
            # is the reference's editorial choice.
            assert marker in text, (
                f"`references/campaign-locate.md` does not mention "
                f"`{marker}` — the four-marker list is incomplete."
            )

    def test_reference_documents_four_shapes(self, repo_root: Path) -> None:
        """The reference's prose names all four orchestration shapes."""
        text = (
            repo_root / "references" / "campaign-locate.md"
        ).read_text(encoding="utf-8")
        # Shape names pinned per the reference's structure.
        for shape_name in (
            "Hard-stop",
            "Locate-or-ask",
            "Auto-detect mode",
            "Already-scaffolded?",
        ):
            assert shape_name in text, (
                f"`references/campaign-locate.md` does not name the "
                f"`{shape_name}` shape — the four shapes are incomplete."
            )


class TestIngestVerbatimMessagePreserved:
    """Slice G's verbatim hard-stop message stays in `/ingest`'s SKILL.md.

    Lifting the marker check to a shared reference must not strip the
    verbatim message — the message is the GM-facing UX that ADR-0019
    relies on for the misrouted-`/ingest` recovery path. The
    reference's "Hard-stop" shape explicitly delegates the verbatim
    phrasing back to the consuming SKILL.md.
    """

    HARD_STOP_MESSAGE = (
        "This directory isn't a scaffolded campaign repo. "
        "Run `/init-campaign` to start a new campaign, "
        "or invoke `/ingest` from a campaign that's already scaffolded."
    )

    def test_ingest_skill_still_has_verbatim_message(
        self, repo_root: Path
    ) -> None:
        text = (
            repo_root / "skills" / "ingest" / "SKILL.md"
        ).read_text(encoding="utf-8")
        assert self.HARD_STOP_MESSAGE in text, (
            "`skills/ingest/SKILL.md` no longer contains the verbatim "
            "hard-stop message. Lifting the marker check to "
            "`campaign-locate.md` must preserve the skill-specific "
            "phrasing — the reference owns the routing shape; the "
            "SKILL.md owns the message text."
        )
