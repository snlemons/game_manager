"""Cross-test helpers for the ttrpg-gm plugin tests.

This module exists because the v0.1 convention "reference impls live
inline in `tests/test_*.py`" works fine when a reference impl is used
by exactly one test file but breaks the moment a second test file
needs the same machinery — pytest discovers `test_*.py` files as
top-level modules, so a `from test_other_file import foo` line
silently couples two test files together. Renaming or removing the
source file then breaks unrelated tests' imports.

The convention this module widens to: **skill-specific reference impls
still live in `test_*.py`, but anything imported across test files
lives here (or as a fixture in `conftest.py`).** The leading underscore
on `_helpers.py` tells pytest "this is not a test file".

See `tests/README.md` for the full rationale and the per-helper
provenance notes.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Hermetic git runner — shared by the scaffolder reference and the per-doc
# commit reference. Both test files used to define an identical copy.
# ---------------------------------------------------------------------------


def _run_git(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run a git command with a hermetic identity for committer + author.

    The plugin itself never configures `user.name` / `user.email`
    (SKILL.md Phase 1 Step 3). The tests are *not* the plugin — they
    have to make commits reproducibly in any environment, including CI.
    Identity is injected through env vars only for this subprocess,
    leaving the user's global git config untouched, and both global +
    system config files are pointed at `/dev/null` so a host-specific
    `init.defaultBranch` or signing setting can't surprise the
    assertions.
    """
    env = os.environ.copy()
    env.update(
        {
            "GIT_AUTHOR_NAME": "ttrpg-gm tests",
            "GIT_AUTHOR_EMAIL": "tests@example.invalid",
            "GIT_COMMITTER_NAME": "ttrpg-gm tests",
            "GIT_COMMITTER_EMAIL": "tests@example.invalid",
            # Pin the initial branch name so `git init` doesn't pick up
            # a host-specific `init.defaultBranch` setting and surprise
            # the assertions in the scaffolder tests.
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
# Scaffolder reference — encodes `references/scaffolder.md` Steps 1–3.
# Originally lived in `tests/test_ingest_scaffolding.py`; lifted here when
# `/init-campaign`, `/init-adventure`, and the per-doc commit tests started
# needing the same machinery (see ADR-0020).
# ---------------------------------------------------------------------------


# The seven templated paths the scaffolder is contracted to write into
# a campaign repo, in the **exact write order** specified by
# `references/scaffolder.md` Step 2. Source paths are under
# `templates/` (with `.template` suffix); destination paths are
# relative to the campaign repo root.
#
# `.claude/settings.json` is FIRST so its `permissions.allow` rules
# are in effect for the remaining six writes — the one-prompt
# property the scaffolder reference guarantees. Slice A (#81) pinned
# this ordering with `TestWriteOrder` in `test_ingest_scaffolding.py`.
#
# `.claude/rules/style.md` was added in issue #103 (slice K follow-up)
# per ADR-0021. The file is committed to version control even though
# it is GM-authored thereafter — the deny entries in
# `.claude/settings.json` block agent edits at the permission layer.
EXPECTED_SCAFFOLDED_FILES: list[tuple[str, str]] = [
    (".claude/settings.json.template", ".claude/settings.json"),
    ("CLAUDE.md.template", "CLAUDE.md"),
    (".claude/rules/sessions.md.template", ".claude/rules/sessions.md"),
    (".claude/rules/adventures.md.template", ".claude/rules/adventures.md"),
    (".claude/rules/style.md.template", ".claude/rules/style.md"),
    ("campaign.md.template", "campaign.md"),
    (".gitignore.template", ".gitignore"),
]

# The six paths actually staged into the initial commit. This is the
# scaffolded set minus `.claude/settings.json`, which is gitignored from
# the start because it carries machine-local absolute paths (see issue
# #62 and `skills/ingest/SKILL.md` Phase 1 Step 3). The file is still
# written to disk (it has to be — its permission rules are in effect
# for the rest of Phase 1) but excluded from `git add`.
EXPECTED_COMMITTED_FILES: list[str] = [
    dest for (_, dest) in EXPECTED_SCAFFOLDED_FILES
    if dest != ".claude/settings.json"
]


# Marker paths the scaffolder's Step 1 inspects to decide whether the
# target is already a campaign repo. Mirrors `references/scaffolder.md`
# Step 1.3 verbatim. The `.git` marker is special-cased — its presence
# alone is not enough (a git-init'd-but-otherwise-empty directory is
# fine); we count commits to decide.
EXISTING_CAMPAIGN_MARKERS: tuple[str, ...] = (
    "campaign.md",
    ".claude/rules/sessions.md",
    ".claude/rules/adventures.md",
)


class ScaffolderAlreadyScaffoldedError(RuntimeError):
    """Raised when the reference scaffolder detects existing campaign markers.

    Mirrors `references/scaffolder.md` Step 1's "stop if any marker is
    present" rule. The exception carries the list of markers found so
    callers (and the idempotency tests) can assert on which markers
    triggered the stop.
    """

    def __init__(self, markers: list[str]) -> None:
        super().__init__(
            "Target directory looks like an existing campaign repo "
            f"(found markers: {markers}); refusing to re-scaffold."
        )
        self.markers: list[str] = markers


def _substitute_placeholders(
    text: str,
    *,
    campaign_name: str,
    campaign_system: str,
    campaign_path: Path,
) -> str:
    """Apply the three documented placeholder substitutions verbatim.

    Per SKILL.md Phase 1 Step 2:

    - `{{CAMPAIGN_NAME}}` and `{{CAMPAIGN_SYSTEM}}` are the GM-supplied
      strings.
    - `{{CAMPAIGN_PATH}}` is the resolved absolute campaign path
      *without* a trailing slash. The template inserts a leading `/`
      in the matcher pattern, so the substituted value should not
      start with one — `str(Path)` already produces the bare form.

    Issue #69 dropped the `{{HOME}}` substitution: the plugin-install
    Read rule now uses `${CLAUDE_PLUGIN_ROOT}`, which Claude Code
    resolves at match time without an upfront text substitution.
    """
    return (
        text.replace("{{CAMPAIGN_NAME}}", campaign_name)
        .replace("{{CAMPAIGN_SYSTEM}}", campaign_system)
        .replace("{{CAMPAIGN_PATH}}", str(campaign_path))
    )


def _existing_campaign_markers(target: Path) -> list[str]:
    """Return the subset of campaign markers present at `target`.

    Used by the reference scaffolder's Step 1 guard and by the
    idempotency tests. Order of the returned list matches
    `EXISTING_CAMPAIGN_MARKERS`, plus a synthetic `".git/"` entry when
    a non-trivial git repo (one or more commits) is present.
    """
    found: list[str] = [
        marker for marker in EXISTING_CAMPAIGN_MARKERS
        if (target / marker).exists()
    ]
    git_dir = target / ".git"
    if git_dir.is_dir():
        # A `.git/` with any commits beyond the empty initial state is
        # a marker. `git rev-list --count HEAD` is the canonical check;
        # it returns non-zero on a fresh `git init` with no commits.
        try:
            result = subprocess.run(
                ["git", "rev-list", "--count", "HEAD"],
                cwd=target,
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode == 0 and int(result.stdout.strip() or "0") > 0:
                found.append(".git/")
        except (ValueError, FileNotFoundError):
            # Either the rev-list output didn't parse or git isn't on
            # the path. Conservative default: treat as no commits.
            pass
    return found


def scaffold_campaign(
    *,
    templates_dir: Path,
    target: Path,
    campaign_name: str,
    campaign_system: str,
    write_order_sink: list[str] | None = None,
) -> None:
    """Run the deterministic scaffolder against `target`.

    Mirrors `references/scaffolder.md` Steps 1–3:

    - Create the target if it doesn't exist (Step 1.2). If it exists
      and any of the markers in `EXISTING_CAMPAIGN_MARKERS` (plus a
      non-trivial `.git/`) is present, raise
      `ScaffolderAlreadyScaffoldedError` (Step 1.3 — "stop and tell
      the GM"). The test path turns the error surface into an
      assertable signal.
    - For each templated path, read the `.template` file, apply
      placeholder substitutions, and write to the destination path,
      stripping the `.template` suffix (Step 2). Intermediate
      directories are created on demand. Templates are written in the
      exact order documented in `references/scaffolder.md` Step 2,
      with `.claude/settings.json` first so its permission rules are
      in effect for the remaining six writes.
    - Run `git init`, stage the six committed written files
      explicitly (the gitignored `.claude/settings.json` is excluded),
      commit with the documented message (Step 3).

    The reference scaffolder skips Step 4's GM-facing report (it's
    LLM-/user-interaction surface, not deterministic behavior the test
    pins down).

    `write_order_sink`, when provided, is appended to with each
    destination path as it is written. Tests use this to assert the
    `.claude/settings.json`-first ordering rule from Step 2.
    """
    target = target.resolve()
    if target.exists():
        markers = _existing_campaign_markers(target)
        if markers:
            raise ScaffolderAlreadyScaffoldedError(markers)
    target.mkdir(parents=True, exist_ok=True)

    for template_rel, dest_rel in EXPECTED_SCAFFOLDED_FILES:
        src = templates_dir / template_rel
        dst = target / dest_rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        content = src.read_text(encoding="utf-8")
        substituted = _substitute_placeholders(
            content,
            campaign_name=campaign_name,
            campaign_system=campaign_system,
            campaign_path=target,
        )
        dst.write_text(substituted, encoding="utf-8")
        if write_order_sink is not None:
            write_order_sink.append(dest_rel)

    _run_git("init", "--initial-branch=main", cwd=target)
    # `.claude/settings.json` is intentionally absent from this argument
    # list — it's written to disk above (its permissions are in effect
    # for the rest of Phase 1) but gitignored by the `.gitignore` that
    # was also just written. See issue #62.
    #
    # `.claude/rules/style.md` was added in issue #103 (slice K
    # follow-up); per ADR-0021 the file is committed so the GM's voice
    # rides in version control. Agent edits against it are blocked at
    # the permissions layer by the deny entries in `.claude/settings.json`.
    _run_git(
        "add",
        "CLAUDE.md",
        ".claude/rules/sessions.md",
        ".claude/rules/adventures.md",
        ".claude/rules/style.md",
        "campaign.md",
        ".gitignore",
        cwd=target,
    )
    _run_git(
        "commit",
        "-m",
        "Scaffold campaign repo via ttrpg-gm /ingest",
        cwd=target,
    )


# ---------------------------------------------------------------------------
# Per-doc commit / wrap-up commit references — encodes `/ingest`'s Phase 3
# Step 5.8 and Phase 4 Step 3c. Originally lived in
# `tests/test_ingest_per_doc_commits.py`; lifted here when `/init-campaign`'s
# docs-mode test started needing the same `commit_doc` / `commit_wrap_up` /
# `per_doc_commit_count` / `wrap_up_commit_exists` machinery.
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Initial-Adventure file writer — encodes `/init-adventure`'s SKILL.md Step 2b
# output. Originally lived in `tests/test_init_adventure.py`; lifted here when
# `/init-campaign`'s first-Adventure sub-flow test started needing the same
# `write_initial_adventure_file` machinery.
# ---------------------------------------------------------------------------


def _slugify(name: str) -> str:
    """Slugify per `references/dedup-matching.md`'s normalization rule.

    Lowercase, strip leading "the ", collapse non-alphanumerics to single
    hyphens, trim leading/trailing hyphens. This is the minimal
    implementation the `/init-adventure` SKILL.md's Step 2a documents;
    the production skill follows the full reference.
    """
    s = name.strip().lower()
    if s.startswith("the "):
        s = s[4:]
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = s.strip("-")
    return s


def write_initial_adventure_file(
    *,
    campaign_root: Path,
    adventure_name: str,
    premise: Optional[str] = None,
) -> Path:
    """Write the initial Adventure file `/init-adventure` Step 2 produces.

    Mirrors the structural shape the walkthrough lands at after the
    Premise step approves: `adventures/<slug>/adventure.md` with the
    canonical Adventure frontmatter (`status: introduced`, `order: ~`,
    all dates `~`) and an H1 + optional premise body.

    The full walkthrough also produces Locations, NPCs, Threads,
    Secrets, and Beats; those are exercised by their own per-kind
    schema tests in `test_frontmatter.py`. This helper pins the
    minimum viable Adventure file — what `/init-adventure` writes for
    a GM who supplies a name and a premise and then approves.
    """
    slug = _slugify(adventure_name)
    adventure_dir = campaign_root / "adventures" / slug
    adventure_dir.mkdir(parents=True, exist_ok=True)
    adventure_path = adventure_dir / "adventure.md"

    frontmatter = (
        "---\n"
        "status: introduced\n"
        "order: ~\n"
        "introduced: ~\n"
        "started: ~\n"
        "completed: ~\n"
        "in_world_duration: ~\n"
        "real_world_duration: ~\n"
        "---\n"
    )
    body_lines = [f"# {adventure_name}", ""]
    if premise:
        body_lines.extend([premise, ""])
    adventure_path.write_text(
        frontmatter + "\n" + "\n".join(body_lines),
        encoding="utf-8",
    )
    return adventure_path
