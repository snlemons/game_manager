"""Fixture-based tests for /ingest Phase 3 per-doc commits (issue #61).

These tests assert the external behavior the skill spec (under
`skills/ingest/SKILL.md` Phase 3 Step 5.8 and the refined-cancel branch
of Step 4b) promises:

  (a) Commit message format. Each per-doc commit's subject matches the
      `/ingest doc <N>/<total>: <doc-name> (<summary>)` form documented
      in Step 5.8.
  (b) Commit cadence. A K-doc Phase 3 run produces 1 scaffold commit
      + K per-doc commits + 1 wrap-up commit = K + 2 total. The
      wrap-up commit's subject matches the narrowed `/ingest wrap-up
      (...)` form documented in Phase 4 Step 3b.
  (c) Reset-to-before-doc-K behavior. From a 3-doc run, `git reset
      --hard <doc-K-minus-1-sha>` (recovered by `git log --grep
      '^/ingest doc '`) leaves HEAD at the doc-(K-1) commit and drops
      every file authored by docs >= K. The carried-forward lessons
      drop mirrors that: only lessons whose source-doc index >= K are
      removed.
  (d) Recovery pre-flight. A campaign in the "N per-doc commits, no
      wrap-up" state is detectable via `git log --grep '^/ingest doc '`
      and the absence of a subsequent wrap-up commit; the spec routes
      that state through the resume prompt in Phase 3 Step 0c.
  (e) Spec conformance. SKILL.md documents the per-doc commit message
      format, the three-choice cancel prompt, the Step 0c recovery
      pre-flight, and the narrowed wrap-up commit message. ADR-0011's
      issue-#61 amendment paragraph acknowledges the per-doc cadence
      asymmetry between /ingest and /prep-session / /wrap-session.

What is **not** tested here is the LLM agent's compliance with the
prompt. The skill is implemented as a prompt; without a headless-LLM
harness in CI, an integration-level test of agent compliance is
impractical. The tests below exercise the *specification* the skill
encodes, using a reference Python implementation of the per-doc commit
loop the same way `tests/test_ingest_scaffolding.py` encodes Phase 1
Steps 1–3 and `tests/test_wrap_session_idempotency.py` encodes
`/wrap-session`'s session-dir staging scope.

That gap is documented in `tests/README.md`.
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Hermetic git runner (mirrors `tests/test_ingest_scaffolding.py::_run_git`).
# ---------------------------------------------------------------------------


def _run_git(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run a git command with a hermetic identity for committer + author.

    The plugin itself never configures `user.name` / `user.email`
    (SKILL.md Phase 1 Step 3). This test is *not* the plugin — it has
    to make commits reproducibly in any environment, including CI.
    Identity is injected through env vars only for this subprocess,
    leaving the user's global git config untouched, and both global +
    system config files are pointed at `/dev/null` so a host-specific
    `init.defaultBranch` or signing setting can't surprise the assertions.
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


# ---------------------------------------------------------------------------
# Reference implementation of the Step 5.8 per-doc commit + Phase 4 wrap-up
# ---------------------------------------------------------------------------


# The lifecycle/reference folders Phase 3 may write into. The per-doc
# commit's staging scope is restricted to these (per SKILL.md Step 5.8's
# scoped-add rule).
LIFECYCLE_FOLDERS: tuple[str, ...] = (
    "npcs",
    "pcs",
    "locations",
    "factions",
    "items",
    "adventures",
    "threads",
    "consequences",
    "beats",
    "secrets",
)


# Subject-line shape for a per-doc commit. The regex below is the
# executable form of SKILL.md Step 5.8's commit-message contract:
#
#   /ingest doc <N>/<total>: <doc-name> (<summary>)
#
# - `<N>` is a positive integer (1-based position in the processing order).
# - `<total>` is a positive integer (count of docs surviving survey ordering).
# - `<doc-name>` is the doc's basename (anything up to the colon-summary
#   boundary, including periods and dots so `.md` reads correctly).
# - `<summary>` is a free-form one-line parenthetical summary.
PER_DOC_COMMIT_SUBJECT_RE = re.compile(
    r"^/ingest doc (\d+)/(\d+): (\S.+?) \((.+)\)$"
)

# Subject-line shape for the Phase 4 wrap-up commit, post-issue-#61.
WRAP_UP_COMMIT_SUBJECT_RE = re.compile(
    r"^/ingest wrap-up \((.+)\)$"
)


@dataclass
class Lesson:
    """A single carried-forward lesson from Step 5b.

    The Step 5b lessons set carries forward GM corrections (rejections,
    classification preferences, dedup decisions, etc.) so doc N+1's
    extraction reflects what the GM corrected on doc N. The relevant
    structural property for issue #61 is that each lesson knows its
    source-doc index — that's what makes the reset-to-before-doc-K
    drop predictable.
    """

    source_doc_index: int  # 1-based
    text: str


@dataclass
class IngestRunState:
    """The in-memory state the agent carries through a Phase 3 run.

    Modeled as a plain dataclass so the reference implementation below
    can mutate it the way the LLM does conceptually (apply lessons,
    drop lessons on reset, etc.) without dragging in spec-internal
    intermediate types.
    """

    lessons: list[Lesson] = field(default_factory=list)

    def drop_lessons_from_doc_onwards(self, k: int) -> None:
        """Drop every lesson with source_doc_index >= k.

        This is the carried-forward-lessons-drop the spec mandates for
        the reset-to-before-doc-K cancel path. Lessons from docs 1..K-1
        survived the reset (their underlying work is still in the tree
        as commits); lessons from docs K..N go away with their commits.
        """
        self.lessons = [l for l in self.lessons if l.source_doc_index < k]

    def drop_all_lessons(self) -> None:
        """Drop every lesson. Used by the abandon-entirely cancel path."""
        self.lessons.clear()


def commit_doc(
    *,
    campaign: Path,
    doc_index: int,
    doc_total: int,
    doc_name: str,
    summary: str,
    paths_written: list[str],
) -> str:
    """Reference implementation of SKILL.md Phase 3 Step 5.8.

    Stages exactly `paths_written` (the doc's tree writes — explicit
    paths, never `git add -A`), then commits with the documented
    subject shape. Returns the commit SHA.

    `paths_written` must contain at least one entry; the spec's
    empty-scope guard ("if the GM rejected every proposed file for
    this doc, skip the commit entirely") is the caller's job and
    represented by NOT calling this function — same as the LLM would
    skip the commit step.
    """
    if not paths_written:
        raise ValueError(
            "Step 5.8 says: skip the commit when nothing was written. "
            "Don't call commit_doc with an empty path set."
        )
    # Stage scoped paths only — the executable form of Step 5.8's
    # "explicit paths, never -A" rule.
    _run_git("add", "--", *paths_written, cwd=campaign)
    subject = (
        f"/ingest doc {doc_index}/{doc_total}: {doc_name} ({summary})"
    )
    _run_git("commit", "-m", subject, cwd=campaign)
    out = _run_git("rev-parse", "HEAD", cwd=campaign).stdout.strip()
    return out


def commit_wrap_up(
    *,
    campaign: Path,
    summary: str,
    paths_written: list[str],
) -> str:
    """Reference implementation of SKILL.md Phase 4 Step 3c.

    Post-issue-#61 the wrap-up commit's scope is narrow: just
    `campaign.md` plus any Adventure files Step 1 touched. Returns
    the commit SHA. Subject shape: `/ingest wrap-up (<summary>)`.
    """
    _run_git("add", "--", *paths_written, cwd=campaign)
    subject = f"/ingest wrap-up ({summary})"
    _run_git("commit", "-m", subject, cwd=campaign)
    return _run_git("rev-parse", "HEAD", cwd=campaign).stdout.strip()


def lookup_doc_commit_sha(campaign: Path, k: int) -> str | None:
    """Return the SHA of the K-th per-doc commit, or None if not present.

    The "Reset to before doc K" cancel branch needs the SHA of the
    commit *before* doc K landed — that is, the doc-(K-1) commit, or
    the Phase 1 scaffold commit if K == 1. The agent recovers this via
    `git log --grep '^/ingest doc '`; this helper is the executable
    form of that lookup.
    """
    result = _run_git(
        "log",
        "--grep=^/ingest doc ",
        "--reverse",
        "--format=%H %s",
        cwd=campaign,
    )
    for line in result.stdout.splitlines():
        sha, _, subject = line.partition(" ")
        m = PER_DOC_COMMIT_SUBJECT_RE.match(subject)
        if not m:
            continue
        if int(m.group(1)) == k:
            return sha
    return None


def lookup_scaffold_sha(campaign: Path) -> str:
    """Return the SHA of the Phase 1 scaffold commit.

    Phase 1 Step 3 pins the subject as `Scaffold campaign repo via
    ttrpg-gm /ingest`. The "Abandon entirely" cancel branch resets
    HEAD here.
    """
    result = _run_git(
        "log",
        "--grep=^Scaffold campaign repo via ttrpg-gm /ingest$",
        "--format=%H",
        cwd=campaign,
    )
    sha = result.stdout.strip().splitlines()
    assert len(sha) == 1, (
        "expected exactly one scaffold commit; found "
        f"{len(sha)}: {sha}"
    )
    return sha[0]


def per_doc_commit_count(campaign: Path) -> int:
    """How many `/ingest doc ...` commits are in HEAD's history?

    The "resume after cancel/crash" pre-flight (Phase 3 Step 0c) uses
    this count to surface the resume-or-abandon prompt.
    """
    result = _run_git(
        "log", "--grep=^/ingest doc ", "--format=%H", cwd=campaign
    )
    return len([l for l in result.stdout.splitlines() if l.strip()])


def wrap_up_commit_exists(campaign: Path) -> bool:
    """Has a Phase 4 wrap-up commit landed after the per-doc commits?

    Phase 3 Step 0c's detection logic distinguishes the "crashed
    mid-Phase-3" state (per-doc commits present, no subsequent
    wrap-up) from the "completed cleanly" state (per-doc commits +
    wrap-up).
    """
    result = _run_git(
        "log", "--grep=^/ingest wrap-up", "--format=%H", cwd=campaign
    )
    return any(l.strip() for l in result.stdout.splitlines())


def reset_hard(campaign: Path, sha: str) -> None:
    """Run `git reset --hard <sha>`. Mirrors the spec's reset paths.

    The Step 4b cancel branch's "Reset to before doc K" and "Abandon
    entirely" both run this command — the only difference is the
    target SHA (doc-(K-1) commit vs. Phase 1 scaffold commit).
    """
    _run_git("reset", "--hard", sha, cwd=campaign)


# ---------------------------------------------------------------------------
# Fixture: a freshly scaffolded campaign repo (reuses the helper from
# test_ingest_scaffolding.py via a direct import-by-path).
# ---------------------------------------------------------------------------


@pytest.fixture
def scaffolded_campaign(
    tmp_path: Path,
    templates_dir: Path,
) -> Path:
    """A fresh campaign repo scaffolded into a temp directory.

    Re-uses the reference Phase 1 scaffolder from
    `tests/test_ingest_scaffolding.py` so this test file doesn't
    duplicate the placeholder-substitution + git-init logic. Named
    `Per-Doc Commit Test Campaign` / system `D&D 5e` so the
    substituted content reads naturally if a maintainer drops into
    the tmp directory to debug.
    """
    # Local import — avoids a circular fixture chain by deferring the
    # import until the fixture actually runs. Pytest discovers test
    # files as top-level modules (no `tests` package), so the import
    # is by file basename, not via a `tests.` package prefix.
    from test_ingest_scaffolding import scaffold_campaign

    target = tmp_path / "campaign-under-test"
    scaffold_campaign(
        templates_dir=templates_dir,
        target=target,
        campaign_name="Per-Doc Commit Test Campaign",
        campaign_system="D&D 5e",
    )
    return target


def _write_lifecycle_file(
    campaign: Path, relpath: str, content: str = "# stub\n"
) -> str:
    """Create `<campaign>/<relpath>` with `content`, returning relpath.

    Helper for the multi-doc commit scenarios — each test doc writes a
    couple of lifecycle files to simulate what its Phase 3 extraction
    would have produced.
    """
    full = campaign / relpath
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(content)
    return relpath


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.fixture
def ingest_skill_path(repo_root: Path) -> Path:
    """Absolute path to the /ingest SKILL.md prompt."""
    return repo_root / "skills" / "ingest" / "SKILL.md"


class TestPerDocCommitMessageFormat:
    """The Step 5.8 commit message subject conforms to the documented shape."""

    def test_message_matches_documented_shape(
        self, scaffolded_campaign: Path
    ) -> None:
        """A representative per-doc commit's subject parses against the
        shape `/ingest doc <N>/<total>: <doc-name> (<summary>)`."""
        campaign = scaffolded_campaign
        paths = [
            _write_lifecycle_file(
                campaign, "npcs/sera.md", "# Sera\n\nThe blacksmith.\n"
            ),
            _write_lifecycle_file(
                campaign, "npcs/maren.md", "# Maren\n\nThe innkeeper.\n"
            ),
        ]
        commit_doc(
            campaign=campaign,
            doc_index=1,
            doc_total=3,
            doc_name="lost-mines.md",
            summary="Adventure, 2 NPCs",
            paths_written=paths,
        )
        subject = _run_git(
            "log", "-1", "--format=%s", cwd=campaign
        ).stdout.strip()
        m = PER_DOC_COMMIT_SUBJECT_RE.match(subject)
        assert m is not None, (
            f"per-doc commit subject {subject!r} does not match the "
            "documented `/ingest doc <N>/<total>: <doc-name> "
            "(<summary>)` shape"
        )
        assert int(m.group(1)) == 1
        assert int(m.group(2)) == 3
        assert m.group(3) == "lost-mines.md"
        assert m.group(4) == "Adventure, 2 NPCs"

    @pytest.mark.parametrize(
        "doc_index,doc_total,doc_name,summary",
        [
            (1, 12, "faerun-gods.md", "5 Reference notes, 2 Secrets"),
            (
                2,
                12,
                "lost-mines.md",
                "Adventure, 12 Reference notes, 4 Beats",
            ),
            (
                12,
                12,
                "session-1-notes.md",
                "3 Threads, 2 Consequences",
            ),
            # Single-doc degenerate case (doc 1 of 1).
            (1, 1, "only-doc.md", "1 Reference note"),
        ],
    )
    def test_subject_round_trips_for_documented_examples(
        self,
        scaffolded_campaign: Path,
        doc_index: int,
        doc_total: int,
        doc_name: str,
        summary: str,
    ) -> None:
        """Each example subject from SKILL.md Step 5.8 round-trips
        through the regex and the commit machinery without loss."""
        campaign = scaffolded_campaign
        paths = [
            _write_lifecycle_file(
                campaign,
                f"npcs/example-{doc_index}.md",
                f"# Example {doc_index}\n",
            )
        ]
        commit_doc(
            campaign=campaign,
            doc_index=doc_index,
            doc_total=doc_total,
            doc_name=doc_name,
            summary=summary,
            paths_written=paths,
        )
        subject = _run_git(
            "log", "-1", "--format=%s", cwd=campaign
        ).stdout.strip()
        m = PER_DOC_COMMIT_SUBJECT_RE.match(subject)
        assert m is not None, f"subject {subject!r} did not parse"
        assert (
            int(m.group(1)),
            int(m.group(2)),
            m.group(3),
            m.group(4),
        ) == (doc_index, doc_total, doc_name, summary)


class TestThreeDocCommitCadence:
    """A 3-doc Phase 3 run produces 1 scaffold + 3 per-doc + 1 wrap-up = 5."""

    @pytest.fixture
    def three_doc_completed_campaign(
        self, scaffolded_campaign: Path
    ) -> Path:
        """Simulate a clean 3-doc Phase 3 + Phase 4 run end-to-end."""
        campaign = scaffolded_campaign
        # Doc 1: world-info, two NPCs.
        commit_doc(
            campaign=campaign,
            doc_index=1,
            doc_total=3,
            doc_name="faerun-gods.md",
            summary="5 Reference notes, 2 Secrets",
            paths_written=[
                _write_lifecycle_file(campaign, "npcs/tymora.md"),
                _write_lifecycle_file(campaign, "npcs/lathander.md"),
            ],
        )
        # Doc 2: adventure with NPCs + threads.
        commit_doc(
            campaign=campaign,
            doc_index=2,
            doc_total=3,
            doc_name="lost-mines.md",
            summary="Adventure, 12 Reference notes, 4 Beats",
            paths_written=[
                _write_lifecycle_file(
                    campaign, "adventures/lost-mines/adventure.md"
                ),
                _write_lifecycle_file(campaign, "npcs/sera.md"),
                _write_lifecycle_file(
                    campaign, "threads/find-rulf.md"
                ),
            ],
        )
        # Doc 3: session log with threads + consequences.
        commit_doc(
            campaign=campaign,
            doc_index=3,
            doc_total=3,
            doc_name="session-1-notes.md",
            summary="3 Threads, 2 Consequences",
            paths_written=[
                _write_lifecycle_file(
                    campaign, "threads/deliver-letter.md"
                ),
                _write_lifecycle_file(
                    campaign,
                    "consequences/temple-was-purged.md",
                ),
            ],
        )
        # Phase 4 wrap-up: regen campaign.md + backfill one Adventure order:.
        (campaign / "campaign.md").write_text(
            "# Per-Doc Commit Test Campaign\n\n(regenerated)\n"
        )
        commit_wrap_up(
            campaign=campaign,
            summary=(
                "campaign.md regen, 1 Adventure backfilled with order: 1"
            ),
            paths_written=["campaign.md"],
        )
        return campaign

    def test_total_commit_count_is_five(
        self, three_doc_completed_campaign: Path
    ) -> None:
        """Phase 1 (1) + Phase 3 (3 per-doc) + Phase 4 (1 wrap-up) = 5."""
        count = int(
            _run_git(
                "rev-list",
                "--count",
                "HEAD",
                cwd=three_doc_completed_campaign,
            ).stdout.strip()
        )
        assert count == 5, (
            f"expected 5 commits (1 scaffold + 3 per-doc + 1 wrap-up); "
            f"got {count}"
        )

    def test_commit_subjects_match_expected_chain(
        self, three_doc_completed_campaign: Path
    ) -> None:
        """The five subjects, in chronological order, are the documented chain."""
        # `--reverse` orders oldest first, matching the documented
        # narrative order in SKILL.md Step 5.8's example.
        result = _run_git(
            "log",
            "--reverse",
            "--format=%s",
            cwd=three_doc_completed_campaign,
        )
        subjects = result.stdout.strip().splitlines()
        assert (
            subjects[0]
            == "Scaffold campaign repo via ttrpg-gm /ingest"
        ), f"first commit subject is wrong: {subjects[0]!r}"
        for i, doc_name in enumerate(
            ["faerun-gods.md", "lost-mines.md", "session-1-notes.md"],
            start=1,
        ):
            m = PER_DOC_COMMIT_SUBJECT_RE.match(subjects[i])
            assert m is not None, (
                f"commit {i+1} subject {subjects[i]!r} doesn't parse as "
                "a per-doc commit"
            )
            assert int(m.group(1)) == i and int(m.group(2)) == 3
            assert m.group(3) == doc_name
        wrap = WRAP_UP_COMMIT_SUBJECT_RE.match(subjects[4])
        assert wrap is not None, (
            f"wrap-up commit subject {subjects[4]!r} doesn't parse"
        )

    def test_per_doc_commit_only_contains_that_docs_writes(
        self, three_doc_completed_campaign: Path
    ) -> None:
        """Each per-doc commit's diff contains only the paths that doc wrote.

        Scoped-add discipline: doc 2's commit must not accidentally
        include doc 1's NPC files or doc 3's threads. This is the
        executable form of Step 5.8's "stage only the paths this doc
        wrote" rule.
        """
        # Look up the doc-2 commit and diff against its parent.
        doc2_sha = lookup_doc_commit_sha(three_doc_completed_campaign, 2)
        assert doc2_sha is not None
        diff = _run_git(
            "diff",
            "--name-only",
            f"{doc2_sha}~1",
            doc2_sha,
            cwd=three_doc_completed_campaign,
        )
        files = set(diff.stdout.strip().splitlines())
        assert files == {
            "adventures/lost-mines/adventure.md",
            "npcs/sera.md",
            "threads/find-rulf.md",
        }, (
            f"doc-2 commit's diff scope leaked or missed paths: {files}"
        )


class TestResetToBeforeDocK:
    """Cancel-with-reset rolls HEAD back and drops the right lessons."""

    @pytest.fixture
    def three_doc_with_lessons(
        self, scaffolded_campaign: Path
    ) -> tuple[Path, IngestRunState]:
        """Mid-run state: 3 per-doc commits landed, lessons accumulated."""
        campaign = scaffolded_campaign
        state = IngestRunState()
        # Doc 1 produces a lesson the GM corrected at review.
        commit_doc(
            campaign=campaign,
            doc_index=1,
            doc_total=3,
            doc_name="faerun-gods.md",
            summary="2 NPCs",
            paths_written=[
                _write_lifecycle_file(campaign, "npcs/tymora.md"),
                _write_lifecycle_file(campaign, "npcs/lathander.md"),
            ],
        )
        state.lessons.append(
            Lesson(
                source_doc_index=1,
                text="do not propose passing innkeepers as Reference notes",
            )
        )
        # Doc 2 produces two lessons.
        commit_doc(
            campaign=campaign,
            doc_index=2,
            doc_total=3,
            doc_name="lost-mines.md",
            summary="Adventure, 1 NPC, 1 Thread",
            paths_written=[
                _write_lifecycle_file(
                    campaign, "adventures/lost-mines/adventure.md"
                ),
                _write_lifecycle_file(campaign, "npcs/sera.md"),
                _write_lifecycle_file(
                    campaign, "threads/find-rulf.md"
                ),
            ],
        )
        state.lessons.append(
            Lesson(
                source_doc_index=2,
                text="GM treats one-line rumors as narrative color, not Threads",
            )
        )
        state.lessons.append(
            Lesson(
                source_doc_index=2,
                text="Sera in this run is npcs/sera.md",
            )
        )
        # Doc 3 produces one lesson.
        commit_doc(
            campaign=campaign,
            doc_index=3,
            doc_total=3,
            doc_name="session-1-notes.md",
            summary="1 Thread, 1 Consequence",
            paths_written=[
                _write_lifecycle_file(
                    campaign, "threads/deliver-letter.md"
                ),
                _write_lifecycle_file(
                    campaign, "consequences/temple-purged.md"
                ),
            ],
        )
        state.lessons.append(
            Lesson(
                source_doc_index=3,
                text="render the captain's seal mention as a wiki link",
            )
        )
        return campaign, state

    def test_reset_to_before_doc_2_drops_docs_2_and_3(
        self,
        three_doc_with_lessons: tuple[Path, IngestRunState],
    ) -> None:
        """Reset-to-before-doc-2 rolls HEAD back to doc-1's commit and
        leaves only doc-1's files on disk."""
        campaign, state = three_doc_with_lessons

        # Look up the doc-1 commit (which is the predecessor of doc-2).
        doc_1_sha = lookup_doc_commit_sha(campaign, 1)
        assert doc_1_sha is not None
        reset_hard(campaign, doc_1_sha)
        state.drop_lessons_from_doc_onwards(2)

        # HEAD is now at doc-1's commit.
        head = _run_git(
            "rev-parse", "HEAD", cwd=campaign
        ).stdout.strip()
        assert head == doc_1_sha, (
            f"HEAD did not move to doc-1's commit; HEAD={head}, "
            f"expected={doc_1_sha}"
        )

        # Doc-1's files are present.
        assert (campaign / "npcs/tymora.md").is_file()
        # Doc-2's and doc-3's files are gone (working tree was reset --hard).
        assert not (
            campaign / "adventures/lost-mines/adventure.md"
        ).exists()
        assert not (campaign / "npcs/sera.md").exists()
        assert not (campaign / "threads/find-rulf.md").exists()
        assert not (campaign / "threads/deliver-letter.md").exists()
        assert not (
            campaign / "consequences/temple-purged.md"
        ).exists()

        # The lessons drop is index-based: only doc-1's lesson remains.
        assert len(state.lessons) == 1
        assert state.lessons[0].source_doc_index == 1
        assert "innkeepers" in state.lessons[0].text

    def test_reset_to_before_doc_1_lands_at_scaffold_commit(
        self,
        three_doc_with_lessons: tuple[Path, IngestRunState],
    ) -> None:
        """K=1 case: reset to before doc 1 lands at the Phase 1 scaffold
        commit (the predecessor of doc 1). All lessons drop."""
        campaign, state = three_doc_with_lessons

        scaffold_sha = lookup_scaffold_sha(campaign)
        # `lookup_doc_commit_sha(..., k)` returns the K-th doc's commit;
        # the predecessor lookup for K=1 is the scaffold commit.
        reset_hard(campaign, scaffold_sha)
        state.drop_lessons_from_doc_onwards(1)

        head = _run_git(
            "rev-parse", "HEAD", cwd=campaign
        ).stdout.strip()
        assert head == scaffold_sha

        # No lifecycle files survive — tree is back to scaffolder output.
        for f in (
            "npcs/tymora.md",
            "npcs/lathander.md",
            "adventures/lost-mines/adventure.md",
            "npcs/sera.md",
            "threads/find-rulf.md",
            "threads/deliver-letter.md",
            "consequences/temple-purged.md",
        ):
            assert not (campaign / f).exists(), (
                f"{f} should have been rolled back by the abandon "
                "reset, but it's still on disk"
            )

        # All lessons dropped.
        assert state.lessons == []

    def test_abandon_entirely_resets_to_scaffold(
        self,
        three_doc_with_lessons: tuple[Path, IngestRunState],
    ) -> None:
        """The abandon-entirely cancel branch resets HEAD to the Phase 1
        scaffold commit (subject `Scaffold campaign repo via ttrpg-gm
        /ingest`) and drops *all* carried-forward lessons regardless of
        source-doc index."""
        campaign, state = three_doc_with_lessons

        scaffold_sha = lookup_scaffold_sha(campaign)
        reset_hard(campaign, scaffold_sha)
        state.drop_all_lessons()

        head = _run_git(
            "rev-parse", "HEAD", cwd=campaign
        ).stdout.strip()
        assert head == scaffold_sha
        assert state.lessons == []
        # Commit count is exactly the one scaffold commit.
        count = int(
            _run_git(
                "rev-list", "--count", "HEAD", cwd=campaign
            ).stdout.strip()
        )
        assert count == 1


