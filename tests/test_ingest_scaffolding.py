"""Behavioral test for the deterministic scaffolder phase of `/ingest`.

What this test covers
---------------------
Issue #8 calls for a fixture-based test of `/ingest` scaffolding
correctness. The full `/ingest` workflow has four phases (see
`skills/ingest/SKILL.md`); only **Phase 1 (Scaffold)** is fully
deterministic — the agent reads templates, substitutes three
placeholders (`{{CAMPAIGN_NAME}}`, `{{CAMPAIGN_SYSTEM}}`,
`{{CAMPAIGN_PATH}}`), writes seven files (six committed + one
gitignored `.claude/settings.json`), runs `git init`, and makes
one initial commit. Phases 2–4 (survey, per-doc extraction, wrap-up)
are LLM-driven and out of scope here. See the README at
`tests/README.md` for the explicit coverage gap.

Per [ADR-0020](../docs/adr/0020-modularization-via-shared-references.md)
and v0.3 slice A (#81), the scaffolder procedure is now defined in
`references/scaffolder.md` so `/init-campaign` and `/init-adventure`
(standalone mode) consume the same single source of truth. This test
remains the canonical reference-impl: it mirrors the shared reference's
Steps 1–3 and pins the external behavior every consumer must produce.

This test embeds a *reference scaffolder* — a small Python
implementation of the shared reference's Steps 1–3 — and runs it
against a temporary target directory using the real `templates/`
directory that ships with the plugin. The test then asserts external
behavior only:

- The seven expected files were written at the documented paths (no
  more, no fewer at the documented locations).
- All placeholder tokens (`{{CAMPAIGN_NAME}}`, `{{CAMPAIGN_SYSTEM}}`,
  `{{CAMPAIGN_PATH}}`) were substituted — no `{{...}}` survives in
  any written file.
- The two `.claude/rules/*.md` files parse as YAML frontmatter +
  markdown body, and the Adventure rule file's documented `status`
  enum matches the canonical lifecycle set
  `{introduced, active, completed, abandoned}` from CONTEXT.md and
  ADR-0007.
- `.claude/settings.json` is valid JSON and contains a
  `permissions.allow` array.
- `git init` produced a repo with exactly one commit, the commit
  contains the six committed scaffolded paths (the seven written
  paths minus the gitignored `.claude/settings.json`) and nothing
  else, and no uncommitted state remains (the gitignored
  `.claude/settings.json` does not appear in `git status`).

The test asserts *behavior at the boundary* (files written, file
shape valid, git state clean), never internal extractor prose, never
LLM-phrased text. It does not consult the fixture's *content*
(`tests/fixtures/ingest_inputs/`) because Phase 1 doesn't read source
docs — Phase 1 only writes templates. The fixture exists for the
LLM-driven dedup integration test the PRD calls out (see
`tests/README.md`).

How to run
----------

    pytest tests/

or

    pytest tests/test_ingest_scaffolding.py -v

Requires `pytest` and `pyyaml` on the path. Both are standard.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest
import yaml


# The seven templated paths the scaffolder is contracted to write into
# a campaign repo, in the **exact write order** specified by
# `references/scaffolder.md` Step 2. Source paths are under
# `templates/` (with `.template` suffix); destination paths are
# relative to the campaign repo root.
#
# `.claude/settings.json` is FIRST so its `permissions.allow` rules
# are in effect for the remaining six writes — the one-prompt
# property the scaffolder reference guarantees. Slice A (#81) pinned
# this ordering with `TestWriteOrder` below.
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

# The canonical Adventure lifecycle set per CONTEXT.md ("Adventure")
# and ADR-0007 ("Temporal model and campaign overview"). Any change to
# this set is a domain-vocabulary change and must propagate through both
# the rule template and this test deliberately.
CANONICAL_ADVENTURE_STATUSES: frozenset[str] = frozenset(
    {"introduced", "active", "completed", "abandoned"}
)


# --------------------------------------------------------------------------
# Reference scaffolder — encodes SKILL.md Phase 1 Steps 1–3 in test code.
# --------------------------------------------------------------------------


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


def _run_git(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run a git command with a hermetic identity for committer + author.

    The plugin itself never configures `user.name` / `user.email`
    (SKILL.md Phase 1 Step 3). This test is *not* the plugin — it has
    to make the initial commit reproducibly in any environment,
    including CI. Identity is injected through env vars only for this
    subprocess, leaving the user's global git config untouched.
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
            # the assertions below.
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


def _existing_campaign_markers(target: Path) -> list[str]:
    """Return the subset of campaign markers present at `target`.

    Used by the reference scaffolder's Step 1 guard and by the
    idempotency tests below. Order of the returned list matches
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


