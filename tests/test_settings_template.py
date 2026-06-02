"""Template-edit validation for `templates/.claude/settings.json.template`.

Companion to `test_ingest_scaffolding.py::TestSettingsJson`. Those tests
check what the scaffolder *did* (substitution landed, JSON parses,
`permissions.allow` is non-empty). This file checks the template's
*content* — specific entries must be present, every entry must match
the documented tool-call pattern shape, and the raw pre-substitution
file must be structurally sane.

Issue #52 traces three categories of silent-failure mistakes that the
existing scaffolder tests do not catch:

1. **Required-entry presence.** A careless edit deletes the
   `Edit(/{{CAMPAIGN_PATH}}/secrets/**)` line; the broader permissions
   array still passes the non-empty check, and the skill starts
   prompting on every Secret write. `TestRequiredEntriesPresent`
   asserts each known-canonical entry by exact post-substitution match.

2. **Pattern-shape errors.** A typo like
   `Read(~/.claude/skills/ttrpg-gm/**` (missing closing paren) is a
   valid JSON string but Claude Code's permission matcher silently
   ignores it — no warning, no prompt, no permission. Per #63 this
   exact failure mode took multiple sessions to diagnose.
   `TestPermissionPatternShape` enforces the regex
   `^[A-Z][a-zA-Z]+\\(.+\\)(?::\\*)?$` on every allow-list entry, with
   a regression test on a deliberately-malformed fixture.

3. **Pre-substitution structural sanity.** The template with
   `{{CAMPAIGN_PATH}}` placeholders is not valid JSON itself, but
   structural checks (balanced braces and brackets,
   trailing comma after each non-last array entry, no smart-quote
   unicode) catch mistakes before the substitution-then-parse step.
   `TestRawTemplateStructure` runs these against the real template and
   exercises each check against an in-memory malformed fixture.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest


# --------------------------------------------------------------------------
# Canonical required entries.
#
# Each tuple is the (tool, target) pair the scaffolded settings.json must
# carry. Generated as a flat list rather than per-directory groupings so
# pytest.mark.parametrize surfaces a separate failure per missing entry —
# a single deletion in the template produces a single, named failure.
# --------------------------------------------------------------------------


# Content directories whose contents the skills write to with Edit, Write,
# and MultiEdit. Derived from the template body — these are the directories
# that ship with the full triplet today.
CONTENT_DIRS_WITH_FULL_TRIPLET: tuple[str, ...] = (
    "npcs",
    "locations",
    "factions",
    "items",
    "threads",
    "consequences",
    "beats",
    "adventures",
    "sessions",
    "secrets",
)

# `.ttrpg-staging/` carries Edit + Write but not MultiEdit (the staging
# tables in SKILL.md reference single-write patterns; MultiEdit isn't
# invoked against staging today). Tracked separately so a future addition
# of MultiEdit there shows up as a deliberate edit to this list.
STAGING_DIR_TOOLS: tuple[str, ...] = ("Edit", "Write")

# Whole-file targets (single file, not `/**`) and their tool sets, matching
# the template body. `.gitignore` ships Edit + Write only; the other three
# ship the full triplet.
WHOLE_FILE_TARGETS_WITH_FULL_TRIPLET: tuple[str, ...] = (
    "campaign.md",
    "CLAUDE.md",
)

DOT_CLAUDE_GLOB_TOOLS: tuple[str, ...] = ("Edit", "Write", "MultiEdit")
GITIGNORE_TOOLS: tuple[str, ...] = ("Edit", "Write")

# Read-only Bash entries. These do not pass through `{{CAMPAIGN_PATH}}`
# substitution; they appear verbatim in both the raw template and the
# rendered settings.json.
REQUIRED_BASH_ENTRIES: tuple[str, ...] = (
    "Bash(git status)",
    "Bash(git diff:*)",
    "Bash(git log:*)",
)

# Plugin-install Read rule. Per issue #69, this uses
# `${CLAUDE_PLUGIN_ROOT}` (resolved at match time by Claude Code) rather
# than the prior pair of literal-`~` + `{{HOME}}`-substituted rules. The
# scaffolder writes this string verbatim — no substitution applies.
PLUGIN_INSTALL_READ_RULE: str = "Read(${CLAUDE_PLUGIN_ROOT}/**)"


def _build_expected_post_substitution_entries(
    *,
    campaign_path: Path,
) -> list[str]:
    """Build the canonical list of post-substitution allow entries.

    Mirrors the structure of the template body. Returned in template-order
    (Edit block, Write block, MultiEdit block, Read entry, Bash entries)
    so parametrized failures point at intuitive locations.
    """
    cp = str(campaign_path)
    entries: list[str] = []

    # Edit block.
    for directory in CONTENT_DIRS_WITH_FULL_TRIPLET:
        entries.append(f"Edit(/{cp}/{directory}/**)")
    entries.append(f"Edit(/{cp}/.ttrpg-staging/**)")
    for whole_file in WHOLE_FILE_TARGETS_WITH_FULL_TRIPLET:
        entries.append(f"Edit(/{cp}/{whole_file})")
    entries.append(f"Edit(/{cp}/.claude/**)")
    entries.append(f"Edit(/{cp}/.gitignore)")

    # Write block.
    for directory in CONTENT_DIRS_WITH_FULL_TRIPLET:
        entries.append(f"Write(/{cp}/{directory}/**)")
    entries.append(f"Write(/{cp}/.ttrpg-staging/**)")
    for whole_file in WHOLE_FILE_TARGETS_WITH_FULL_TRIPLET:
        entries.append(f"Write(/{cp}/{whole_file})")
    entries.append(f"Write(/{cp}/.claude/**)")
    entries.append(f"Write(/{cp}/.gitignore)")

    # MultiEdit block (no `.ttrpg-staging`, no `.gitignore`).
    for directory in CONTENT_DIRS_WITH_FULL_TRIPLET:
        entries.append(f"MultiEdit(/{cp}/{directory}/**)")
    for whole_file in WHOLE_FILE_TARGETS_WITH_FULL_TRIPLET:
        entries.append(f"MultiEdit(/{cp}/{whole_file})")
    entries.append(f"MultiEdit(/{cp}/.claude/**)")

    # Plugin-install Read rule. Per issue #69, the template ships a
    # single `Read(${CLAUDE_PLUGIN_ROOT}/**)` entry — Claude Code resolves
    # `${CLAUDE_PLUGIN_ROOT}` at match time, so no scaffolder-side path
    # substitution is needed (and the rule works for both local-development
    # and marketplace plugin install modes).
    entries.append(PLUGIN_INSTALL_READ_RULE)

    # Read-only Bash entries.
    entries.extend(REQUIRED_BASH_ENTRIES)

    return entries


# Module-level reference list for parametrize id generation. The values
# inside are template-shape only (with `{{CAMPAIGN_PATH}}` literal) so the
# parametrize ids stay machine-stable across CI hosts. The runtime test
# resolves the actual values against the scaffolded fixture's campaign
# path; the plugin-install Read rule is verbatim per #69 and needs no
# per-host substitution.
TEMPLATE_SHAPE_REQUIRED_ENTRIES: list[str] = (
    [f"Edit(/{{{{CAMPAIGN_PATH}}}}/{d}/**)" for d in CONTENT_DIRS_WITH_FULL_TRIPLET]
    + ["Edit(/{{CAMPAIGN_PATH}}/.ttrpg-staging/**)"]
    + [
        f"Edit(/{{{{CAMPAIGN_PATH}}}}/{f})"
        for f in WHOLE_FILE_TARGETS_WITH_FULL_TRIPLET
    ]
    + ["Edit(/{{CAMPAIGN_PATH}}/.claude/**)", "Edit(/{{CAMPAIGN_PATH}}/.gitignore)"]
    + [f"Write(/{{{{CAMPAIGN_PATH}}}}/{d}/**)" for d in CONTENT_DIRS_WITH_FULL_TRIPLET]
    + ["Write(/{{CAMPAIGN_PATH}}/.ttrpg-staging/**)"]
    + [
        f"Write(/{{{{CAMPAIGN_PATH}}}}/{f})"
        for f in WHOLE_FILE_TARGETS_WITH_FULL_TRIPLET
    ]
    + ["Write(/{{CAMPAIGN_PATH}}/.claude/**)", "Write(/{{CAMPAIGN_PATH}}/.gitignore)"]
    + [
        f"MultiEdit(/{{{{CAMPAIGN_PATH}}}}/{d}/**)"
        for d in CONTENT_DIRS_WITH_FULL_TRIPLET
    ]
    + [
        f"MultiEdit(/{{{{CAMPAIGN_PATH}}}}/{f})"
        for f in WHOLE_FILE_TARGETS_WITH_FULL_TRIPLET
    ]
    + ["MultiEdit(/{{CAMPAIGN_PATH}}/.claude/**)"]
    + [PLUGIN_INSTALL_READ_RULE]
    + list(REQUIRED_BASH_ENTRIES)
)


# Permission-pattern shape regex from issue #52: tool name (PascalCase),
# parens around at least one character, optional `:*` suffix. Catches:
#   - missing closing paren        (`Read(...**`)
#   - missing tool name            (`(...**)`)
#   - lowercase / wrong-case tool  (`read(...)`, `BASH(...)`)
#   - empty content                (`Read()`)
#   - bare `:*` without parens     (`Bash:*`)
PERMISSION_ENTRY_PATTERN: re.Pattern[str] = re.compile(
    r"^[A-Z][a-zA-Z]+\(.+\)(?::\*)?$"
)


# --------------------------------------------------------------------------
# Helpers shared across the structural-sanity checks below.
# --------------------------------------------------------------------------


SMART_QUOTE_CHARS: tuple[str, ...] = (
    "“",  # left double quotation mark
    "”",  # right double quotation mark
    "‘",  # left single quotation mark
    "’",  # right single quotation mark
)


def _strip_placeholders(text: str) -> str:
    """Remove `{{...}}` placeholder blocks so brace-counting works.

    The template uses `{{CAMPAIGN_PATH}}` as a substitution marker. The
    placeholder is a literal pair of `{`/`}` braces in the raw text and
    disappears after substitution. Stripping it before structural
    brace-counting keeps the check focused on the JSON structure itself.
    """
    return re.sub(r"\{\{[^{}]+\}\}", "", text)


def check_balanced_brackets(raw: str) -> list[str]:
    """Return a list of bracket-balance complaints; empty if balanced.

    Strips `{{...}}` placeholders first. The check is count-based, not
    nesting-aware — sufficient for catching the bulk-deletion or
    bulk-paste mistakes that a careless template edit introduces.
    """
    stripped = _strip_placeholders(raw)
    complaints: list[str] = []
    for open_char, close_char in (("{", "}"), ("[", "]")):
        opens = stripped.count(open_char)
        closes = stripped.count(close_char)
        if opens != closes:
            complaints.append(
                f"`{open_char}` count {opens} != `{close_char}` count {closes}"
            )
    return complaints


def check_no_smart_quotes(raw: str) -> list[str]:
    """Return a list of smart-quote complaints; empty if all-ASCII quotes."""
    found = [ch for ch in SMART_QUOTE_CHARS if ch in raw]
    if not found:
        return []
    names = {
        "“": "U+201C left double quotation mark",
        "”": "U+201D right double quotation mark",
        "‘": "U+2018 left single quotation mark",
        "’": "U+2019 right single quotation mark",
    }
    return [f"contains smart-quote: {names[ch]}" for ch in found]


def check_allow_array_comma_discipline(raw: str) -> list[str]:
    """Return a list of comma-discipline complaints; empty if all good.

    Scans the `permissions.allow` array. Every entry line (a `"..."`
    string literal) must end with `,` except the last one, which must
    end without a comma. Lines that are not entry strings (the opening
    `[`, the closing `]`, blank lines, comments) are skipped.

    Catches:
      - trailing comma on the last entry (invalid JSON, but the parser
        error in CI is several layers downstream — surfacing it as a
        comma-discipline complaint points the maintainer at the right
        line).
      - missing comma on a non-last entry (would silently concatenate
        strings or trip the JSON parser, depending on whitespace).
    """
    lines = raw.splitlines()
    # Locate the `"allow": [` line and the matching `]` line. The close
    # may end with a trailing `,` when a sibling key (e.g.
    # `"deny": [...]` per ADR-0021) follows the allow array in the same
    # object — accept both `]` and `],` as end markers.
    start_idx: int | None = None
    end_idx: int | None = None
    for idx, line in enumerate(lines):
        if start_idx is None and '"allow"' in line and line.rstrip().endswith("["):
            start_idx = idx
            continue
        if start_idx is not None and line.strip() in ("]", "],"):
            end_idx = idx
            break

    if start_idx is None or end_idx is None:
        return ["could not locate `permissions.allow` array bounds"]

    # Entry lines: the strings between `[` and `]`. Filter to lines that
    # look like a string literal (starts with `"` after whitespace).
    entry_indices: list[int] = []
    for idx in range(start_idx + 1, end_idx):
        if lines[idx].lstrip().startswith('"'):
            entry_indices.append(idx)

    if not entry_indices:
        return ["`permissions.allow` array contains no entry lines"]

    complaints: list[str] = []
    for position, idx in enumerate(entry_indices):
        is_last = position == len(entry_indices) - 1
        stripped = lines[idx].rstrip()
        has_trailing_comma = stripped.endswith(",")
        if is_last and has_trailing_comma:
            complaints.append(
                f"line {idx + 1}: last `allow` entry has trailing comma "
                f"(JSON disallows): {stripped!r}"
            )
        if not is_last and not has_trailing_comma:
            complaints.append(
                f"line {idx + 1}: non-last `allow` entry missing trailing "
                f"comma: {stripped!r}"
            )
    return complaints


# --------------------------------------------------------------------------
# Fixtures.
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def settings_template_path(templates_dir: Path) -> Path:
    """Absolute path to the raw `settings.json.template` file."""
    return templates_dir / ".claude" / "settings.json.template"


@pytest.fixture(scope="module")
def settings_template_raw(settings_template_path: Path) -> str:
    """Pre-substitution template file contents, read once per module."""
    return settings_template_path.read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# Required-entry presence — scaffolder-fixture based.
#
# The `scaffolded_campaign` fixture is defined in test_ingest_scaffolding.py.
# pytest discovers it via conftest auto-import once both files run in the
# same session. We re-host it as a thin local fixture here to keep this
# file self-sufficient and avoid an implicit cross-file dependency.
# --------------------------------------------------------------------------


@pytest.fixture
def scaffolded_settings(tmp_path: Path, templates_dir: Path) -> dict:
    """Render the settings template with realistic substitutions.

    Mirrors the reference scaffolder's substitution map (post-#69, that's
    just `{{CAMPAIGN_PATH}}`). The campaign path is a `tmp_path`
    subdirectory so the value is a real absolute path the test can also
    compare against.
    """
    campaign_path = (tmp_path / "campaign-under-test").resolve()
    campaign_path.mkdir(parents=True, exist_ok=True)

    template_text = (
        templates_dir / ".claude" / "settings.json.template"
    ).read_text(encoding="utf-8")
    substituted = template_text.replace("{{CAMPAIGN_PATH}}", str(campaign_path))
    return {
        "data": json.loads(substituted),
        "campaign_path": campaign_path,
    }


class TestRequiredEntriesPresent:
    """Each known-canonical `permissions.allow` entry is present.

    Parametrized over the template-shape entry list. Each entry is its
    own test case so a single deletion in the template produces a single
    named failure (e.g., `test_entry_present[...]` for the missing line)
    rather than a single batched failure pointing at the whole array.
    """

    @pytest.mark.parametrize(
        "template_shape_entry",
        TEMPLATE_SHAPE_REQUIRED_ENTRIES,
        ids=TEMPLATE_SHAPE_REQUIRED_ENTRIES,
    )
    def test_entry_present(
        self,
        scaffolded_settings: dict,
        template_shape_entry: str,
    ) -> None:
        """Assert the substituted form of each entry is in `permissions.allow`."""
        expected = template_shape_entry.replace(
            "{{CAMPAIGN_PATH}}", str(scaffolded_settings["campaign_path"])
        )
        allow = scaffolded_settings["data"]["permissions"]["allow"]
        assert expected in allow, (
            f"Expected `permissions.allow` entry not found after "
            f"substitution: {expected!r}. Template-shape: "
            f"{template_shape_entry!r}. A line was likely deleted from "
            f"`templates/.claude/settings.json.template`; the skills "
            "that depend on this permission will silently start "
            "prompting the GM at runtime."
        )

    def test_all_canonical_entries_resolve(
        self,
        scaffolded_settings: dict,
    ) -> None:
        """Sanity: the canonical entry-builder produces a subset of the array.

        Belt-and-suspenders companion to the parametrized check: confirms
        the entire computed required-set lives in `permissions.allow` in
        one assertion, so a refactor that drops the parametrization
        wholesale still surfaces missing entries.
        """
        expected = _build_expected_post_substitution_entries(
            campaign_path=scaffolded_settings["campaign_path"],
        )
        allow = set(scaffolded_settings["data"]["permissions"]["allow"])
        missing = [e for e in expected if e not in allow]
        assert not missing, (
            f"Canonical required entries missing from `permissions.allow`: "
            f"{missing}. Template likely had a line removed without a "
            "matching update here; verify by diff against "
            "`templates/.claude/settings.json.template`."
        )


class TestPermissionPatternShape:
    """Every `permissions.allow` entry matches the tool-call regex.

    Catches the silent-failure mode #63 spent a session diagnosing: a
    permission string like `Read(~/.claude/skills/ttrpg-gm/**` (missing
    the closing paren) is valid JSON, so the existing
    `test_settings_is_valid_json` test passes — but Claude Code's
    permission matcher silently rejects the string, and the rule does
    nothing.
    """

    def test_every_allow_entry_matches_pattern(
        self,
        scaffolded_settings: dict,
    ) -> None:
        allow = scaffolded_settings["data"]["permissions"]["allow"]
        offenders = [
            entry for entry in allow if not PERMISSION_ENTRY_PATTERN.match(entry)
        ]
        assert not offenders, (
            f"`permissions.allow` entries do not match the documented "
            f"tool-call shape `^[A-Z][a-zA-Z]+\\(.+\\)(?::\\*)?$`: "
            f"{offenders}. Claude Code's permission matcher silently "
            "ignores malformed entries — the rule is dead code. "
            "Common cause: missing closing paren after a glob."
        )

    @pytest.mark.parametrize(
        "good_entry",
        [
            "Edit(/abs/path/npcs/**)",
            "Read(~/.claude/skills/ttrpg-gm/**)",
            "Bash(git status)",
            "Bash(git diff:*)",
            "MultiEdit(/abs/path/campaign.md)",
        ],
    )
    def test_pattern_accepts_well_formed(self, good_entry: str) -> None:
        """Regression check: the regex accepts representative real entries."""
        assert PERMISSION_ENTRY_PATTERN.match(good_entry), (
            f"Pattern rejected a well-formed entry the template ships: "
            f"{good_entry!r}. The regex is too strict."
        )

    @pytest.mark.parametrize(
        "bad_entry,why",
        [
            ("Read(~/.claude/skills/ttrpg-gm/**", "missing closing paren"),
            ("read(/abs/path/npcs/**)", "lowercase tool name"),
            ("Edit()", "empty content"),
            ("(/abs/path/**)", "no tool name"),
            ("Bash:*", "no parens at all"),
            ("Read(~/.claude/skills/ttrpg-gm/**):", "trailing colon without star"),
        ],
    )
    def test_pattern_rejects_malformed(
        self,
        bad_entry: str,
        why: str,
    ) -> None:
        """Regression check: the regex rejects the documented bad shapes.

        Without these cases, a future "simplification" of the regex
        could accidentally let through the exact strings #63 was
        investigating — and CI would still go green.
        """
        assert not PERMISSION_ENTRY_PATTERN.match(bad_entry), (
            f"Pattern accepted a malformed entry ({why}): {bad_entry!r}. "
            f"The regex is too loose — the silent-failure mode from "
            "issue #63 would still ship."
        )


class TestRawTemplateStructure:
    """Pre-substitution structural sanity on the raw template file.

    These checks run against the literal text on disk, before any
    placeholder substitution. They catch mistakes earlier than the
    substitution-then-parse pipeline does, with line-specific complaints
    where possible.
    """

    def test_brackets_balanced(
        self,
        settings_template_raw: str,
    ) -> None:
        complaints = check_balanced_brackets(settings_template_raw)
        assert not complaints, (
            f"Raw template has unbalanced brackets after stripping "
            f"`{{{{...}}}}` placeholders: {complaints}. A `{{`/`[` was "
            "added or removed without a matching closer; the substituted "
            "file would fail to parse as JSON."
        )

    def test_no_smart_quotes(
        self,
        settings_template_raw: str,
    ) -> None:
        complaints = check_no_smart_quotes(settings_template_raw)
        assert not complaints, (
            f"Raw template contains smart-quote characters: {complaints}. "
            "JSON only accepts ASCII `\"`; smart quotes often slip in via "
            "copy-paste from chat apps, docs, or wiki pages."
        )

    def test_allow_array_comma_discipline(
        self,
        settings_template_raw: str,
    ) -> None:
        complaints = check_allow_array_comma_discipline(settings_template_raw)
        assert not complaints, (
            f"Raw template has comma-discipline problems in "
            f"`permissions.allow`: {complaints}. Every entry must end "
            "with `,` except the last."
        )

    # ----------------------------------------------------------------------
    # Regression fixtures for each structural check.
    #
    # In-memory malformed strings, not edits to the real template. They
    # confirm each check's *detector* works — i.e., that the test would
    # actually catch the failure mode it claims to catch.
    # ----------------------------------------------------------------------

    def test_brackets_detector_catches_missing_close_brace(self) -> None:
        broken = '{\n  "permissions": {\n    "allow": [\n      "Edit(x)"\n    ]\n  \n}\n'
        # One `{` opens permissions but its matching `}` is missing — the
        # outer `}` is the only close. So opens=2, closes=1.
        complaints = check_balanced_brackets(broken)
        assert complaints, (
            "Bracket detector did not flag a missing `}`. The detector "
            "is too lenient — real malformed templates would pass."
        )

    def test_brackets_detector_catches_missing_close_bracket(self) -> None:
        broken = '{\n  "permissions": {\n    "allow": [\n      "Edit(x)"\n  }\n}\n'
        complaints = check_balanced_brackets(broken)
        assert complaints, "Bracket detector did not flag a missing `]`."

    def test_brackets_detector_ignores_placeholder_braces(self) -> None:
        # `{{CAMPAIGN_PATH}}` is a literal pair of `{`/`}` in the raw
        # text. The detector must strip the placeholder before counting,
        # otherwise it would false-positive on every well-formed template.
        # An in-memory `{{EXAMPLE}}` placeholder exercises the same code
        # path — the detector strips any `{{...}}` block.
        well_formed = (
            '{\n  "permissions": {\n    "allow": [\n      '
            '"Edit(/{{CAMPAIGN_PATH}}/npcs/**)",\n      '
            '"Read(/{{EXAMPLE}}/path/**)"\n    ]\n  }\n}\n'
        )
        complaints = check_balanced_brackets(well_formed)
        assert not complaints, (
            f"Bracket detector false-positives on `{{{{...}}}}` placeholder "
            f"braces: {complaints}. The detector must strip placeholders "
            "before counting."
        )

    @pytest.mark.parametrize("smart_quote", SMART_QUOTE_CHARS)
    def test_smart_quote_detector_catches_each_variant(
        self,
        smart_quote: str,
    ) -> None:
        broken = (
            '{\n  "permissions": {\n    "allow": [\n      '
            + smart_quote
            + "Edit(x)"
            + smart_quote
            + '\n    ]\n  }\n}\n'
        )
        complaints = check_no_smart_quotes(broken)
        assert complaints, (
            f"Smart-quote detector did not flag U+{ord(smart_quote):04X}."
        )

    def test_comma_detector_catches_trailing_comma_on_last_entry(self) -> None:
        broken = (
            '{\n  "permissions": {\n    "allow": [\n      '
            '"Edit(x)",\n      "Write(y)",\n    ]\n  }\n}\n'
        )
        complaints = check_allow_array_comma_discipline(broken)
        assert complaints, (
            "Comma detector did not flag a trailing comma on the last "
            "entry. JSON would reject this template at parse time, but "
            "the detector is supposed to surface a more pointed message."
        )

    def test_comma_detector_catches_missing_comma_on_nonlast_entry(self) -> None:
        broken = (
            '{\n  "permissions": {\n    "allow": [\n      '
            '"Edit(x)"\n      "Write(y)"\n    ]\n  }\n}\n'
        )
        complaints = check_allow_array_comma_discipline(broken)
        assert complaints, (
            "Comma detector did not flag a missing comma on a non-last "
            "entry. This is the most common copy-paste-edit mistake — "
            "the detector must surface it."
        )

    def test_comma_detector_passes_well_formed_array(self) -> None:
        good = (
            '{\n  "permissions": {\n    "allow": [\n      '
            '"Edit(x)",\n      "Write(y)",\n      "Read(z)"\n    ]\n  }\n}\n'
        )
        complaints = check_allow_array_comma_discipline(good)
        assert not complaints, (
            f"Comma detector false-positives on a well-formed array: "
            f"{complaints}."
        )