class TestRecoveryPreflight:
    """Step 0c detects per-doc commits without a wrap-up and offers resume."""

    def test_fresh_scaffold_has_no_per_doc_commits(
        self, scaffolded_campaign: Path
    ) -> None:
        """A scaffold-only campaign has zero per-doc commits — Phase 3
        Step 0c proceeds straight to doc 1 without prompting."""
        assert per_doc_commit_count(scaffolded_campaign) == 0
        assert not wrap_up_commit_exists(scaffolded_campaign)

    def test_partial_run_is_detectable_as_resumable(
        self, scaffolded_campaign: Path
    ) -> None:
        """Per-doc commits without a wrap-up is the "crashed mid-Phase-3 /
        keep-all cancel" state Step 0c surfaces via the resume prompt."""
        campaign = scaffolded_campaign
        commit_doc(
            campaign=campaign,
            doc_index=1,
            doc_total=5,
            doc_name="doc-a.md",
            summary="1 NPC",
            paths_written=[_write_lifecycle_file(campaign, "npcs/a.md")],
        )
        commit_doc(
            campaign=campaign,
            doc_index=2,
            doc_total=5,
            doc_name="doc-b.md",
            summary="1 NPC",
            paths_written=[_write_lifecycle_file(campaign, "npcs/b.md")],
        )
        # State: 2 per-doc commits, no wrap-up.
        assert per_doc_commit_count(campaign) == 2
        assert not wrap_up_commit_exists(campaign)
        # The next invocation's Step 0c prompt is "resume at doc 3 of 5,
        # or abandon and re-scaffold?" The detection signal is exactly
        # the (per_doc_commit_count > 0, wrap_up_commit_exists == False)
        # pair this test pins down.

    def test_completed_run_is_not_resumable(
        self, scaffolded_campaign: Path
    ) -> None:
        """Per-doc commits *plus* a subsequent wrap-up is the "completed
        cleanly" state — Step 0c does not surface a resume prompt."""
        campaign = scaffolded_campaign
        commit_doc(
            campaign=campaign,
            doc_index=1,
            doc_total=1,
            doc_name="only.md",
            summary="1 NPC",
            paths_written=[
                _write_lifecycle_file(campaign, "npcs/only.md")
            ],
        )
        (campaign / "campaign.md").write_text(
            "# Per-Doc Commit Test Campaign\n\n(regenerated)\n"
        )
        commit_wrap_up(
            campaign=campaign,
            summary="campaign.md regen",
            paths_written=["campaign.md"],
        )
        assert per_doc_commit_count(campaign) == 1
        assert wrap_up_commit_exists(campaign)
        # Step 0c proceeds to doc 1 of *this* run without prompting.


