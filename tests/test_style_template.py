"""Structural validation for `templates/.claude/rules/style.md.template`.

Per [ADR-0021](../docs/adr/0021-gm-writing-style-via-claude-rules-style.md),
the GM-authored writing-style guide ships as a stub at
`.claude/rules/style.md` whose `paths:` frontmatter auto-loads it
whenever the agent edits artifacts under any of eleven content-bearing
campaign directories. This test enforces the structural invariants of
that stub and the `permissions.deny` interlock in the settings template
that backs the GM-authored-not-agent-written contract.

Three categories of check:

1. **Stub frontmatter shape.** YAML parses cleanly; `paths:` is a list;
   the eleven documented globs are present. A careless edit that drops a
   glob silently disables the auto-load on that directory, defeating
   the steering for whichever artifacts live there.

2. **Stub body invariants.** The GM-authored-not-agent-written contract
   is stated in the file's header prose. The line-count budget from
   ADR-0021 ("roughly 50 to 200 lines") holds. ASCII-only quotes (the
   plugin convention — see `test_settings_template.py`'s smart-quote
   check). Each documented placeholder section heading appears.

3. **Deny interlock present.** The settings template carries
   `Edit` / `Write` / `MultiEdit` deny entries against the style file
   path. The deny block is the permission-matcher backstop for the
   prose contract in the stub's header; without it, the agent's
   pre-approved `.claude/**` allow entries would let a sub-agent write
   to the file unchecked.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml


# --------------------------------------------------------------------------
# Canonical invariants from ADR-0021.
# --------------------------------------------------------------------------


# The eleven content-bearing directory globs that drive auto-load. Listed
# in the order they appear in the stub so parametrized failures point at
# the right line. Adding a directory in a later version means extending
# this tuple deliberately, which surfaces the change in code review.
EXPECTED_PATHS_GLOBS: tuple[str, ...] = (
    "sessions/**/*.md",
    "adventures/**/*.md",
    "npcs/**/*.md",
    "pcs/**/*.md",
    "locations/**/*.md",
    "factions/**/*.md",
    "items/**/*.md",
    "threads/**/*.md",
    "consequences/**/*.md",
    "beats/**/*.md",
    "secrets/**/*.md",
)

# Placeholder section headings the stub ships with. ADR-0021 names these
# as the categories surfaced by issue #56; reorganization (renaming,
# dropping, adding) is a deliberate template change, surfaced as a test
# diff.
EXPECTED_SECTION_HEADINGS: tuple[str, ...] = (
    "## Formality and register",
    "## Tense (especially for Logs)",
    "## Vocabulary preferences",
    "## PC referencing conventions",
    "## Narrative voice",
    "## Anything else",
)

# The GM-authored-not-agent-written contract prose. The exact wording
# below is a substring check, not a verbatim block — minor copy edits
# don't fail the test, but removing the contract entirely does. The
# contract is the primary mechanism per ADR-0021 ("the deny entries are
# an interlock, not the primary contract — the primary contract is the
# prose at the top of the file").
CONTRACT_PROSE_SUBSTRINGS: tuple[str, ...] = (
    "GM-authored",
    "does not write to this file",
)

# Line-count budget from ADR-0021's "Template content principles" section:
# "roughly 50 to 200 lines." Enforced as a window with slack at both ends
# so the stub can grow or shrink slightly without churning the test.
LINE_COUNT_MIN: int = 30
LINE_COUNT_MAX: int = 220

# Smart-quote characters, reused from `test_settings_template.py`. The
# plugin convention is ASCII-only quotes across templates.
SMART_QUOTE_CHARS: tuple[str, ...] = (
    "“",  # left double quotation mark
    "”",  # right double quotation mark
    "‘",  # left single quotation mark
    "’",  # right single quotation mark
)

# Deny-block entries the settings template must carry, per ADR-0021's
# permission-matcher interlock. Template-shape strings (with
# `{{CAMPAIGN_PATH}}` literal) so the test is host-independent.
EXPECTED_DENY_ENTRIES: tuple[str, ...] = (
    "Edit(/{{CAMPAIGN_PATH}}/.claude/rules/style.md)",
    "Write(/{{CAMPAIGN_PATH}}/.claude/rules/style.md)",
    "MultiEdit(/{{CAMPAIGN_PATH}}/.claude/rules/style.md)",
)


# --------------------------------------------------------------------------
# Fixtures.
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def style_template_path(templates_dir: Path) -> Path:
    """Absolute path to the raw `style.md.template` file."""
    return templates_dir / ".claude" / "rules" / "style.md.template"


@pytest.fixture(scope="module")
def style_template_raw(style_template_path: Path) -> str:
    """Pre-substitution stub contents, read once per module."""
    return style_template_path.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def style_template_frontmatter(style_template_raw: str) -> dict:
    """Parse the stub's YAML frontmatter into a dict.

    Frontmatter is the leading `---`-delimited block. If the block is
    missing or malformed, this fixture fails the test that uses it with
    a YAML parse error — which is the correct failure mode for a stub
    whose frontmatter drives auto-load.
    """
    match = re.match(r"^---\n(.*?)\n---\n", style_template_raw, re.DOTALL)
    if match is None:
        pytest.fail(
            "Style template does not start with a `---`-delimited "
            "YAML frontmatter block. Auto-load via `paths:` requires "
            "the frontmatter; without it, the rule never fires."
        )
    return yaml.safe_load(match.group(1))


@pytest.fixture(scope="module")
def settings_template_raw_for_deny(templates_dir: Path) -> str:
    """Raw settings template contents for deny-block checks."""
    return (templates_dir / ".claude" / "settings.json.template").read_text(
        encoding="utf-8"
    )


# --------------------------------------------------------------------------
# Frontmatter shape.
# --------------------------------------------------------------------------


class TestStubFrontmatter:
    """The stub's YAML frontmatter drives `.claude/rules/` auto-load.

    A missing or wrong-shaped `paths:` value silently disables the
    style steering on the missing directories — exactly the
    silent-failure mode the test exists to catch.
    """

    def test_frontmatter_parses_as_yaml(
        self,
        style_template_frontmatter: dict,
    ) -> None:
        """The frontmatter must be a non-empty mapping."""
        assert isinstance(style_template_frontmatter, dict), (
            "Style template frontmatter did not parse as a YAML mapping. "
            "Check the `---` delimiters and the YAML body shape."
        )
        assert style_template_frontmatter, (
            "Style template frontmatter is an empty mapping. The "
            "`paths:` key is required for auto-load to fire."
        )

    def test_paths_key_present(
        self,
        style_template_frontmatter: dict,
    ) -> None:
        assert "paths" in style_template_frontmatter, (
            "Style template frontmatter is missing the `paths:` key. "
            "Without it, Claude Code does not auto-load the rule on "
            "any path, and the steering never fires."
        )

    def test_paths_value_is_list(
        self,
        style_template_frontmatter: dict,
    ) -> None:
        paths_value = style_template_frontmatter["paths"]
        assert isinstance(paths_value, list), (
            f"`paths:` value must be a YAML list; got "
            f"{type(paths_value).__name__}. Other rule templates use "
            "either inline (`['x']`) or block (`- 'x'`) list syntax; "
            "both parse as Python lists."
        )

    @pytest.mark.parametrize(
        "expected_glob",
        EXPECTED_PATHS_GLOBS,
        ids=EXPECTED_PATHS_GLOBS,
    )
    def test_expected_glob_present(
        self,
        style_template_frontmatter: dict,
        expected_glob: str,
    ) -> None:
        """Each documented glob from ADR-0021 is in the `paths:` list.

        Parametrized so a single missing glob produces a single named
        failure rather than a list-equality diff.
        """
        paths_value = style_template_frontmatter["paths"]
        assert expected_glob in paths_value, (
            f"Expected `paths:` glob not found: {expected_glob!r}. "
            "ADR-0021 lists this directory as a content-bearing surface "
            "where the style guide should auto-load. A deleted glob "
            "silently disables steering for whichever artifacts live "
            f"under that directory. Current `paths:`: {paths_value}."
        )

    def test_no_unexpected_globs(
        self,
        style_template_frontmatter: dict,
    ) -> None:
        """Deliberate additions to the glob set go through code review.

        Catches the inverse failure mode: a glob added without an ADR
        amendment. The GM is free to extend their own campaign copy;
        the *template* stays at the documented eleven-glob set.
        """
        paths_value = set(style_template_frontmatter["paths"])
        unexpected = paths_value - set(EXPECTED_PATHS_GLOBS)
        assert not unexpected, (
            f"Style template ships globs not documented in ADR-0021: "
            f"{sorted(unexpected)}. Adding a glob to the template stub "
            "is a deliberate domain expansion — update ADR-0021's "
            "documented glob set and this test together."
        )


# --------------------------------------------------------------------------
# Body invariants.
# --------------------------------------------------------------------------


class TestStubBody:
    """The stub's body carries the GM-authored contract and placeholder shape."""

    def test_h1_heading_present(self, style_template_raw: str) -> None:
        """The stub leads with a single `# Writing style and voice` heading."""
        assert "# Writing style and voice" in style_template_raw, (
            "Style template is missing the documented H1 heading "
            "`# Writing style and voice`. The heading is the file's "
            "self-identification when the GM opens it cold."
        )

    @pytest.mark.parametrize(
        "contract_substring",
        CONTRACT_PROSE_SUBSTRINGS,
        ids=CONTRACT_PROSE_SUBSTRINGS,
    )
    def test_contract_prose_present(
        self,
        style_template_raw: str,
        contract_substring: str,
    ) -> None:
        """The GM-authored-not-agent-written contract is stated in prose.

        Per ADR-0021, the prose contract is the *primary* mechanism;
        the deny block is the interlock. The two work together — but
        the prose is what the GM reads when they open the file, and
        what tells the agent the file is read-only-for-it.
        """
        assert contract_substring in style_template_raw, (
            f"Style template prose is missing contract substring "
            f"{contract_substring!r}. The GM-authored contract is the "
            "primary mechanism per ADR-0021 — removing it silently "
            "leaves only the permission-matcher backstop, and the GM "
            "no longer sees the contract when opening the file."
        )

    @pytest.mark.parametrize(
        "section_heading",
        EXPECTED_SECTION_HEADINGS,
        ids=EXPECTED_SECTION_HEADINGS,
    )
    def test_placeholder_section_present(
        self,
        style_template_raw: str,
        section_heading: str,
    ) -> None:
        """Each documented placeholder section heading appears verbatim."""
        assert section_heading in style_template_raw, (
            f"Style template is missing placeholder section heading "
            f"{section_heading!r}. ADR-0021 names this category as one "
            "the stub surfaces by default. Renaming or dropping it is "
            "a deliberate template change — update the ADR and this "
            "test together."
        )

    def test_line_count_within_budget(self, style_template_raw: str) -> None:
        """Stub line count falls within ADR-0021's documented budget."""
        line_count = len(style_template_raw.splitlines())
        assert LINE_COUNT_MIN <= line_count <= LINE_COUNT_MAX, (
            f"Style template line count ({line_count}) is outside the "
            f"documented budget [{LINE_COUNT_MIN}, {LINE_COUNT_MAX}]. "
            "Per ADR-0021, the stub rides into working context on "
            "every matching draft; bloat costs agent attention. If "
            "the stub legitimately needs to grow, widen the budget in "
            "ADR-0021 and this test."
        )

    def test_no_smart_quotes(self, style_template_raw: str) -> None:
        """Plugin convention: ASCII-only quotes across all templates.

        Mirrors the smart-quote check in `test_settings_template.py`.
        Smart quotes slip in via copy-paste from chat apps, docs, or
        wiki pages and produce hard-to-spot diffs in plain-text
        templates.
        """
        offenders = [ch for ch in SMART_QUOTE_CHARS if ch in style_template_raw]
        assert not offenders, (
            f"Style template contains smart-quote characters "
            f"({[hex(ord(c)) for c in offenders]}). Templates use "
            "ASCII-only quotes — smart quotes often slip in via "
            "copy-paste from chat apps."
        )

    def test_inline_example_blocks_present(
        self,
        style_template_raw: str,
    ) -> None:
        """Stub uses blockquote-shaped inline examples, not rule lists.

        Per ADR-0021's "Template content principles" item #1:
        prose-with-examples over rule lists. The marker is the
        blockquote prefix `> ` appearing repeatedly — at least one per
        placeholder section. Fewer than the section count suggests
        the prose-with-examples shape has eroded toward rule-list shape.
        """
        blockquote_lines = [
            line for line in style_template_raw.splitlines()
            if line.lstrip().startswith("> ")
        ]
        # One example per section is the minimum. Some sections may
        # have multi-line example blocks; the absolute floor is the
        # section count.
        min_expected = len(EXPECTED_SECTION_HEADINGS)
        assert len(blockquote_lines) >= min_expected, (
            f"Style template has only {len(blockquote_lines)} blockquote "
            f"lines (expected at least {min_expected} — one per "
            "placeholder section). Per ADR-0021, the stub uses "
            "prose-with-examples shape; fewer examples than sections "
            "suggests the prose-with-examples shape has eroded."
        )


