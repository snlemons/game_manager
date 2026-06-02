"""Behavioral tests for the `/init-adventure` skill (v0.3 slice F).

What these tests cover
----------------------
Issue #90 introduces `/init-adventure` — net-new Adventure authoring,
with two modes auto-detected from cwd:

- **In-campaign mode** — adds `adventures/<slug>/adventure.md` (plus
  supporting Locations / NPCs / Threads / Beats / Secrets) to an
  already-scaffolded campaign.
- **Standalone mode** — invokes the shared scaffolder reference first
  (creating a campaign-shaped repo per ADR-0019), then runs the same
  in-campaign walkthrough. Output is structurally identical to
  `/init-campaign` output.

The walkthrough itself is LLM-driven (the GM-facing conversational
loop) and not deterministic. These tests pin **structural shape**:

- The SKILL.md exists at the conventional path with the right
  frontmatter.
- The SKILL.md uses relative paths to its references and templates
  (per #69's discipline; enforced campaign-wide by
  `test_plugin_manifest.py::TestRelativePathsInProse`, but a
  skill-local check here keeps the failure message specific).
- The in-campaign mode's documented output layout (an Adventure file
  at `adventures/<slug>/adventure.md` with the canonical frontmatter
  schema) round-trips through a reference-impl writer + the existing
  Adventure frontmatter validator from `test_frontmatter.py`.
- The standalone mode's documented output is structurally identical
  to the scaffolder's output (the same five-committed-files +
  one-gitignored-settings shape verified by
  `test_ingest_scaffolding.py`). This test re-uses the scaffolder
  reference impl as the contract: anything `/init-adventure --
  standalone` produces that the scaffolder also produces is correct
  by construction.

These tests do not assert LLM-phrased text, specific Adventure
content, or the conversational-refinement-loop's turn structure —
those are out-of-scope for reference-impl-style tests (per
`tests/README.md`'s "Why reference implementations, not real skill
invocations?" section).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

import pytest
import yaml


# Conventional path the skill ships at, per ADR-0013 (skills directory
# packaging) and the manifest auto-discovery contract.
SKILL_MD_PATH_RELATIVE: str = "skills/init-adventure/SKILL.md"


# The Adventure frontmatter schema, restated here so the test fails
# locally if a future schema change breaks `/init-adventure`'s output
# without updating its SKILL.md. Mirrors
# `references/frontmatter-schemas.md`'s Adventure section.
ADVENTURE_REQUIRED_FRONTMATTER_KEYS: frozenset[str] = frozenset(
    {
        "status",
        "order",
        "introduced",
        "started",
        "completed",
        "in_world_duration",
        "real_world_duration",
    }
)
ADVENTURE_STATUS_ENUM: frozenset[str] = frozenset(
    {"introduced", "active", "completed", "abandoned"}
)


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _split_frontmatter(text: str) -> tuple[dict, str]:
    """Split a markdown doc into (parsed-YAML-frontmatter, body).

    Returns `({}, text)` if the doc has no `---`-delimited frontmatter
    block. Mirrors the helper in `test_ingest_scaffolding.py` for
    independent test-file usability.
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
    """Slugify per `references/dedup-matching.md`'s normalization rule.

    Lowercase, strip leading "the ", collapse non-alphanumerics to single
    hyphens, trim leading/trailing hyphens. This is the minimal
    implementation the SKILL.md's Step 2a documents; the production
    skill follows the full reference.
    """
    s = name.strip().lower()
    if s.startswith("the "):
        s = s[4:]
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = s.strip("-")
    return s


# --------------------------------------------------------------------------
# Reference Adventure-file writer — encodes the SKILL.md's Step 2b output.
# --------------------------------------------------------------------------


