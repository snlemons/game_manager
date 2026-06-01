"""Fixture-based idempotency tests for /wrap-session (issue #9).

These tests assert the external behavior the skill's specification (under
`skills/wrap-session/SKILL.md` and `docs/adr/0011-wrap-session-workflow.md`)
promises:

  (a) No duplicates on re-run: re-running against the same `notes.md` does
      not create new Thread / Consequence / Beat / Reference-note files when
      a name-matching file already exists.
  (b) Confirm-before-overwrite of an existing `log.md`: the workflow's
      staging-then-cancel path leaves the existing `log.md` byte-identical.
  (c) Deterministic `campaign.md` regeneration: composing `campaign.md`
      from identical campaign state twice produces byte-identical content.

Each test copies the fixture under `tests/fixtures/wrap_session_idempotency/`
into a fresh temp dir, renaming `dot_claude/` -> `.claude/` on copy (the
fixture stores its `.claude/` content under that escaped name so the test
harness can write it without tripping plugin-internal path sandboxing).

What is **not** tested here is the LLM agent's compliance with the spec.
The skill is implemented as a prompt; without a headless-LLM harness in CI
(an end-to-end `claude --print` driver with canned approval responses for
the multiple GM prompts the workflow surfaces), an integration-level test
of agent compliance is impractical. The tests below exercise the
**specification** the skill encodes:

  * the dedup normalization rule from SKILL.md Step 2 "Dedup",
  * the staging-then-cancel invariant from SKILL.md Step 4,
  * the campaign.md regeneration ordering from SKILL.md Step 5 #7 and
    ADR-0007.

That gap is documented in `tests/README.md` and the PR for issue #9.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def materialize_fixture(src: Path, dest: Path) -> Path:
    """Copy the static fixture into `dest`, renaming `dot_claude/` -> `.claude/`.

    The fixture stores its `.claude/` subtree under `dot_claude/` so the
    test source tree can hold it without colliding with the plugin's own
    `.claude/` permissions. On copy we materialize the real layout a
    campaign repo expects.
    """
    shutil.copytree(src, dest)
    dot_claude = dest / "dot_claude"
    if dot_claude.exists():
        dot_claude.rename(dest / ".claude")
    return dest


# ---------------------------------------------------------------------------
# Spec-derived helpers
# ---------------------------------------------------------------------------

# Dedup normalization, lifted from SKILL.md Step 2 "Dedup":
#   "Name match: case-insensitive, light normalization (strip leading 'the',
#    collapse whitespace, hyphenate)."
_THE_PREFIX = re.compile(r"^the[\s\-_]+", re.IGNORECASE)
_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def normalize_name(name: str) -> str:
    """Mirror the dedup normalization rule documented in SKILL.md Step 2.

    Per the spec: case-insensitive, strip leading 'the', collapse whitespace,
    hyphenate. We also strip the `.md` suffix so candidate names and existing
    filenames normalize to the same form.
    """
    n = name.strip().lower()
    if n.endswith(".md"):
        n = n[: -len(".md")]
    n = _THE_PREFIX.sub("", n)
    n = _NON_ALNUM.sub("-", n).strip("-")
    return n


def first_heading_title(path: Path) -> str | None:
    """Return the text of the first `# ` heading in a markdown file, if any.

    The dedup spec matches a candidate name against both the existing
    filename and 'the first-heading title inside each file'. We replicate
    that — the LLM, given the same spec, has to do the same match.
    """
    in_frontmatter = False
    saw_frontmatter_open = False
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if stripped == "---":
            if not saw_frontmatter_open:
                in_frontmatter = True
                saw_frontmatter_open = True
                continue
            if in_frontmatter:
                in_frontmatter = False
                continue
        if in_frontmatter:
            continue
        if stripped.startswith("# "):
            return stripped[2:].strip()
    return None


def existing_names_for_kind(campaign: Path, kind: str) -> set[str]:
    """All normalized names for an existing lifecycle/reference kind.

    Spec: match candidate against filename **and** first-heading title.
    Returns the union so a candidate matching either is treated as a dup.
    """
    d = campaign / kind
    if not d.is_dir():
        return set()
    names: set[str] = set()
    for p in d.iterdir():
        if not p.is_file() or not p.name.endswith(".md"):
            continue
        names.add(normalize_name(p.name))
        title = first_heading_title(p)
        if title:
            names.add(normalize_name(title))
    return names


def would_dedup(candidate_name: str, existing: set[str]) -> bool:
    """True if a proposed new item with `candidate_name` would collide
    with an existing item under the SKILL.md Step 2 dedup rule."""
    return normalize_name(candidate_name) in existing


# ---------------------------------------------------------------------------
# Reference composer mirroring SKILL.md Step 5 #7 + ADR-0007 section order
# ---------------------------------------------------------------------------


def parse_frontmatter(path: Path) -> tuple[dict[str, str], str]:
    """Tiny frontmatter parser: returns ({key: raw_value}, body_after_fm).

    Values are kept as raw strings (no YAML coercion) — sufficient for the
    fields the composer uses (`status`, `created`, `closed`, dates).
    """
    text = path.read_text()
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}, text
    fm_block = text[4:end]
    body = text[end + len("\n---\n") :]
    fm: dict[str, str] = {}
    for line in fm_block.splitlines():
        if ":" not in line:
            continue
        k, _, v = line.partition(":")
        fm[k.strip()] = v.strip()
    return fm, body


def compose_campaign_md(campaign: Path, campaign_name: str, system: str) -> str:
    """Reference `campaign.md` composer.

    Deterministically derives the file from current campaign state per
    SKILL.md Step 5 #7 + ADR-0007 (as updated for issue #13's open-world
    support):
      * Header: campaign name, system
      * Where the party might go next session:
          - Active arcs sub-bucket (omitted entirely if no `status: active`
            Adventures)
          - Introduced Adventures the party could pick up
          - Recent open Threads that could become a session focus
          - Party location line
      * Open threads: every Thread with `status: open`, most-recent first
      * Recent significant consequences: Consequences by `created:` desc,
        top 5
      * Pending beats: every Beat with `status: pending`, one line each

    The "Where the party might go next session" section replaces the older
    "Active adventures" + "Party location" framing, handling zero/one/many
    active Adventures equally (issue #13).

    This is the executable specification of 'deterministic regeneration' —
    given the same campaign state, the function must return byte-identical
    output across calls.

    Note: the composer's curated "session-driver Threads" filter is judgment
    the LLM applies; the deterministic reference here lists all open Threads
    under that sub-bucket. The determinism property doesn't depend on the
    filter, only on the function being a deterministic mapping of inputs to
    output.
    """

    def latest_log_party_location() -> str:
        sessions_dir = campaign / "sessions"
        if not sessions_dir.is_dir():
            return "Party location not stated in this session's Log."
        session_dirs = sorted(
            (d for d in sessions_dir.iterdir() if d.is_dir()),
            key=lambda d: d.name,
            reverse=True,
        )
        for d in session_dirs:
            log = d / "log.md"
            if log.is_file():
                # Spec doesn't constrain extraction — we fall through to the
                # honest 'unclear' string. Real composer (the LLM) does
                # more here, but the determinism property doesn't depend on
                # what's extracted, only on it being a deterministic function
                # of the inputs.
                return "Party location not stated in this session's Log."
        return "Party location not stated in this session's Log."

    lines: list[str] = []
    lines.append(f"# {campaign_name} — Campaign Overview")
    lines.append("")
    lines.append(
        "*This file is agent-maintained. It snapshots the campaign's current "
        "state in glance-readable form and is rewritten by `/wrap-session` "
        "and `/ingest`. Manual edits will be reconciled (or overwritten with "
        "warning) at the next regeneration. For editorial campaign notes "
        "(themes, pitch, house rules), use a separate file the agent doesn't "
        "touch.*"
    )
    lines.append("")
    lines.append(f"- **Campaign:** {campaign_name}")
    lines.append(f"- **System:** {system}")
    lines.append("")

    # Where the party might go next session
    lines.append("## Where the party might go next session")
    lines.append("")
    adv_dir = campaign / "adventures"
    active: list[tuple[str, str]] = []
    introduced: list[tuple[str, str, str]] = []  # (order_key, slug, title)
    if adv_dir.is_dir():
        for slug in sorted(d.name for d in adv_dir.iterdir() if d.is_dir()):
            adv_md = adv_dir / slug / "adventure.md"
            if not adv_md.is_file():
                continue
            fm, _ = parse_frontmatter(adv_md)
            status = fm.get("status")
            title = first_heading_title(adv_md) or slug
            if status == "active":
                active.append((slug, title))
            elif status == "introduced":
                # Sort numeric `order:` ascending, then null-order alpha by slug.
                raw_order = fm.get("order", "")
                # Numbered orders sort before unset; use a tuple key.
                if raw_order and raw_order != "~":
                    try:
                        order_key = (0, int(raw_order))
                    except ValueError:
                        order_key = (1, 0)
                else:
                    order_key = (1, 0)
                introduced.append((order_key, slug, title))

    # Active arcs sub-bucket — omit entirely if no active Adventures.
    if active:
        lines.append("**Active arcs — could continue any of these:**")
        lines.append("")
        for _, title in active:
            lines.append(f"- **{title}**")
        lines.append("")

    # Introduced Adventures the party could pick up.
    lines.append("**Introduced Adventures the party could pick up:**")
    lines.append("")
    if introduced:
        introduced.sort(key=lambda t: (t[0], t[1]))
        for _, _, title in introduced:
            lines.append(f"- **{title}**")
    else:
        lines.append("_None._")
    lines.append("")

    # Session-driver Threads sub-bucket. The deterministic reference renders
    # all open Threads here; the LLM applies session-driver curation.
    lines.append("**Recent open Threads that could become a session focus:**")
    lines.append("")
    thr_dir = campaign / "threads"
    open_threads: list[tuple[str, str, str]] = []
    if thr_dir.is_dir():
        for p in sorted(thr_dir.iterdir(), key=lambda x: x.name):
            if not p.is_file() or not p.name.endswith(".md"):
                continue
            fm, _ = parse_frontmatter(p)
            if fm.get("status") == "open":
                title = first_heading_title(p) or p.stem
                created = fm.get("created", "")
                open_threads.append((created, p.stem, title))
    open_threads.sort(key=lambda t: (t[0], t[1]), reverse=True)
    if open_threads:
        for _, _, title in open_threads:
            lines.append(f"- **{title}**")
    else:
        lines.append("_None._")
    lines.append("")

    # Party location line at the end of the menu.
    lines.append(f"**Party location:** {latest_log_party_location()}")
    lines.append("")

    # Open threads (full list)
    lines.append("## Open threads")
    lines.append("")
    if open_threads:
        for _, _, title in open_threads:
            lines.append(f"- **{title}**")
    else:
        lines.append("*None.*")
    lines.append("")

    # Recent significant consequences: by created desc, top 5
    lines.append("## Recent significant consequences")
    lines.append("")
    cons_dir = campaign / "consequences"
    cons: list[tuple[str, str, str]] = []
    if cons_dir.is_dir():
        for p in sorted(cons_dir.iterdir(), key=lambda x: x.name):
            if not p.is_file() or not p.name.endswith(".md"):
                continue
            fm, _ = parse_frontmatter(p)
            title = first_heading_title(p) or p.stem
            cons.append((fm.get("created", ""), p.stem, title))
    cons.sort(key=lambda t: (t[0], t[1]), reverse=True)
    if cons:
        for _, _, title in cons[:5]:
            lines.append(f"- {title}")
    else:
        lines.append("*None.*")
    lines.append("")

    # Pending beats
    lines.append("## Pending beats")
    lines.append("")
    beats_dir = campaign / "beats"
    pending: list[tuple[str, str]] = []
    if beats_dir.is_dir():
        for p in sorted(beats_dir.iterdir(), key=lambda x: x.name):
            if not p.is_file() or not p.name.endswith(".md"):
                continue
            fm, _ = parse_frontmatter(p)
            if fm.get("status") == "pending":
                title = first_heading_title(p) or p.stem
                pending.append((p.stem, title))
    if pending:
        for _, title in pending:
            lines.append(f"- **{title}**")
    else:
        lines.append("*None.*")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fixture_src(fixtures_dir: Path) -> Path:
    """Absolute path to the wrap-session idempotency fixture source tree."""
    return fixtures_dir / "wrap_session_idempotency"


@pytest.fixture
def wrap_skill_path(repo_root: Path) -> Path:
    """Absolute path to the wrap-session SKILL.md prompt."""
    return repo_root / "skills" / "wrap-session" / "SKILL.md"


@pytest.fixture
def campaign(tmp_path: Path, fixture_src: Path) -> Path:
    """A freshly materialized copy of the wrap-session fixture campaign.

    Lives under `tmp_path`; `dot_claude/` is renamed to `.claude/` on copy
    so the materialized tree matches what a real campaign repo looks like.
    """
    return materialize_fixture(fixture_src, tmp_path / "campaign")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestFixtureSanityChecks:
    """The fixture itself must look like a real post-ingest campaign repo
    so the rest of the suite is testing a representative state."""

    def test_fixture_has_required_campaign_repo_markers(
        self, campaign: Path
    ) -> None:
        for marker in (
            "CLAUDE.md",
            "campaign.md",
            ".claude/rules/sessions.md",
            ".claude/rules/adventures.md",
        ):
            assert (campaign / marker).is_file(), (
                f"fixture is missing campaign-repo marker: {marker}"
            )

    def test_fixture_has_session_with_notes_and_no_log(
        self, campaign: Path
    ) -> None:
        target = campaign / "sessions" / "2026-05-29-session-5"
        assert (target / "notes.md").is_file()
        assert not (target / "log.md").exists(), (
            "the target session should have no log.md before wrap"
        )
        assert (target / "notes.md").stat().st_size > 0, (
            "fixture's notes.md should be non-empty"
        )

    def test_fixture_has_prior_session_with_log(self, campaign: Path) -> None:
        prior = campaign / "sessions" / "2026-05-20-session-4"
        assert (prior / "log.md").is_file()


class TestDedupOnRerun:
    """Acceptance criterion (a): no duplicates on re-run.

    Re-running `/wrap-session` against the same `notes.md` after corrections
    must not create new files for items the spec's dedup rule should
    collapse against existing files. We test the dedup rule itself against
    the fixture's existing lifecycle objects — the LLM, given the same
    spec, has to apply the same normalization.
    """

    def test_existing_thread_name_match_collapses(self, campaign: Path) -> None:
        # threads/deliver-the-letter.md exists with the heading "Deliver the letter".
        # Any of these phrasings the LLM might emit as a new Thread on re-run
        # must collide with the existing one and not create a new file.
        existing = existing_names_for_kind(campaign, "threads")
        for candidate in (
            "Deliver the letter",
            "deliver the letter",
            "Deliver The Letter",
            "Deliver  the   letter",
            "the deliver-the-letter",  # slug-like
            "deliver-the-letter",
            "Deliver-the-letter.md",
        ):
            assert would_dedup(candidate, existing), (
                f"candidate Thread name {candidate!r} should dedup against "
                f"existing threads, but did not"
            )

    def test_existing_consequence_name_match_collapses(
        self, campaign: Path
    ) -> None:
        existing = existing_names_for_kind(campaign, "consequences")
        for candidate in (
            "Captain Marra owes the party a favor",
            "captain marra owes the party a favor",
            "captain-marra-owes-favor",
            "Captain Marra Owes Favor",
        ):
            assert would_dedup(candidate, existing), (
                f"candidate Consequence {candidate!r} should dedup against "
                f"existing consequences, but did not"
            )

    def test_existing_beat_name_match_collapses(self, campaign: Path) -> None:
        existing = existing_names_for_kind(campaign, "beats")
        for candidate in (
            "Orin's armor",
            "orin's armor",
            "orin-armor",
            "Orin armor",
        ):
            assert would_dedup(candidate, existing), (
                f"candidate Beat {candidate!r} should dedup against "
                f"existing beats, but did not"
            )

    def test_existing_reference_note_name_match_collapses(
        self, campaign: Path
    ) -> None:
        existing = existing_names_for_kind(campaign, "npcs")
        for candidate in ("Sera", "sera", "SERA"):
            assert would_dedup(candidate, existing), (
                f"candidate NPC {candidate!r} should dedup against "
                f"existing npcs, but did not"
            )

        locations = existing_names_for_kind(campaign, "locations")
        for candidate in (
            "The Broken Mines",
            "the broken mines",
            "Broken Mines",
            "the-broken-mines",
        ):
            assert would_dedup(candidate, locations), (
                f"candidate location {candidate!r} should dedup against "
                f"existing locations, but did not"
            )

    def test_genuinely_new_names_do_not_dedup(self, campaign: Path) -> None:
        """A genuinely new item (from session 5's notes) must NOT dedup —
        otherwise the rule would suppress real new content."""
        existing_threads = existing_names_for_kind(campaign, "threads")
        existing_npcs = existing_names_for_kind(campaign, "npcs")
        existing_locations = existing_names_for_kind(campaign, "locations")
        for new_name, existing in (
            # From session 5's notes — none of these exist in the fixture yet.
            ("Doric", existing_npcs),
            ("Deliver word to Doric's sister", existing_threads),
            ("The Mouth", existing_npcs),
            ("Cult of the Broken Flame", existing_threads),
            ("Level Three Stairway", existing_locations),
        ):
            assert not would_dedup(new_name, existing), (
                f"new item {new_name!r} should NOT dedup against existing, "
                f"but did — the rule is over-collapsing"
            )

    def test_rerun_dedup_against_fixture_produces_zero_dups(
        self, campaign: Path
    ) -> None:
        """Integration-style: simulate a 'second run' where the LLM proposes
        the same set of *existing* items by name. After applying the dedup
        rule, the count of items the runtime would actually create is zero.
        """
        proposed_threads = ["Deliver the letter"]
        proposed_consequences = ["Captain Marra owes the party a favor"]
        proposed_beats = ["Orin's armor"]
        proposed_npcs = ["Sera", "Captain Marra"]
        proposed_locations = ["The Broken Mines"]

        for kind, proposals in (
            ("threads", proposed_threads),
            ("consequences", proposed_consequences),
            ("beats", proposed_beats),
            ("npcs", proposed_npcs),
            ("locations", proposed_locations),
        ):
            existing = existing_names_for_kind(campaign, kind)
            would_create = [
                p for p in proposals if not would_dedup(p, existing)
            ]
            assert would_create == [], (
                f"on re-run, the dedup rule should suppress every "
                f"already-existing {kind} candidate; instead it would "
                f"create new files for: {would_create}"
            )


class TestConfirmBeforeOverwriteLog:
    """Acceptance criterion (b): confirm-before-overwrite of existing log.md.

    Two assertions:
    1. The skill's normative spec documents the gate (so the agent has it
       in its prompt). This is a spec-conformance assertion.
    2. The staging-then-cancel workflow path leaves the existing log.md
       byte-identical — this is the behavior the gate is the affordance for.
    """

    ORIGINAL_LOG = (
        "# Session 5 Log — 2026-05-29\n"
        "\n"
        "GM-edited log. The wrap workflow MUST NOT silently overwrite "
        "this.\n"
    )

    @pytest.fixture
    def campaign_with_existing_log(self, campaign: Path) -> Path:
        """Plant a pre-existing log.md in session 5 so the re-run guard is
        the path under test. The content represents a GM-hand-edited log
        we must not silently overwrite."""
        target_session = campaign / "sessions" / "2026-05-29-session-5"
        log_path = target_session / "log.md"
        log_path.write_text(self.ORIGINAL_LOG)
        return campaign

    def test_skill_spec_contains_rerun_guard(
        self, wrap_skill_path: Path
    ) -> None:
        """The skill's prompt must document the confirm-before-overwrite
        gate — without that text, the LLM has no rule to follow."""
        spec = wrap_skill_path.read_text()
        # Section header and explicit STOP / overwrite-confirmation language.
        assert "Re-run guard (confirm-before-overwrite)" in spec
        assert "`log.md` exists" in spec
        assert "STOP" in spec
        assert "Overwrite the Log" in spec

    def test_staging_then_cancel_leaves_existing_log_unchanged(
        self, campaign_with_existing_log: Path
    ) -> None:
        """Simulate the workflow's Step 4 'cancel' path:
          - the agent stages a proposed new log under
            `.ttrpg-staging/wrap/sessions/.../log.md` (per Step 4 of the
            spec),
          - the GM says 'cancel' (or fails to approve),
          - the spec requires the staging dir to be deleted and **no files
            outside `.ttrpg-staging/`** to be modified.

        After this cycle, the existing log.md must be byte-identical.
        """
        campaign = campaign_with_existing_log
        log_path = (
            campaign / "sessions" / "2026-05-29-session-5" / "log.md"
        )
        original_bytes = log_path.read_bytes()

        staging = (
            campaign
            / ".ttrpg-staging"
            / "wrap"
            / "sessions"
            / "2026-05-29-session-5"
        )
        staging.mkdir(parents=True, exist_ok=True)
        proposed_log = staging / "log.md"
        proposed_log.write_text(
            "# Session 5 Log — 2026-05-29\n"
            "\n"
            "A proposed log the agent drafted but the GM rejected.\n"
        )
        # Also stage some proposed lifecycle objects to make the scenario
        # representative — these too must not leak out on cancel.
        cult_thread = campaign / ".ttrpg-staging" / "wrap" / "threads"
        cult_thread.mkdir(parents=True, exist_ok=True)
        (cult_thread / "cult-of-the-broken-flame.md").write_text(
            "---\nstatus: open\ncreated: 2026-05-29\nclosed: ~\n---\n\n"
            "# Cult of the Broken Flame\n\nProposed but not approved.\n"
        )

        # GM cancels: per spec, "delete `.ttrpg-staging/`, leave the rest of
        # the filesystem unchanged, exit cleanly."
        shutil.rmtree(campaign / ".ttrpg-staging")

        # The original log.md must be byte-identical.
        assert log_path.read_bytes() == original_bytes, (
            "existing log.md was modified during a staging-then-cancel cycle "
            "— the confirm-before-overwrite guarantee is broken"
        )
        # No leaked threads file either.
        assert not (
            campaign / "threads" / "cult-of-the-broken-flame.md"
        ).exists(), (
            "proposed but unapproved Thread leaked into the final tree"
        )
        # The staging dir must be gone.
        assert not (campaign / ".ttrpg-staging").exists(), (
            "staging directory not cleaned up on cancel"
        )

    def test_staging_dir_is_gitignored_per_scaffolder(
        self, campaign_with_existing_log: Path
    ) -> None:
        """`.ttrpg-staging/` must be gitignored at the campaign root so a
        cancelled wrap leaves no trace in git status (per ingest scaffolder
        and `templates/.gitignore.template`)."""
        gi = (campaign_with_existing_log / ".gitignore").read_text()
        assert ".ttrpg-staging/" in gi


class TestCampaignMdRegenerationIsDeterministic:
    """Acceptance criterion (c): deterministic `campaign.md` regeneration.

    The spec (SKILL.md Step 5 #7, ADR-0007) requires `campaign.md` to be
    a pure function of current campaign state — section order is fixed,
    field semantics are fixed. We exercise that with a reference composer:
    given identical state, two runs must produce byte-identical content.

    The composer is the executable specification. If the LLM diverges from
    this composer's output, the divergence is the LLM's drift from the
    spec, not a determinism failure in the spec itself.
    """

    def test_identical_state_produces_identical_output(
        self, campaign: Path
    ) -> None:
        first = compose_campaign_md(campaign, "Test Campaign", "D&D 5e")
        second = compose_campaign_md(campaign, "Test Campaign", "D&D 5e")
        assert first == second, (
            "campaign.md regeneration is not deterministic — same state, "
            "different output"
        )

    def test_output_contains_required_sections_in_spec_order(
        self, campaign: Path
    ) -> None:
        """Section order is fixed by SKILL.md Step 5 #7 (updated for #13)."""
        out = compose_campaign_md(campaign, "Test Campaign", "D&D 5e")
        # All required top-level sections present:
        required_sections = [
            "## Where the party might go next session",
            "## Open threads",
            "## Recent significant consequences",
            "## Pending beats",
        ]
        for section in required_sections:
            assert section in out, f"missing required section: {section}"
        # And in the prescribed order:
        positions = [out.index(s) for s in required_sections]
        assert positions == sorted(positions), (
            f"required sections are not in spec order: positions={positions}"
        )
        # The menu's party-location line is a sub-element (one line in the
        # menu), not its own H2 section.
        assert "**Party location:**" in out, (
            "party location line missing from menu"
        )

    def test_output_reflects_only_current_state(self, campaign: Path) -> None:
        """Mutating campaign state changes the regenerated output;
        mutating only ignored fields does not. This is the property that
        makes the regeneration *meaningful*, not just stable."""
        baseline = compose_campaign_md(campaign, "Test Campaign", "D&D 5e")
        # Close the only open Thread; output must change.
        thread = campaign / "threads" / "deliver-the-letter.md"
        text = thread.read_text()
        text = text.replace("status: open", "status: closed")
        thread.write_text(text)
        after = compose_campaign_md(campaign, "Test Campaign", "D&D 5e")
        assert baseline != after, (
            "closing a Thread did not change the regenerated campaign.md — "
            "the composer is not actually reading state"
        )

    def test_output_is_stable_across_filesystem_order(
        self, campaign: Path
    ) -> None:
        """The composer must impose a deterministic ordering rather than
        relying on filesystem enumeration order. Re-running after adding
        and removing a sibling file should not perturb section ordering of
        unrelated items."""
        baseline = compose_campaign_md(campaign, "Test Campaign", "D&D 5e")
        # Touch a file (changing mtime/inode order without changing content
        # the composer reads).
        extra = campaign / "threads" / "z-unrelated-stub.md"
        extra.write_text(
            "---\nstatus: closed\ncreated: 2026-04-01\nclosed: 2026-04-02\n---\n\n"
            "# Z unrelated stub\n\nClosed long ago.\n"
        )
        with_extra = compose_campaign_md(campaign, "Test Campaign", "D&D 5e")
        extra.unlink()
        after_remove = compose_campaign_md(
            campaign, "Test Campaign", "D&D 5e"
        )
        # Adding a *closed* Thread should not affect Open threads or any
        # other section: with_extra should equal baseline (closed threads
        # are excluded from the rendered list).
        assert baseline == with_extra, (
            "adding a closed Thread perturbed campaign.md — the composer "
            "is leaking non-active state into the rendered output"
        )
        # Removing it again returns to the baseline byte-for-byte.
        assert baseline == after_remove, (
            "campaign.md regeneration is not stable across add+remove of "
            "an unrelated closed Thread"
        )


# ---------------------------------------------------------------------------
# Helpers + reference implementation for the wrap-commit staging set (issue #71)
# ---------------------------------------------------------------------------


def _run_git(
    *args: str, cwd: Path
) -> subprocess.CompletedProcess[str]:
    """Run a git command with a hermetic identity for committer + author.

    Mirrors `tests/test_ingest_scaffolding.py::_run_git`. Identity is
    injected via env vars only for this subprocess so the user's global
    git config is untouched, and both the system and global config files
    are pointed at `/dev/null` so a host-specific `init.defaultBranch`
    or other setting can't surprise the assertions below.
    """
    env = os.environ.copy()
    env.update(
        {
            "GIT_AUTHOR_NAME": "ttrpg-gm tests",
            "GIT_AUTHOR_EMAIL": "tests@example.invalid",
            "GIT_COMMITTER_NAME": "ttrpg-gm tests",
            "GIT_COMMITTER_EMAIL": "tests@example.invalid",
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_SYSTEM": "/dev/null",
        }
    )
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )


def staging_set_for_session_dir(
    campaign: Path, session_rel: str
) -> set[str]:
    """Reference implementation of SKILL.md Step 5 #10's session-dir scope.

    The spec (post-issue-#71): "Run `git status sessions/YYYY-MM-DD-session-N/`
    and stage every entry the command surfaces, regardless of git's status
    code (`M` modified, `??` untracked, `A` added)."

    Returns the set of repo-relative file paths inside `session_rel` that
    have any uncommitted state. The LLM, given the same spec, has to compute
    the same set; this function is the executable specification of that scope.

    Implementation notes:

    * Uses `--untracked-files=all` so that when an entire directory is
      untracked (the retroactively-created-session case), git lists each
      file individually rather than collapsing to the parent directory.
      Either form leads the agent to stage the contents (`git add <dir>`
      is recursive), but the file-level set is the meaningful comparison
      target for the tests.
    * `--porcelain=v1 -z`: the `v1` format is stable, and `-z` uses NUL
      separators so paths with whitespace or unusual characters round-trip
      cleanly. Each record's first two bytes are the status code (e.g.
      `?? `, ` M `, `M  `, `A  `), followed by a space, followed by the
      path.
    """
    result = subprocess.run(
        [
            "git",
            "status",
            "--porcelain=v1",
            "-z",
            "--untracked-files=all",
            "--",
            session_rel,
        ],
        cwd=campaign,
        check=True,
        capture_output=True,
        text=False,
    )
    out: set[str] = set()
    if not result.stdout:
        return out
    # Records are NUL-separated. Renames have an extra NUL-separated source
    # path; the wrap spec doesn't expect renames inside the session dir but
    # we tolerate them by reading only the destination path.
    records = result.stdout.split(b"\x00")
    i = 0
    while i < len(records):
        rec = records[i]
        if not rec:
            i += 1
            continue
        # First three bytes are 'XY ' (status + space); path follows.
        if len(rec) < 4:
            i += 1
            continue
        xy = rec[:2].decode("ascii", errors="replace")
        path = rec[3:].decode("utf-8", errors="replace")
        out.add(path)
        # Skip the source path for renames/copies.
        if xy[0] in ("R", "C"):
            i += 2
        else:
            i += 1
    return out


# ---------------------------------------------------------------------------
# Session-directory commit scope (issue #71)
# ---------------------------------------------------------------------------


class TestSessionDirectoryWrapCommitScope:
    """Acceptance criterion for issue #71: the wrap commit checkpoints the
    target session directory as a coherent unit.

    Per ADR-0005, a session is a directory of three documents
    (`brief.md`, `notes.md`, `log.md`) all preserved indefinitely. Per the
    issue-#71 amendment to SKILL.md Step 5 #10 and ADR-0011, the wrap
    commit's staging scope includes any entry inside the target session
    directory with uncommitted state — *regardless* of git's status code
    (`M` modified, `??` untracked, `A` added). This covers two real
    failure modes the strict-spec agent on Sofia's second machine hit:

      1. GM hand-edits `brief.md` mid-session (scratchpad ticks, beats
         marked landed, carry-forward intent). After `/prep-session`
         committed it, the working-tree modification was orphaned.
      2. `/prep-session` committed an empty `notes.md`; the GM filled it
         in during play. The modification was orphaned.
      3. (Variant) the session was created retroactively without
         `/prep-session`, so `notes.md` is untracked, not modified. The
         strict "modified-files only" reading would miss it.

    The tests below pin the staging-set reference (`staging_set_for_session_dir`)
    against these three configurations and assert it captures every
    uncommitted session-dir entry.
    """

    SESSION_REL = "sessions/2026-05-29-session-5"

    @pytest.fixture
    def campaign_with_prep_session_committed(
        self, campaign: Path
    ) -> Path:
        """Materialize the fixture and run `git init` + commit `brief.md`
        and an empty `notes.md` so the campaign is in the post-`/prep-session`
        state for session 5: brief tracked + committed, notes tracked +
        committed (empty), no log yet.

        The fixture's session 5 already ships with a non-empty `notes.md`
        (it's what TestDedupOnRerun exercises). For the mid-session-edit
        scenario we restore the post-`/prep-session` state by truncating
        `notes.md` to empty before the initial commit, then planting the
        GM's in-play content as a working-tree modification.
        """
        _run_git("init", "-b", "main", cwd=campaign)
        # Restore the post-/prep-session state: notes.md exists but empty.
        notes = campaign / self.SESSION_REL / "notes.md"
        notes_backup = notes.read_text()
        notes.write_text("")
        _run_git("add", "-A", cwd=campaign)
        _run_git("commit", "-m", "prep session 5", cwd=campaign)
        # Stash the GM's in-play content on the fixture object so the test
        # can replay it as a "GM authored notes during the session" edit.
        (campaign / ".test-notes-stash").write_text(notes_backup)
        return campaign

    def _replay_in_play_notes(self, campaign: Path) -> None:
        """Replay the fixture's session-5 notes content into `notes.md` as
        a working-tree modification — the in-play authoring case."""
        stash = campaign / ".test-notes-stash"
        (campaign / self.SESSION_REL / "notes.md").write_text(
            stash.read_text()
        )
        stash.unlink()

    def test_mid_session_brief_edit_and_in_play_notes_are_staged(
        self, campaign_with_prep_session_committed: Path
    ) -> None:
        """The headline case from the issue: GM hand-edits `brief.md`
        during the session AND fills in `notes.md`. Both are
        tracked-and-modified before the wrap. The wrap also writes a new
        `log.md`. The staging set must include all three."""
        campaign = campaign_with_prep_session_committed

        # GM mid-session edit to brief.md (scratchpad tick, carry-forward).
        brief = campaign / self.SESSION_REL / "brief.md"
        brief.write_text(
            brief.read_text()
            + "\n- [x] Goblin ambush landed.\n"
            + "- Carry forward: remind me the captive miner is a rumor source.\n"
        )
        # GM in-play notes (the empty notes.md becomes the real content).
        self._replay_in_play_notes(campaign)
        # Wrap writes log.md.
        log = campaign / self.SESSION_REL / "log.md"
        log.write_text(
            "# Session 5 Log — 2026-05-29\n\nThe party entered the mines.\n"
        )

        staged = staging_set_for_session_dir(campaign, self.SESSION_REL)

        assert f"{self.SESSION_REL}/brief.md" in staged, (
            "mid-session brief.md edit was NOT in the wrap staging set — "
            "the GM's carry-forward intent will be orphaned"
        )
        assert f"{self.SESSION_REL}/notes.md" in staged, (
            "in-play notes.md authoring was NOT in the wrap staging set — "
            "the source-of-truth notes will be orphaned"
        )
        assert f"{self.SESSION_REL}/log.md" in staged, (
            "newly-written log.md was NOT in the wrap staging set"
        )

    def test_staging_set_actually_commits_the_three_documents(
        self, campaign_with_prep_session_committed: Path
    ) -> None:
        """Integration-style: simulate the full wrap-commit step by
        running `git add` over the computed staging set, committing, and
        asserting the resulting commit's tree includes all three files
        with the modified/added content. This is what the LLM would do
        after computing the staging set."""
        campaign = campaign_with_prep_session_committed

        brief = campaign / self.SESSION_REL / "brief.md"
        brief.write_text(brief.read_text() + "\n- [x] Goblin ambush landed.\n")
        self._replay_in_play_notes(campaign)
        log = campaign / self.SESSION_REL / "log.md"
        log.write_text("# Session 5 Log — 2026-05-29\n\nThe party descended.\n")

        staged = staging_set_for_session_dir(campaign, self.SESSION_REL)
        # The reference algorithm yields a non-empty set covering all three.
        for path in staged:
            _run_git("add", "--", path, cwd=campaign)
        _run_git("commit", "-m", "Wrap session 5 (2026-05-29)", cwd=campaign)

        # After commit, the working tree should be clean for the session dir.
        post = staging_set_for_session_dir(campaign, self.SESSION_REL)
        assert post == set(), (
            f"after wrap commit, session dir still has uncommitted entries: "
            f"{post}"
        )

        # And the commit's tree must contain the three files with current
        # working-tree content (no orphans).
        for fname in ("brief.md", "notes.md", "log.md"):
            result = _run_git(
                "show",
                f"HEAD:{self.SESSION_REL}/{fname}",
                cwd=campaign,
            )
            on_disk = (campaign / self.SESSION_REL / fname).read_text()
            assert result.stdout == on_disk, (
                f"committed {fname} content diverges from working tree — "
                f"the wrap commit did not capture the session as a "
                f"coherent unit"
            )
        # Specific content checks: the mid-session brief edit landed, and
        # the in-play notes content landed (not the empty placeholder).
        committed_brief = _run_git(
            "show", f"HEAD:{self.SESSION_REL}/brief.md", cwd=campaign
        ).stdout
        assert "Goblin ambush landed" in committed_brief
        committed_notes = _run_git(
            "show", f"HEAD:{self.SESSION_REL}/notes.md", cwd=campaign
        ).stdout
        assert committed_notes.strip(), (
            "committed notes.md is empty — the in-play authoring did not "
            "land in the wrap commit"
        )

    def test_retroactive_session_with_untracked_notes_is_staged(
        self, campaign: Path
    ) -> None:
        """Variant case: the session was created retroactively — without
        `/prep-session` running — so `notes.md` is untracked rather than
        tracked-and-modified. The staging set must still capture it (the
        spec mandates "every entry the command surfaces, regardless of git
        status code"; `??` counts).

        We construct this by `git init`-ing the campaign WITHOUT staging
        the session-5 directory at all. From git's POV, every file in the
        session dir is `??` untracked."""
        # Initialize a repo containing only campaign-root content; the
        # session-5 directory exists on disk but is untracked.
        _run_git("init", "-b", "main", cwd=campaign)
        # Stage everything *except* the target session dir so a baseline
        # commit exists and the session dir's files are the only `??`
        # entries inside its path.
        for entry in sorted(campaign.iterdir()):
            if entry.name == ".git":
                continue
            if entry.name == "sessions":
                # Stage prior sessions but not the target session.
                for sess in sorted(entry.iterdir()):
                    if sess.name == "2026-05-29-session-5":
                        continue
                    _run_git(
                        "add", "--", f"sessions/{sess.name}", cwd=campaign
                    )
                continue
            _run_git("add", "--", entry.name, cwd=campaign)
        _run_git("commit", "-m", "baseline", cwd=campaign)

        # The wrap writes log.md as well.
        log = campaign / self.SESSION_REL / "log.md"
        log.write_text(
            "# Session 5 Log — 2026-05-29\n\nRetroactive wrap.\n"
        )

        staged = staging_set_for_session_dir(campaign, self.SESSION_REL)
        # All three session-dir entries must be picked up, untracked
        # or otherwise. The fixture's notes.md is non-empty, brief.md
        # was authored by the (skipped) prep, log.md was just written.
        for fname in ("brief.md", "notes.md", "log.md"):
            assert f"{self.SESSION_REL}/{fname}" in staged, (
                f"retroactive session: untracked {fname} was NOT in the "
                f"wrap staging set — the 'every entry regardless of "
                f"status code' rule is not being honored"
            )

    def test_spec_documents_session_dir_staging_rule(
        self, wrap_skill_path: Path
    ) -> None:
        """Spec-conformance: SKILL.md Step 5 #10 must document the rule
        that drives the staging set. Without that text in the prompt, the
        LLM has nothing to apply."""
        spec = wrap_skill_path.read_text()
        # The amendment's load-bearing phrase: status codes covered,
        # session-directory scope, ADR-0005 framing.
        assert "git status sessions/" in spec, (
            "SKILL.md does not instruct the agent to use `git status` "
            "over the session directory"
        )
        assert "regardless of git's status code" in spec or (
            "regardless of whether `git` reports it as modified" in spec
        ), "SKILL.md does not cover both modified and untracked entries"
        # The "unrelated GM edits" guardrail must explicitly carve out
        # the session-dir files.
        assert "carve-out" in spec or "carve out" in spec, (
            "SKILL.md guardrail does not document the session-dir "
            "carve-out from the 'unrelated GM edits' rule"
        )

    def test_adr_0011_amendment_covers_session_dir_scope(
        self, repo_root: Path
    ) -> None:
        """ADR-0011's amendment paragraph must explicitly include the
        session-dir files in the wrap commit's scope so SKILL.md and the
        ADR don't drift."""
        adr = (
            repo_root / "docs" / "adr" / "0011-wrap-session-workflow.md"
        ).read_text()
        assert "brief.md" in adr and "notes.md" in adr, (
            "ADR-0011 amendment does not mention brief.md / notes.md in "
            "the wrap commit's scope"
        )
        assert "ADR-0005" in adr, (
            "ADR-0011 amendment does not reference ADR-0005's "
            "'all three preserved indefinitely' framing as the rationale"
        )