class TestSpecConformance:
    """SKILL.md and ADR-0011 document the spec the LLM follows."""

    def test_skill_documents_per_doc_commit_message_format(
        self, ingest_skill_path: Path
    ) -> None:
        """SKILL.md Step 5.8 must show the per-doc commit message shape."""
        spec = ingest_skill_path.read_text()
        # Subject template (the load-bearing phrase the LLM will follow).
        assert (
            "/ingest doc <N>/<total>: <doc-name> "
            "(<one-line summary of what was extracted>)"
        ) in spec, (
            "SKILL.md Phase 3 Step 5.8 does not show the documented "
            "per-doc commit subject template"
        )
        # The motivating examples (5 Reference notes / 2 Secrets, etc.).
        assert (
            "/ingest doc 1/12: faerun-gods.md "
            "(5 Reference notes, 2 Secrets)" in spec
        )
        assert (
            "/ingest doc 2/12: lost-mines.md "
            "(Adventure, 12 Reference notes, 4 Beats)" in spec
        )

    def test_skill_documents_scoped_staging_rule(
        self, ingest_skill_path: Path
    ) -> None:
        """Step 5.8 must document scoped staging (never `-A`-sweep)."""
        spec = ingest_skill_path.read_text()
        assert "never sweep in unrelated GM edits" in spec, (
            "SKILL.md Step 5.8 doesn't document the scoped-staging rule "
            "from ADR-0011"
        )
        # Mention all the lifecycle/reference folder names so the LLM
        # has an authoritative enumeration.
        for folder in (
            "npcs/",
            "locations/",
            "secrets/",
            "beats/",
            "adventures/",
        ):
            assert folder in spec, (
                f"SKILL.md Step 5.8 doesn't enumerate the {folder} "
                "lifecycle folder"
            )

    def test_skill_documents_three_choice_cancel_prompt(
        self, ingest_skill_path: Path
    ) -> None:
        """The refined cancel-mid-Phase-3 prompt must surface all three
        responses verbatim — keep all / reset to before doc K / abandon
        entirely. Without these in the prompt, the LLM has no shape to
        offer the GM."""
        spec = ingest_skill_path.read_text()
        # Verbatim phrases from the issue-#61 refined-cancel design.
        assert "Keep all" in spec
        assert "Reset to before doc" in spec
        assert "Abandon entirely" in spec
        # The mechanism: git reset --hard.
        assert "git reset --hard" in spec
        # The lessons-drop rule for the reset path.
        assert (
            "Drop every carried-forward lesson whose source-doc index is ≥ K"
            in spec
            or "drop carried-forward lessons accumulated by docs ≥ K"
            in spec
            or "drop carried-forward lessons accumulated by docs >= K"
            in spec
        ), "SKILL.md doesn't document the lessons-drop on reset"

    def test_skill_documents_recovery_preflight(
        self, ingest_skill_path: Path
    ) -> None:
        """Phase 3 Step 0c detects per-doc-committed state and offers resume."""
        spec = ingest_skill_path.read_text()
        assert "Step 0c" in spec, (
            "SKILL.md does not include the Phase 3 Step 0c recovery "
            "pre-flight section header"
        )
        # The detection mechanism the spec uses.
        assert "git log --grep '^/ingest doc '" in spec
        # The resume / abandon-and-rescaffold prompt shape.
        assert "Resume at doc N+1" in spec or "Resume" in spec

    def test_skill_documents_narrowed_wrap_up_commit_message(
        self, ingest_skill_path: Path
    ) -> None:
        """Phase 4 Step 3b must document the narrowed wrap-up commit
        message (no longer summarizing everything since the scaffold —
        the per-doc commits carry that)."""
        spec = ingest_skill_path.read_text()
        # The exemplar message from the updated spec.
        assert (
            "/ingest wrap-up (campaign.md regen, 3 Adventures "
            "backfilled with order: 1/2/3)"
        ) in spec, (
            "SKILL.md Phase 4 Step 3b doesn't show the narrowed wrap-up "
            "commit message example"
        )
        # The subject-line shape.
        assert "/ingest wrap-up (<short summary>)" in spec

    def test_adr_0011_amendment_covers_ingest_per_doc_asymmetry(
        self, repo_root: Path
    ) -> None:
        """ADR-0011 must acknowledge the per-doc cadence asymmetry between
        /ingest and /prep-session / /wrap-session so SKILL.md and the
        ADR don't drift on the "one skill invocation = one commit" rule.
        """
        adr = (
            repo_root / "docs" / "adr" / "0011-wrap-session-workflow.md"
        ).read_text()
        # The motivating issue number.
        assert "issue #61" in adr or "#61" in adr, (
            "ADR-0011 amendment does not cite issue #61 as the "
            "motivation for the per-doc cadence"
        )
        # The asymmetry framing.
        assert "/ingest" in adr and (
            "/prep-session" in adr and "/wrap-session" in adr
        ), (
            "ADR-0011 amendment does not contrast /ingest's per-doc "
            "cadence with /prep-session and /wrap-session's single-commit "
            "cadence"
        )
        # The "multi-doc, unbounded" reasoning.
        assert "multi-doc" in adr, (
            "ADR-0011 amendment does not surface the multi-doc workflow "
            "rationale for the asymmetry"
        )