def write_initial_adventure_file(
    *,
    campaign_root: Path,
    adventure_name: str,
    premise: Optional[str] = None,
) -> Path:
    """Write the initial Adventure file the SKILL.md Step 2 produces.

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


# --------------------------------------------------------------------------
# Tests — SKILL.md presence and shape.
# --------------------------------------------------------------------------


class TestSkillMdExistsAndIsWellFormed:
    """The SKILL.md is present at the conventional path with valid frontmatter."""

    def test_skill_md_file_exists(self, repo_root: Path) -> None:
        path = repo_root / SKILL_MD_PATH_RELATIVE
        assert path.is_file(), (
            f"Expected `/init-adventure` SKILL.md at {SKILL_MD_PATH_RELATIVE}; "
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
        assert fm.get("name") == "init-adventure", (
            "SKILL.md frontmatter must have `name: init-adventure` so "
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

    def test_skill_md_references_both_modes(
        self,
        repo_root: Path,
    ) -> None:
        """Both modes are documented somewhere in the SKILL.md.

        The skill's whole value-add per ADR-0019 is the mode split
        (in-campaign vs. standalone). A SKILL.md missing either mode's
        prose has lost the load-bearing part of the spec.

        This is a token-presence check, not a prose check — the
        wording can evolve as long as both terms appear.
        """
        text = (repo_root / SKILL_MD_PATH_RELATIVE).read_text(encoding="utf-8")
        lower = text.lower()
        assert "in-campaign" in lower, (
            "SKILL.md must document the in-campaign mode by name "
            "(token `in-campaign`)."
        )
        assert "standalone" in lower, (
            "SKILL.md must document the standalone mode by name "
            "(token `standalone`)."
        )


class TestSkillMdCitesSharedReferences:
    """Per ADR-0020, the skill consumes shared references via relative paths."""

    EXPECTED_REFERENCE_CITATIONS: tuple[str, ...] = (
        # The scaffolder reference — consumed by standalone mode.
        "../../references/scaffolder.md",
        # The conversational-refinement-loop reference — drives the
        # walkthrough mechanics.
        "../../references/conversational-refinement-loop.md",
        # Frontmatter schemas for Adventure / Thread / Beat / Secret.
        "../../references/frontmatter-schemas.md",
        # Reference-note extraction conventions for Locations + NPCs.
        "../../references/reference-note-extraction.md",
        # Beat-kind classification for set-piece / clue / escalation.
        "../../references/beat-kind-classification.md",
        # Secret extraction + bidi-link maintenance.
        "../../references/secret-extraction.md",
        "../../references/bidi-link-maintenance.md",
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
        to `/init-adventure` so a failure message points at the right
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
# Tests — In-campaign mode structural output.
# --------------------------------------------------------------------------


class TestInCampaignModeAdventureFile:
    """The in-campaign mode produces a valid Adventure file at the documented path."""

    def test_adventure_file_lands_at_documented_path(
        self,
        tmp_path: Path,
    ) -> None:
        # Pretend we have a scaffolded campaign root; the
        # in-campaign mode walkthrough lands the Adventure file under
        # `adventures/<slug>/adventure.md` regardless of what else is
        # in the campaign root.
        campaign_root = tmp_path / "fake-campaign"
        campaign_root.mkdir()
        path = write_initial_adventure_file(
            campaign_root=campaign_root,
            adventure_name="The Whitebridge Job",
            premise="A heist at the merchant Whitebridge's manor.",
        )
        assert path == campaign_root / "adventures/whitebridge-job/adventure.md", (
            "Adventure file must land at `adventures/<slug>/adventure.md` "
            "per the SKILL.md Step 2b output spec and the Adventure "
            "frontmatter-schema's filename rule. Got: "
            f"{path.relative_to(campaign_root)}"
        )
        assert path.is_file()

    def test_adventure_frontmatter_uses_canonical_schema(
        self,
        tmp_path: Path,
    ) -> None:
        campaign_root = tmp_path / "fake-campaign"
        campaign_root.mkdir()
        path = write_initial_adventure_file(
            campaign_root=campaign_root,
            adventure_name="Heist at the Crimson Ledger",
        )
        fm, _ = _split_frontmatter(path.read_text(encoding="utf-8"))
        missing = ADVENTURE_REQUIRED_FRONTMATTER_KEYS - fm.keys()
        assert not missing, (
            f"Adventure file missing required frontmatter keys {sorted(missing)}; "
            "the Adventure schema from `references/frontmatter-schemas.md` is "
            "the contract `/init-adventure` outputs against."
        )

    def test_adventure_status_is_introduced_at_creation(
        self,
        tmp_path: Path,
    ) -> None:
        """Per the Adventure schema's 'Defaults at creation' section,
        a net-new Adventure starts at `status: introduced` (party knows
        about it but hasn't started running it). `/wrap-session` flips
        it to `active` when the party engages.
        """
        campaign_root = tmp_path / "fake-campaign"
        campaign_root.mkdir()
        path = write_initial_adventure_file(
            campaign_root=campaign_root,
            adventure_name="The Sunless Citadel",
        )
        fm, _ = _split_frontmatter(path.read_text(encoding="utf-8"))
        assert fm["status"] == "introduced", (
            "A newly authored Adventure must start at `status: introduced` "
            "per the schema's defaults-at-creation rule. Got: "
            f"{fm['status']!r}."
        )
        assert fm["status"] in ADVENTURE_STATUS_ENUM, (
            f"Adventure status {fm['status']!r} is outside the canonical "
            f"enum {sorted(ADVENTURE_STATUS_ENUM)}."
        )

    def test_adventure_dates_are_null_at_creation(
        self,
        tmp_path: Path,
    ) -> None:
        """All four date fields are `~` (null) at design time —
        `introduced` / `started` / `completed` are session-driven
        transitions written by `/wrap-session`. `/init-adventure` is
        pre-session authoring; it has no dates to attribute.

        Per the schema: "Never invent dates."
        """
        campaign_root = tmp_path / "fake-campaign"
        campaign_root.mkdir()
        path = write_initial_adventure_file(
            campaign_root=campaign_root,
            adventure_name="Lost Mines of Phandelver",
        )
        fm, _ = _split_frontmatter(path.read_text(encoding="utf-8"))
        for date_field in ("introduced", "started", "completed"):
            assert fm[date_field] is None, (
                f"Adventure field `{date_field}` should be null (`~`) at "
                "design-time creation; only `/wrap-session` populates date "
                f"fields. Got: {fm[date_field]!r}."
            )

    def test_adventure_body_includes_h1_with_canonical_name(
        self,
        tmp_path: Path,
    ) -> None:
        campaign_root = tmp_path / "fake-campaign"
        campaign_root.mkdir()
        path = write_initial_adventure_file(
            campaign_root=campaign_root,
            adventure_name="The Whitebridge Job",
            premise="A heist at the merchant Whitebridge's manor.",
        )
        _, body = _split_frontmatter(path.read_text(encoding="utf-8"))
        first_non_blank = next(
            (line for line in body.splitlines() if line.strip()),
            "",
        )
        assert first_non_blank == "# The Whitebridge Job", (
            "Adventure body's first non-blank line must be the H1 with "
            f"the canonical name. Got: {first_non_blank!r}."
        )


# --------------------------------------------------------------------------
# Tests — Standalone mode structural output (matches scaffolder).
# --------------------------------------------------------------------------


class TestStandaloneModeMatchesScaffolderShape:
    """Standalone mode's output is structurally identical to the scaffolder's.

    Per ADR-0019, a one-shot is a single-Adventure campaign — no
    separate repo shape. The standalone mode invokes the same
    scaffolder reference any other `/init-*` skill would (and that
    `test_ingest_scaffolding.py` pins down), then layers the Adventure
    content on top.

    These tests verify the *structural commitment* — that the
    standalone case's pre-Adventure surface is byte-equivalent to the
    scaffolder's output. The Adventure-layering is covered by the
    `TestInCampaignModeAdventureFile` cases (the walkthrough is the
    same in both modes once the campaign root is scaffolded).
    """

    def test_standalone_scaffold_produces_the_six_documented_files(
        self,
        tmp_path: Path,
        templates_dir: Path,
    ) -> None:
        # Import the reference scaffolder from the sibling test file;
        # both tests share the contract that the scaffolder produces
        # exactly six files (five committed + one gitignored
        # `.claude/settings.json`).
        from test_ingest_scaffolding import (
            EXPECTED_SCAFFOLDED_FILES,
            scaffold_campaign,
        )

        target = tmp_path / "standalone-oneshot"
        scaffold_campaign(
            templates_dir=templates_dir,
            target=target,
            # In standalone mode the campaign name conventionally
            # equals the Adventure name (the SKILL.md Step 1 note
            # documents the option to override).
            campaign_name="The Whitebridge Job",
            campaign_system="D&D 5e",
        )

        for _, dest_rel in EXPECTED_SCAFFOLDED_FILES:
            assert (target / dest_rel).is_file(), (
                f"Standalone-mode scaffold did not write {dest_rel}; "
                "per ADR-0019 standalone mode must produce a "
                "campaign-shaped repo structurally identical to "
                "`/init-campaign`'s output."
            )

    def test_standalone_scaffold_plus_adventure_yields_campaign_shape(
        self,
        tmp_path: Path,
        templates_dir: Path,
    ) -> None:
        """End-to-end standalone shape check.

        Scaffold the campaign, then layer the Adventure file on top —
        the resulting tree should be a fully-shaped campaign with one
        Adventure pre-populated, ready for `/prep-session` to draft
        session 1 against.
        """
        from test_ingest_scaffolding import scaffold_campaign

        target = tmp_path / "standalone-oneshot"
        scaffold_campaign(
            templates_dir=templates_dir,
            target=target,
            campaign_name="The Whitebridge Job",
            campaign_system="D&D 5e",
        )
        adventure_path = write_initial_adventure_file(
            campaign_root=target,
            adventure_name="The Whitebridge Job",
            premise="A heist at the merchant Whitebridge's manor.",
        )

        # The campaign-shape commitments per ADR-0019:
        # 1) CLAUDE.md present (scaffolder wrote it).
        assert (target / "CLAUDE.md").is_file()
        # 2) campaign.md present (scaffolder wrote a placeholder; the
        #    Step 4 regen will replace it with a composed overview).
        assert (target / "campaign.md").is_file()
        # 3) .claude/rules/{sessions,adventures}.md present.
        assert (target / ".claude/rules/sessions.md").is_file()
        assert (target / ".claude/rules/adventures.md").is_file()
        # 4) Exactly one Adventure under `adventures/`.
        adventures_root = target / "adventures"
        assert adventures_root.is_dir()
        adventures = [p for p in adventures_root.iterdir() if p.is_dir()]
        assert len(adventures) == 1, (
            f"Standalone mode should produce exactly one Adventure "
            f"directory; got {len(adventures)}: "
            f"{[p.name for p in adventures]}."
        )
        # 5) The Adventure file at the documented path validates.
        assert adventure_path.is_file()
        fm, _ = _split_frontmatter(adventure_path.read_text(encoding="utf-8"))
        assert fm["status"] == "introduced"
