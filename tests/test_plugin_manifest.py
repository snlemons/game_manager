"""Pin the Claude Code plugin manifest's shape.

Issue #69 added `.claude-plugin/plugin.json` so `/plugin install
https://github.com/snlemons/game_manager` discovers the three skills
without the user having to clone into a specific user-level directory.
These tests assert the manifest exists at the canonical path, parses
as JSON, declares the plugin's identity, and lists each shipped skill
with a SKILL.md actually present at the declared path.

The exact manifest schema Claude Code expects may shift across
versions; these tests pin only the load-bearing invariants the issue
calls out:

- a manifest file exists at `.claude-plugin/plugin.json`
- it parses as JSON
- it carries `name`, `version`, `description`
- each entry under `skills` resolves to an on-disk directory containing
  a `SKILL.md` file at its top
- the plugin name matches the `ttrpg-gm` identity used throughout the
  repo (path bake-ins, scaffolder commit subject, README).

Schema fields beyond these load-bearing ones are intentionally not
pinned — they may be added or renamed as the Claude Code plugin
ecosystem evolves without breaking these tests.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture(scope="module")
def manifest_path(repo_root: Path) -> Path:
    return repo_root / ".claude-plugin" / "plugin.json"


@pytest.fixture(scope="module")
def manifest(manifest_path: Path) -> dict:
    return json.loads(manifest_path.read_text(encoding="utf-8"))


class TestManifestPresence:
    """The manifest file exists at the canonical Claude Code path."""

    def test_claude_plugin_directory_exists(self, repo_root: Path) -> None:
        assert (repo_root / ".claude-plugin").is_dir(), (
            "Claude Code's plugin discovery expects a `.claude-plugin/` "
            "directory at the repo root. Without it, `/plugin install` "
            "has no manifest to read and the skills fail to register."
        )

    def test_manifest_file_exists(self, manifest_path: Path) -> None:
        assert manifest_path.is_file(), (
            f"Plugin manifest missing at {manifest_path}. Per issue "
            "#69, the manifest is the entry point for `/plugin install` "
            "discovery."
        )

    def test_manifest_parses_as_json(self, manifest_path: Path) -> None:
        try:
            json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            pytest.fail(
                f"{manifest_path} is not valid JSON: {exc}. Claude Code "
                "cannot register the plugin if the manifest does not "
                "parse."
            )


class TestManifestIdentity:
    """Required identity fields are present and match the repo."""

    def test_name_is_ttrpg_gm(self, manifest: dict) -> None:
        """The plugin name is the load-bearing identifier baked into
        path references (`~/.claude/skills/ttrpg-gm/...`), the
        scaffolder commit subject (`Scaffold campaign repo via
        ttrpg-gm /ingest`), and `references/` cross-doc links. Renaming
        the plugin without updating those is a guaranteed break.
        """
        assert manifest.get("name") == "ttrpg-gm", (
            "Plugin `name` must be `ttrpg-gm` — every path bake-in and "
            "the scaffolder's commit subject depend on this exact "
            "string."
        )

    def test_version_is_present(self, manifest: dict) -> None:
        version = manifest.get("version")
        assert isinstance(version, str) and version, (
            "Plugin `version` must be a non-empty string. `/plugin "
            "update` relies on it for upgrade detection."
        )

    def test_description_is_present(self, manifest: dict) -> None:
        description = manifest.get("description")
        assert isinstance(description, str) and description, (
            "Plugin `description` must be a non-empty string — it's "
            "what `/plugin list` and the marketplace UI show."
        )


class TestManifestSkills:
    """Each declared skill resolves to an on-disk SKILL.md."""

    def test_skills_field_lists_three_entries(self, manifest: dict) -> None:
        """v0.2 ships exactly three skills: `/ingest`,
        `/prep-session`, `/wrap-session`. If the manifest's skill
        count drifts from this, either a skill was added without
        manifesting it or the manifest was hand-edited out of sync.
        """
        skills = manifest.get("skills")
        assert isinstance(skills, list), (
            "Manifest `skills` must be a list of skill directory "
            "paths relative to the plugin root."
        )
        assert len(skills) == 3, (
            f"Expected 3 skills in the manifest (v0.2 ships /ingest, "
            f"/prep-session, /wrap-session); found {len(skills)}."
        )

    def test_each_declared_skill_resolves_to_a_skill_md(
        self,
        repo_root: Path,
        manifest: dict,
    ) -> None:
        """The manifest's `skills` list points at directories inside
        the repo, each containing a `SKILL.md` at its top. This is
        the file Claude Code reads to register the skill.
        """
        for skill_rel in manifest["skills"]:
            skill_dir = repo_root / skill_rel
            assert skill_dir.is_dir(), (
                f"Manifest declares skill at `{skill_rel}` but no "
                f"such directory exists in the repo. Either the path "
                "drifted or a skill was removed without updating the "
                "manifest."
            )
            skill_md = skill_dir / "SKILL.md"
            assert skill_md.is_file(), (
                f"Manifest declares skill at `{skill_rel}` but "
                f"`{skill_rel}/SKILL.md` is missing. Claude Code's "
                "registration reads from this file; without it the "
                "skill is unusable."
            )

    def test_three_known_skills_are_declared(self, manifest: dict) -> None:
        """The three v0.2 skills are declared by their canonical
        relative paths.
        """
        declared = set(manifest["skills"])
        expected = {
            "skills/ingest",
            "skills/prep-session",
            "skills/wrap-session",
        }
        assert declared == expected, (
            f"Manifest skills set drift: expected {expected}, "
            f"got {declared}."
        )
