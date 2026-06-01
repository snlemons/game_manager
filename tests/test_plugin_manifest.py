"""Plugin manifest validation for `.claude-plugin/plugin.json`.

Issue #69 adds a canonical Claude Code plugin manifest at
`.claude-plugin/plugin.json` so the repo installs cleanly via
`/plugin install <github-url>` (marketplace mode) in addition to the
local-development `git clone ~/.claude/skills/ttrpg-gm` mode it
already supports.

These tests pin the manifest's shape against Anthropic's plugin docs:

- File exists at the canonical location and parses as JSON.
- Required `name` field is present and matches the conventional plugin
  name `ttrpg-gm`.
- Manifest does NOT contain a `skills` array. The earlier PR #78
  attempt added one; per Anthropic's docs, declaring skills in the
  manifest breaks Claude Code (skills are auto-discovered from the
  `skills/` directory). This is the canonical regression check.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


MANIFEST_PATH_RELATIVE: str = ".claude-plugin/plugin.json"


@pytest.fixture(scope="module")
def manifest_path(repo_root: Path) -> Path:
    """Absolute path to the canonical plugin manifest."""
    return repo_root / MANIFEST_PATH_RELATIVE


@pytest.fixture(scope="module")
def manifest_data(manifest_path: Path) -> dict:
    """Parsed manifest JSON, read once per module."""
    return json.loads(manifest_path.read_text(encoding="utf-8"))


class TestManifestExistsAndParses:
    """The manifest exists at the canonical path and is valid JSON."""

    def test_manifest_file_exists(self, manifest_path: Path) -> None:
        assert manifest_path.is_file(), (
            f"Plugin manifest not found at {MANIFEST_PATH_RELATIVE}. "
            "Per Anthropic's plugin docs, the manifest must live at "
            "`.claude-plugin/plugin.json` at the plugin repo root for "
            "the plugin to install via `/plugin install <url>`."
        )

    def test_manifest_parses_as_json(self, manifest_path: Path) -> None:
        # Raises json.JSONDecodeError if malformed; pytest surfaces the
        # failing body in the report.
        json.loads(manifest_path.read_text(encoding="utf-8"))


class TestManifestRequiredFields:
    """Required-field shape per Anthropic's plugin docs.

    Per the docs, the only REQUIRED field is `name`. Other fields are
    optional but the plugin ships several conventional ones.
    """

    def test_name_is_ttrpg_gm(self, manifest_data: dict) -> None:
        assert manifest_data.get("name") == "ttrpg-gm", (
            "Plugin manifest `name` field must be `ttrpg-gm` so the "
            "plugin's slash commands and skill directory naming line "
            "up with the install path convention. Current value: "
            f"{manifest_data.get('name')!r}."
        )


class TestManifestDoesNotDeclareSkills:
    """Regression check for PR #78's mistake.

    PR #78 tried to add a `skills` array to the manifest declaring the
    three skills (`/ingest`, `/prep-session`, `/wrap-session`). Per
    Anthropic's plugin docs, this is wrong — Claude Code auto-discovers
    skills from the `skills/` directory, and declaring them in the
    manifest breaks plugin loading. #69 replaces #78 with the correct
    shape; this test prevents a regression.
    """

    def test_manifest_has_no_skills_array(self, manifest_data: dict) -> None:
        assert "skills" not in manifest_data, (
            "Plugin manifest contains a `skills` array. Per Anthropic's "
            "plugin docs, skills are auto-discovered from the `skills/` "
            "directory and declaring them in the manifest breaks Claude "
            "Code. (This was PR #78's mistake; #69 reverts and fixes.)"
        )

    def test_skills_directory_has_three_skill_md_files(
        self,
        repo_root: Path,
    ) -> None:
        """The three skills the manifest no longer declares must exist on disk.

        Belt-and-suspenders for the auto-discovery contract: skills come
        from the filesystem, not the manifest, so the three SKILL.md
        files must be present at their conventional paths.
        """
        for skill_name in ("ingest", "prep-session", "wrap-session"):
            skill_path = repo_root / "skills" / skill_name / "SKILL.md"
            assert skill_path.is_file(), (
                f"Expected skill file at {skill_path.relative_to(repo_root)} "
                "for Claude Code auto-discovery. The manifest does not "
                "declare skills; their presence on disk is the contract."
            )


class TestRelativePathsInProse:
    """Markdown prose under `skills/` and `references/` uses relative paths.

    Per #69's fix shape and the known Claude Code bug at
    anthropics/claude-code#9354, the `${CLAUDE_PLUGIN_ROOT}` variable
    only works in JSON files — not in markdown prose. So skill prose
    and reference prose must use relative paths (e.g.,
    `../../references/foo.md` from a SKILL.md at depth 2, or
    `foo.md` between siblings in `references/`) rather than the
    `~/.claude/skills/ttrpg-gm/...` absolute install-path form that
    PRs #50 / #51 / #67 originally baked in.

    Absolute install paths only resolve under local-development install
    mode; they break under marketplace install (where the plugin lives
    at `~/.claude/plugins/cache/<marketplace>/ttrpg-gm/<version>/`).
    """

    ABSOLUTE_INSTALL_PREFIX: str = "~/.claude/skills/ttrpg-gm"

    def test_no_absolute_install_paths_in_skills_prose(
        self,
        repo_root: Path,
    ) -> None:
        offenders: list[tuple[Path, int]] = []
        for md_path in (repo_root / "skills").rglob("*.md"):
            content = md_path.read_text(encoding="utf-8")
            if self.ABSOLUTE_INSTALL_PREFIX in content:
                line_no = next(
                    (
                        i + 1
                        for i, line in enumerate(content.splitlines())
                        if self.ABSOLUTE_INSTALL_PREFIX in line
                    ),
                    0,
                )
                offenders.append((md_path.relative_to(repo_root), line_no))
        assert not offenders, (
            f"Found absolute install-path references "
            f"`{self.ABSOLUTE_INSTALL_PREFIX}/...` in skills prose:\n"
            + "\n".join(f"  {path}:{line}" for path, line in offenders)
            + "\n\nPer #69 (and anthropics/claude-code#9354), markdown "
            "prose must use relative paths — the absolute install-path "
            "form breaks under marketplace install."
        )

    def test_no_absolute_install_paths_in_references_prose(
        self,
        repo_root: Path,
    ) -> None:
        offenders: list[tuple[Path, int]] = []
        for md_path in (repo_root / "references").rglob("*.md"):
            content = md_path.read_text(encoding="utf-8")
            # The preflight reference intentionally documents the
            # pre-#69 rule shape in a regression-context note. Allow a
            # mention of the literal old rule string inside a backtick
            # span; reject any other use. We narrow this by checking the
            # exact pre-#69 rule fragment, not the broader install-path
            # prefix.
            if self.ABSOLUTE_INSTALL_PREFIX in content:
                line_no = next(
                    (
                        i + 1
                        for i, line in enumerate(content.splitlines())
                        if self.ABSOLUTE_INSTALL_PREFIX in line
                    ),
                    0,
                )
                offenders.append((md_path.relative_to(repo_root), line_no))
        assert not offenders, (
            f"Found absolute install-path references "
            f"`{self.ABSOLUTE_INSTALL_PREFIX}/...` in references prose:\n"
            + "\n".join(f"  {path}:{line}" for path, line in offenders)
            + "\n\nPer #69, references must use relative paths (e.g., "
            "`foo.md` for a same-directory sibling, `../templates/...` "
            "for a sibling-directory target). The absolute install-path "
            "form breaks under marketplace install."
        )