# --------------------------------------------------------------------------
# Settings deny-block interlock.
# --------------------------------------------------------------------------


class TestSettingsDenyBlock:
    """The settings template's `permissions.deny` block enforces the contract.

    Per ADR-0021, the deny entries are the permission-matcher backstop
    behind the prose contract in the stub's header. Without them, the
    pre-approved `.claude/**` allow entries would let a sub-agent write
    to the style file unchecked.
    """

    def test_deny_block_present_in_raw_template(
        self,
        settings_template_raw_for_deny: str,
    ) -> None:
        """The raw template carries a `permissions.deny` array."""
        assert '"deny"' in settings_template_raw_for_deny, (
            "Settings template is missing the `permissions.deny` block. "
            "Per ADR-0021, the deny block is the permission-matcher "
            "interlock backing the style file's GM-authored contract."
        )

    @pytest.mark.parametrize(
        "deny_entry",
        EXPECTED_DENY_ENTRIES,
        ids=EXPECTED_DENY_ENTRIES,
    )
    def test_expected_deny_entry_present(
        self,
        settings_template_raw_for_deny: str,
        deny_entry: str,
    ) -> None:
        """Each expected deny entry appears verbatim in the raw template."""
        assert deny_entry in settings_template_raw_for_deny, (
            f"Settings template is missing expected deny entry "
            f"{deny_entry!r}. Per ADR-0021, all three of "
            "Edit / Write / MultiEdit must be denied against the "
            "style file path — denying only one or two lets the "
            "other tools through."
        )

    def test_deny_block_parses_after_substitution(
        self,
        templates_dir: Path,
        tmp_path: Path,
    ) -> None:
        """After `{{CAMPAIGN_PATH}}` substitution the JSON parses cleanly.

        Belt-and-suspenders companion to the raw-text checks above:
        confirms the deny block didn't break the JSON's overall
        structural validity (e.g., a missing comma between `allow` and
        `deny`).
        """
        campaign_path = (tmp_path / "campaign-under-test").resolve()
        template_text = (
            templates_dir / ".claude" / "settings.json.template"
        ).read_text(encoding="utf-8")
        substituted = template_text.replace(
            "{{CAMPAIGN_PATH}}", str(campaign_path)
        )
        data = json.loads(substituted)
        deny = data["permissions"]["deny"]
        for expected in EXPECTED_DENY_ENTRIES:
            resolved = expected.replace(
                "{{CAMPAIGN_PATH}}", str(campaign_path)
            )
            assert resolved in deny, (
                f"After substitution, deny entry {resolved!r} not in "
                f"`permissions.deny`. Current deny: {deny}."
            )