# --------------------------------------------------------------------------
# Fixture: a fresh scaffolded campaign in a tmp_path target.
# --------------------------------------------------------------------------


@pytest.fixture
def scaffolded_campaign(
    tmp_path: Path,
    templates_dir: Path,
) -> Path:
    """A fresh campaign repo scaffolded into a temp directory.

    Named `The Sunless Citadel Revisited` / system `D&D 5e` matching
    the example values in SKILL.md so the substituted content reads
    naturally if a maintainer drops into the tmp directory to debug.
    """
    target = tmp_path / "campaign-under-test"
    scaffold_campaign(
        templates_dir=templates_dir,
        target=target,
        campaign_name="The Sunless Citadel Revisited",
        campaign_system="D&D 5e",
    )
    return target


# --------------------------------------------------------------------------
# Helpers used by multiple tests.
# --------------------------------------------------------------------------


def _split_frontmatter(text: str) -> tuple[dict, str]:
    """Split a markdown doc into (parsed-YAML-frontmatter, body).

    Returns `({}, text)` if the doc has no `---`-delimited frontmatter
    block. Raises `yaml.YAMLError` if a frontmatter block is present
    but unparseable — that's an external-behavior failure the test
    wants to surface.
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


# --------------------------------------------------------------------------
# Tests — external behavior only.
# --------------------------------------------------------------------------


class TestScaffoldedFiles:
    """The seven documented files land at the documented paths."""

    @pytest.mark.parametrize(
        "dest_rel",
        [dest for (_, dest) in EXPECTED_SCAFFOLDED_FILES],
    )
    def test_file_was_written(
        self,
        scaffolded_campaign: Path,
        dest_rel: str,
    ) -> None:
        assert (scaffolded_campaign / dest_rel).is_file(), (
            f"Scaffolder did not write {dest_rel}"
        )

    @pytest.mark.parametrize(
        "dest_rel",
        [dest for (_, dest) in EXPECTED_SCAFFOLDED_FILES],
    )
    def test_no_unsubstituted_placeholders_remain(
        self,
        scaffolded_campaign: Path,
        dest_rel: str,
    ) -> None:
        text = (scaffolded_campaign / dest_rel).read_text(encoding="utf-8")
        # The scaffolder is contracted to substitute every
        # `{{TOKEN}}` placeholder. Any survivor indicates a template
        # was changed without a matching scaffolder update.
        assert "{{" not in text and "}}" not in text, (
            f"{dest_rel} still contains an unsubstituted placeholder; "
            "the scaffolder's substitution map and the templates have "
            "drifted apart."
        )


class TestRuleFileFrontmatter:
    """The three scoped-rule files parse as valid YAML frontmatter + body."""

    def test_sessions_rule_frontmatter_parses(
        self,
        scaffolded_campaign: Path,
    ) -> None:
        text = (
            scaffolded_campaign / ".claude/rules/sessions.md"
        ).read_text(encoding="utf-8")
        fm, body = _split_frontmatter(text)
        assert "paths" in fm, (
            "sessions.md rule file missing `paths:` frontmatter scope"
        )
        assert isinstance(fm["paths"], list) and fm["paths"], (
            "`paths:` must be a non-empty list"
        )
        assert body.strip(), "Rule file body must not be empty"

    def test_adventures_rule_frontmatter_parses(
        self,
        scaffolded_campaign: Path,
    ) -> None:
        text = (
            scaffolded_campaign / ".claude/rules/adventures.md"
        ).read_text(encoding="utf-8")
        fm, body = _split_frontmatter(text)
        assert "paths" in fm, (
            "adventures.md rule file missing `paths:` frontmatter scope"
        )
        assert isinstance(fm["paths"], list) and fm["paths"], (
            "`paths:` must be a non-empty list"
        )
        assert body.strip(), "Rule file body must not be empty"

    def test_style_rule_frontmatter_parses(
        self,
        scaffolded_campaign: Path,
    ) -> None:
        """`.claude/rules/style.md` (issue #103, ADR-0021) lands shaped.

        The scaffolder ships the stub verbatim from
        `templates/.claude/rules/style.md.template`. Per ADR-0021 the
        frontmatter carries an eleven-glob `paths:` list covering every
        content-bearing campaign directory; the body is the GM-authored
        writing-style steering contract.
        """
        text = (
            scaffolded_campaign / ".claude/rules/style.md"
        ).read_text(encoding="utf-8")
        fm, body = _split_frontmatter(text)
        assert "paths" in fm, (
            "style.md rule file missing `paths:` frontmatter scope"
        )
        assert isinstance(fm["paths"], list) and fm["paths"], (
            "`paths:` must be a non-empty list"
        )
        assert body.strip(), "Rule file body must not be empty"

    def test_adventure_status_enum_matches_canonical_set(
        self,
        scaffolded_campaign: Path,
    ) -> None:
        """The Adventure rule file documents the canonical status enum.

        The body of `.claude/rules/adventures.md` documents the
        lifecycle states the scaffolder shipped to the campaign
        author. Per ADR-0007 and CONTEXT.md, the canonical set is
        `{introduced, active, completed, abandoned}`. If the rule file
        documents a different set, the scaffolded campaign would teach
        the GM a lifecycle the rest of the plugin does not honor.

        This is a structural check (token presence in the body), not a
        prose check — the test does not care how the file phrases the
        states, only that every canonical state name appears
        somewhere in the body.
        """
        text = (
            scaffolded_campaign / ".claude/rules/adventures.md"
        ).read_text(encoding="utf-8")
        _, body = _split_frontmatter(text)
        missing = {
            state for state in CANONICAL_ADVENTURE_STATUSES if state not in body
        }
        assert not missing, (
            f"Adventure rule file is missing canonical lifecycle "
            f"state(s) {sorted(missing)}; the scaffolder is shipping "
            "a campaign with a divergent Adventure lifecycle."
        )


class TestSettingsJson:
    """`.claude/settings.json` is valid JSON and shaped as documented."""

    def test_settings_is_valid_json(
        self,
        scaffolded_campaign: Path,
    ) -> None:
        text = (
            scaffolded_campaign / ".claude/settings.json"
        ).read_text(encoding="utf-8")
        # Will raise json.JSONDecodeError on malformed JSON, which
        # pytest surfaces with the failing template body.
        json.loads(text)

    def test_settings_has_permissions_allow_array(
        self,
        scaffolded_campaign: Path,
    ) -> None:
        data = json.loads(
            (
                scaffolded_campaign / ".claude/settings.json"
            ).read_text(encoding="utf-8")
        )
        assert "permissions" in data, "settings.json missing `permissions`"
        assert "allow" in data["permissions"], (
            "settings.json missing `permissions.allow`"
        )
        allow = data["permissions"]["allow"]
        assert isinstance(allow, list) and allow, (
            "`permissions.allow` must be a non-empty list of patterns"
        )

    def test_settings_paths_resolved_to_absolute(
        self,
        scaffolded_campaign: Path,
    ) -> None:
        """SKILL.md Phase 1 Step 2 bakes the absolute campaign path in.

        The template carries `/{{CAMPAIGN_PATH}}/...` patterns; after
        substitution they should resolve to `//absolute/path/...`. The
        leading `//` is intentional per the SKILL.md commentary — it
        is the form Claude Code's permission matcher requires. A
        leftover `{{CAMPAIGN_PATH}}` token here means the matcher
        will fail at runtime and the GM will get spurious permission
        prompts.
        """
        text = (
            scaffolded_campaign / ".claude/settings.json"
        ).read_text(encoding="utf-8")
        assert "{{CAMPAIGN_PATH}}" not in text, (
            "settings.json still contains the unsubstituted "
            "`{{CAMPAIGN_PATH}}` placeholder; permission matchers "
            "will not resolve correctly at runtime."
        )
        absolute = str(scaffolded_campaign.resolve())
        assert absolute in text, (
            "settings.json does not contain the absolute campaign "
            "path the matcher was supposed to be parameterised by."
        )

    def test_settings_plugin_read_rule_uses_claude_plugin_root(
        self,
        scaffolded_campaign: Path,
    ) -> None:
        """Issue #69: the plugin-install Read rule uses `${CLAUDE_PLUGIN_ROOT}`.

        Plugin-aware path references in JSON files (per Claude Code's
        plugin docs) use `${CLAUDE_PLUGIN_ROOT}`, which resolves at
        match time to the installed plugin root regardless of whether
        the plugin was installed via marketplace, local-development
        skills-directory clone, or any other install mode.

        Issue #69 replaced the prior `Read({{HOME}}/.claude/skills/...)`
        substitution (#63) with this form. The substitution machinery
        is no longer needed; the rule string lands verbatim in the
        rendered settings file.
        """
        data = json.loads(
            (
                scaffolded_campaign / ".claude/settings.json"
            ).read_text(encoding="utf-8")
        )
        allow = data["permissions"]["allow"]
        expected_rule = "Read(${CLAUDE_PLUGIN_ROOT}/**)"
        assert expected_rule in allow, (
            "settings.json does not contain the plugin-install Read "
            f"rule {expected_rule!r}; the marketplace-install path is "
            "broken because Claude Code's permission matcher has no "
            "way to pre-approve plugin reads. Per #69 this rule is "
            "the canonical shape."
        )
        # The literal `{{HOME}}` token must not appear — the substitution
        # machinery from #63 was dropped in #69.
        text = (
            scaffolded_campaign / ".claude/settings.json"
        ).read_text(encoding="utf-8")
        assert "{{HOME}}" not in text, (
            "settings.json contains the `{{HOME}}` placeholder; "
            "#69 dropped that substitution. Drop the placeholder from "
            "templates/.claude/settings.json.template."
        )
        # The old absolute-home form must not appear either; the new
        # rule is the only plugin-install Read rule in the template.
        home = str(Path.home())
        old_rule = f"Read({home}/.claude/skills/ttrpg-gm/**)"
        assert old_rule not in allow, (
            f"settings.json still contains the pre-#69 absolute-home "
            f"Read rule {old_rule!r}; #69 replaced it with "
            "`Read(${CLAUDE_PLUGIN_ROOT}/**)`."
        )


class TestGitInit:
    """`git init` and the initial commit landed exactly as documented."""

    def test_git_repo_was_initialized(
        self,
        scaffolded_campaign: Path,
    ) -> None:
        assert (scaffolded_campaign / ".git").is_dir(), (
            "scaffolder did not run `git init` on the target directory"
        )

    def test_initial_commit_exists(
        self,
        scaffolded_campaign: Path,
    ) -> None:
        result = subprocess.run(
            ["git", "rev-list", "--count", "HEAD"],
            cwd=scaffolded_campaign,
            capture_output=True,
            check=True,
            text=True,
        )
        count = int(result.stdout.strip())
        assert count == 1, (
            f"scaffolder should produce exactly one commit; found {count}"
        )

    def test_initial_commit_message(
        self,
        scaffolded_campaign: Path,
    ) -> None:
        """The commit message is part of the public contract.

        SKILL.md Phase 1 Step 3 specifies the exact subject line.
        Future tooling (e.g., `/upgrade-campaign`) may consult this
        commit's subject to detect plugin-scaffolded repos, so it is
        load-bearing.
        """
        result = subprocess.run(
            ["git", "log", "-1", "--pretty=%s"],
            cwd=scaffolded_campaign,
            capture_output=True,
            check=True,
            text=True,
        )
        subject = result.stdout.strip()
        assert subject == "Scaffold campaign repo via ttrpg-gm /ingest", (
            f"unexpected initial-commit subject: {subject!r}"
        )

    def test_working_tree_is_clean(
        self,
        scaffolded_campaign: Path,
    ) -> None:
        """No untracked or modified files after the scaffolder runs.

        Per SKILL.md Phase 1 Step 3, the scaffolder writes seven files
        (six committed + one gitignored `.claude/settings.json`) and
        commits exactly the six non-ignored files. The gitignored
        settings file does not appear in `git status --porcelain` —
        gitignored paths are filtered out by porcelain output. Anything
        else here means the scaffolder dropped a stray file or staged
        something that didn't get committed.
        """
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=scaffolded_campaign,
            capture_output=True,
            check=True,
            text=True,
        )
        assert result.stdout == "", (
            f"working tree is not clean after scaffold:\n{result.stdout}"
        )

    def test_initial_commit_tracks_exactly_the_documented_paths(
        self,
        scaffolded_campaign: Path,
    ) -> None:
        """The initial commit contains the six committed files only.

        `.claude/settings.json` is written to disk but gitignored from
        the start (issue #62 — its absolute paths are machine-local).
        It must not appear in the initial commit's tree.
        """
        result = subprocess.run(
            ["git", "ls-tree", "-r", "--name-only", "HEAD"],
            cwd=scaffolded_campaign,
            capture_output=True,
            check=True,
            text=True,
        )
        tracked = set(result.stdout.splitlines())
        expected = set(EXPECTED_COMMITTED_FILES)
        assert tracked == expected, (
            f"initial commit tracks the wrong set of files.\n"
            f"  expected: {sorted(expected)}\n"
            f"  actual:   {sorted(tracked)}"
        )
        assert ".claude/settings.json" not in tracked, (
            "`.claude/settings.json` should be gitignored (machine-local "
            "absolute paths); it must not appear in the initial commit."
        )


class TestCampaignOverviewPlaceholder:
    """`campaign.md` is the agent-maintained Campaign overview surface.

    Phase 1 writes a placeholder; Phase 4 (or `/wrap-session`)
    overwrites it later. This test verifies only the Phase 1 surface
    — the placeholder substitutes the campaign name into its H1 — not
    the Phase 4 regen content, which is LLM-driven.
    """

    def test_campaign_name_substituted_in_overview_h1(
        self,
        scaffolded_campaign: Path,
    ) -> None:
        text = (scaffolded_campaign / "campaign.md").read_text(
            encoding="utf-8"
        )
        first_line = text.splitlines()[0]
        assert "The Sunless Citadel Revisited" in first_line, (
            "campaign.md H1 did not receive the substituted campaign "
            f"name; first line was {first_line!r}"
        )


class TestStyleRuleShipped:
    """`.claude/rules/style.md` is shipped by the scaffolder (issue #103).

    Slice K (#100) landed `templates/.claude/rules/style.md.template`
    and the ADR/glossary/permissions-deny pieces but intentionally
    deferred the scaffolder wiring. Issue #103 closes that loop. These
    tests pin the wiring: the file is written to disk at the documented
    destination, it lands in the initial commit (the GM's voice belongs
    in version control per ADR-0021), and its bytes match the template
    verbatim — the scaffolder is a pass-through and the style template
    carries no `{{...}}` placeholders to substitute.
    """

    def test_style_rule_was_written(
        self,
        scaffolded_campaign: Path,
    ) -> None:
        assert (
            scaffolded_campaign / ".claude/rules/style.md"
        ).is_file(), (
            "Scaffolder did not write `.claude/rules/style.md`. "
            "Issue #103 wired the seventh template into the scaffolder; "
            "verify EXPECTED_SCAFFOLDED_FILES and the `git add` line."
        )

    def test_style_rule_is_in_initial_commit(
        self,
        scaffolded_campaign: Path,
    ) -> None:
        """The file is captured by the initial commit, not just on disk."""
        result = subprocess.run(
            ["git", "ls-tree", "-r", "--name-only", "HEAD"],
            cwd=scaffolded_campaign,
            capture_output=True,
            check=True,
            text=True,
        )
        tracked = set(result.stdout.splitlines())
        assert ".claude/rules/style.md" in tracked, (
            "`.claude/rules/style.md` is not tracked by the initial "
            "commit. Per ADR-0021 the GM's writing-style file rides in "
            "version control; the scaffolder's `git add` step must "
            "include it."
        )

    def test_style_rule_content_matches_template(
        self,
        scaffolded_campaign: Path,
        templates_dir: Path,
    ) -> None:
        """The scaffolder is a pass-through over the style.md template.

        `templates/.claude/rules/style.md.template` carries no
        `{{...}}` placeholders (verified by `test_style_template.py`),
        so the written file should be byte-identical to the template.
        Any drift here means a substitution leaked or the read/write
        path mangled the content.
        """
        template_text = (
            templates_dir / ".claude/rules/style.md.template"
        ).read_text(encoding="utf-8")
        written_text = (
            scaffolded_campaign / ".claude/rules/style.md"
        ).read_text(encoding="utf-8")
        assert written_text == template_text, (
            "`.claude/rules/style.md` does not match its template "
            "byte-for-byte. The style template carries no `{{...}}` "
            "placeholders, so the scaffolder should write it verbatim."
        )


# --------------------------------------------------------------------------
# Slice A (#81) additions — write order, gitignore membership, idempotency.
# --------------------------------------------------------------------------


class TestWriteOrder:
    """`.claude/settings.json` is written before the other six templates.

    Per `references/scaffolder.md` Step 2, the settings file is written
    first so its `permissions.allow` rules are in effect before the
    remaining six template writes. The agent only takes one permission
    prompt (the settings.json write itself); every subsequent write
    falls under the freshly-installed allow list. Reorderings would
    break that property and re-introduce per-file permission prompts.
    """

    def test_settings_json_is_written_first(
        self,
        tmp_path: Path,
        templates_dir: Path,
    ) -> None:
        target = tmp_path / "campaign-write-order"
        order: list[str] = []
        scaffold_campaign(
            templates_dir=templates_dir,
            target=target,
            campaign_name="Order Check",
            campaign_system="System X",
            write_order_sink=order,
        )
        assert order, "Reference scaffolder did not record any writes"
        assert order[0] == ".claude/settings.json", (
            "`.claude/settings.json` must be the first written file so "
            "its `permissions.allow` rules cover the remaining writes; "
            f"actual order: {order}"
        )

    def test_full_write_order_matches_reference_table(
        self,
        tmp_path: Path,
        templates_dir: Path,
    ) -> None:
        """All seven writes happen in the documented sequence.

        `references/scaffolder.md` Step 2 documents the exact write
        order in a numbered table; the scaffolder follows it without
        rearrangement. This test pins the full ordering, not just the
        settings-first property, so a future templates addition can't
        silently slip into the middle without a corresponding update
        here.
        """
        target = tmp_path / "campaign-full-order"
        order: list[str] = []
        scaffold_campaign(
            templates_dir=templates_dir,
            target=target,
            campaign_name="Full Order Check",
            campaign_system="System Y",
            write_order_sink=order,
        )
        expected = [dest for (_, dest) in EXPECTED_SCAFFOLDED_FILES]
        assert order == expected, (
            "Scaffolder write order drifted from "
            "`references/scaffolder.md` Step 2's table.\n"
            f"  expected: {expected}\n"
            f"  actual:   {order}"
        )


class TestSettingsJsonIsGitignored:
    """`.claude/settings.json` is gitignored from the start.

    Per `references/scaffolder.md` Step 2 (gitignore content) and Step
    3 (commit staging), the settings file is excluded from version
    control because it carries machine-local absolute paths. Three
    redundant signals confirm this:

    1. The committed `.gitignore` lists `.claude/settings.json`.
    2. `git check-ignore` agrees with that listing.
    3. `git status --porcelain` shows no entry for the file even though
       it exists on disk (already covered by
       `TestGitInit.test_working_tree_is_clean` and
       `TestGitInit.test_initial_commit_tracks_exactly_the_documented_paths`,
       but reasserted here as a slice-A summary).
    """

    def test_gitignore_lists_settings_json(
        self,
        scaffolded_campaign: Path,
    ) -> None:
        gitignore = (scaffolded_campaign / ".gitignore").read_text(
            encoding="utf-8"
        )
        # The token must appear on a non-comment line — a comment-only
        # mention would not actually ignore the file.
        ignored_lines = [
            line.strip()
            for line in gitignore.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        assert ".claude/settings.json" in ignored_lines, (
            "`.gitignore` does not include `.claude/settings.json` as "
            "an active (non-comment) pattern; the file's machine-local "
            "absolute paths would end up tracked.\n"
            f"  active patterns: {ignored_lines}"
        )

    def test_git_check_ignore_agrees_with_gitignore(
        self,
        scaffolded_campaign: Path,
    ) -> None:
        """`git check-ignore` is the authoritative oracle.

        `git check-ignore` exits 0 if the path is ignored, 1 if not.
        We invoke it without `--no-index` because the file is untracked
        — the default behavior covers the test case.
        """
        result = subprocess.run(
            ["git", "check-ignore", ".claude/settings.json"],
            cwd=scaffolded_campaign,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, (
            "`git check-ignore .claude/settings.json` did not report the "
            "file as ignored. Either the `.gitignore` pattern is wrong "
            "or the file is being tracked.\n"
            f"  stdout: {result.stdout!r}\n"
            f"  stderr: {result.stderr!r}"
        )


class TestIdempotency:
    """Re-running the scaffolder against an existing scaffold is a no-op.

    Per `references/scaffolder.md` "Idempotency: re-running against an
    existing scaffold", the scaffolder's Step 1 marker check stops
    before any file is written when any of `campaign.md`,
    `.claude/rules/sessions.md`, `.claude/rules/adventures.md`, or a
    non-trivial `.git/` is present. The existing campaign is untouched
    — no template overwrites, no second commit, no `git init` re-run.

    These tests cover the three observable consequences:

    1. The reference scaffolder raises (the spec's "stop" surface).
    2. The committed files are byte-identical before and after the
       attempted re-run.
    3. The git log still shows exactly one commit (no second commit
       got appended).
    """

    def test_rerun_stops_with_existing_scaffold_error(
        self,
        scaffolded_campaign: Path,
        templates_dir: Path,
    ) -> None:
        with pytest.raises(ScaffolderAlreadyScaffoldedError) as excinfo:
            scaffold_campaign(
                templates_dir=templates_dir,
                target=scaffolded_campaign,
                campaign_name="Different Name",
                campaign_system="Different System",
            )
        # The error surfaces the markers that triggered the stop so the
        # GM (and the test) can see which marker the scaffolder caught.
        # All three content markers from a fresh scaffold should be
        # detected; the `.git/` marker is also present (one commit).
        for expected_marker in EXISTING_CAMPAIGN_MARKERS:
            assert expected_marker in excinfo.value.markers, (
                f"Idempotency stop did not detect marker "
                f"{expected_marker!r}; markers seen: "
                f"{excinfo.value.markers}"
            )
        assert ".git/" in excinfo.value.markers, (
            "Idempotency stop did not detect the `.git/` marker even "
            "though the scaffolded campaign has a commit; markers seen: "
            f"{excinfo.value.markers}"
        )

    def test_rerun_does_not_modify_committed_files(
        self,
        scaffolded_campaign: Path,
        templates_dir: Path,
    ) -> None:
        """The six committed files are byte-identical after a rejected re-run."""
        before: dict[str, bytes] = {
            dest: (scaffolded_campaign / dest).read_bytes()
            for dest in EXPECTED_COMMITTED_FILES
        }
        with pytest.raises(ScaffolderAlreadyScaffoldedError):
            scaffold_campaign(
                templates_dir=templates_dir,
                target=scaffolded_campaign,
                campaign_name="Different Name",
                campaign_system="Different System",
            )
        after: dict[str, bytes] = {
            dest: (scaffolded_campaign / dest).read_bytes()
            for dest in EXPECTED_COMMITTED_FILES
        }
        assert before == after, (
            "Re-running the scaffolder against an existing scaffold "
            "modified at least one committed file. The scaffolder must "
            "be protective of populated targets per "
            "`references/scaffolder.md` Step 1."
        )

    def test_rerun_does_not_add_a_second_commit(
        self,
        scaffolded_campaign: Path,
        templates_dir: Path,
    ) -> None:
        with pytest.raises(ScaffolderAlreadyScaffoldedError):
            scaffold_campaign(
                templates_dir=templates_dir,
                target=scaffolded_campaign,
                campaign_name="Different Name",
                campaign_system="Different System",
            )
        result = subprocess.run(
            ["git", "rev-list", "--count", "HEAD"],
            cwd=scaffolded_campaign,
            capture_output=True,
            check=True,
            text=True,
        )
        count = int(result.stdout.strip())
        assert count == 1, (
            "Re-running the scaffolder against an existing scaffold "
            f"produced a second commit; expected 1, found {count}."
        )

    def test_rerun_leaves_working_tree_clean(
        self,
        scaffolded_campaign: Path,
        templates_dir: Path,
    ) -> None:
        """No stray uncommitted writes after a rejected re-run.

        If the scaffolder stops as documented, no files are written.
        `git status --porcelain` must therefore still be empty after
        the rejected re-run.
        """
        with pytest.raises(ScaffolderAlreadyScaffoldedError):
            scaffold_campaign(
                templates_dir=templates_dir,
                target=scaffolded_campaign,
                campaign_name="Different Name",
                campaign_system="Different System",
            )
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=scaffolded_campaign,
            capture_output=True,
            check=True,
            text=True,
        )
        assert result.stdout == "", (
            "Rejected re-run left the working tree dirty:\n"
            f"{result.stdout}"
        )


class TestSharedReferenceExists:
    """The shared `references/scaffolder.md` exists and is non-empty.

    Slice A (#81) extracted the scaffolder procedure into
    `references/scaffolder.md` per ADR-0020. The file's presence is
    load-bearing: `skills/ingest/SKILL.md` Phase 1 now cites it, and
    post-v0.3 `/init-campaign` and `/init-adventure` SKILL.md prose
    will cite it too. A missing file means the citation in SKILL.md
    dangles.
    """

    def test_scaffolder_reference_exists(self, repo_root: Path) -> None:
        ref = repo_root / "references" / "scaffolder.md"
        assert ref.is_file(), (
            "`references/scaffolder.md` not found. Slice A (#81) "
            "extracted the scaffolder procedure into this file; the "
            "`/ingest` SKILL.md Phase 1 prose cites it. A missing file "
            "means the citation dangles."
        )
        # Belt-and-suspenders: the file should be non-trivial. An
        # empty placeholder would satisfy `is_file()` but not the
        # citation contract.
        assert ref.stat().st_size > 1_000, (
            "`references/scaffolder.md` is suspiciously short "
            f"({ref.stat().st_size} bytes); slice A's extraction "
            "should produce a self-contained reference (several KB)."
        )
