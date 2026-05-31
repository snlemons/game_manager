"""Behavioral test for the deterministic scaffolder phase of `/ingest`.

What this test covers
---------------------
Issue #8 calls for a fixture-based test of `/ingest` scaffolding
correctness. The full `/ingest` workflow has four phases (see
`skills/ingest/SKILL.md`); only **Phase 1 (Scaffold)** is fully
deterministic — the agent reads templates, substitutes three
placeholders (`{{CAMPAIGN_NAME}}`, `{{CAMPAIGN_SYSTEM}}`,
`{{CAMPAIGN_PATH}}`), writes six files (five committed + one
gitignored `.claude/settings.json`), runs `git init`, and makes
one initial commit. Phases 2–4 (survey, per-doc extraction, wrap-up)
are LLM-driven and out of scope here. See the README at
`tests/README.md` for the explicit coverage gap.

This test embeds a *reference scaffolder* — a small Python
implementation of SKILL.md Phase 1 Steps 1–3 — and runs it against a
temporary target directory using the real `templates/` directory that
ships with the plugin. The test then asserts external behavior only:

- The six expected files were written at the documented paths (no
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
  contains the five committed scaffolded paths (the six written
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


# The six templated paths the scaffolder is contracted to write into a
# campaign repo. Source paths are under `templates/` (with `.template`
# suffix); destination paths are relative to the campaign repo root.
EXPECTED_SCAFFOLDED_FILES: list[tuple[str, str]] = [
    ("CLAUDE.md.template", "CLAUDE.md"),
    (".claude/rules/sessions.md.template", ".claude/rules/sessions.md"),
    (".claude/rules/adventures.md.template", ".claude/rules/adventures.md"),
    (".claude/settings.json.template", ".claude/settings.json"),
    ("campaign.md.template", "campaign.md"),
    (".gitignore.template", ".gitignore"),
]

# The five paths actually staged into the initial commit. This is the
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

    Per SKILL.md Phase 1 Step 2, `{{CAMPAIGN_PATH}}` is the resolved
    absolute path *without* a trailing slash. The template inserts a
    leading `/` in the matcher pattern, so the substituted value should
    not start with one — `str(Path)` already produces the bare form.
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


def scaffold_campaign(
    *,
    templates_dir: Path,
    target: Path,
    campaign_name: str,
    campaign_system: str,
) -> None:
    """Run the deterministic Phase 1 scaffolder against `target`.

    Mirrors SKILL.md Phase 1 Steps 1–3:

    - Create the target if it doesn't exist (Step 1).
    - For each templated path, read the `.template` file, apply
      placeholder substitutions, and write to the destination path,
      stripping the `.template` suffix (Step 2). Intermediate
      directories are created on demand.
    - Run `git init`, stage the five committed written files
      explicitly (the gitignored `.claude/settings.json` is excluded),
      commit with the documented message (Step 3).

    The reference scaffolder skips Step 1's "existing-campaign
    markers" guard (the test creates a fresh empty `target`, so the
    guard is vacuously satisfied) and skips Step 4's GM-facing report.
    Both are LLM-/user-interaction surface, not the deterministic
    behavior the test pins down.
    """
    target = target.resolve()
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

    _run_git("init", "--initial-branch=main", cwd=target)
    # `.claude/settings.json` is intentionally absent from this argument
    # list — it's written to disk above (its permissions are in effect
    # for the rest of Phase 1) but gitignored by the `.gitignore` that
    # was also just written. See issue #62.
    _run_git(
        "add",
        "CLAUDE.md",
        ".claude/rules/sessions.md",
        ".claude/rules/adventures.md",
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
    """The six documented files land at the documented paths."""

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
    """The two scoped-rule files parse as valid YAML frontmatter + body."""

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

        Per SKILL.md Phase 1 Step 3, the scaffolder writes six files
        (five committed + one gitignored `.claude/settings.json`) and
        commits exactly the five non-ignored files. The gitignored
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
        """The initial commit contains the five committed files only.

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
