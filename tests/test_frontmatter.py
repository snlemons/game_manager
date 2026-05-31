"""Frontmatter shape + per-kind schema tests.

This file follows the v0.1 test convention: the reference Python below
is a thin near-translation of the schema spec in
`references/frontmatter-schemas.md`, used by the tests to verify the
spec the LLM-driven skills are supposed to honor. The skills do the
actual runtime validation in SKILL.md prose — this test file does not
ship a runtime helper.

(An earlier scope draft promoted this logic into a `lib/frontmatter.py`
runtime helper invoked from skills. That was rolled back; the helper
convention is deferred to a future version. The schema tests are kept
here as standalone spec coverage that didn't exist in v0.1.)
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Tuple

import pytest
import yaml


# --------------------------------------------------------------------------
# Reference implementation — mirrors references/frontmatter-schemas.md.
# Kept in-file per the v0.1 convention (see test_ingest_scaffolding.py and
# test_wrap_session_idempotency.py for the same pattern).
# --------------------------------------------------------------------------


# Per-kind enums, sourced from references/frontmatter-schemas.md.
ADVENTURE_STATUSES = frozenset({"introduced", "active", "completed", "abandoned"})
THREAD_STATUSES = frozenset({"open", "closed", "decayed"})
BEAT_STATUSES = frozenset({"pending", "delivered", "dropped"})


class FrontmatterError(Exception):
    """A validation failure surfaced with a self-contained message."""


def split_frontmatter(text: str) -> Tuple[dict, str]:
    """Split a markdown doc into (parsed-YAML-frontmatter, body).

    Raises `FrontmatterError` if the doc has no `---\\n...\\n---\\n`
    block, if the YAML fails to parse, or if the parsed value is not a
    mapping.
    """
    if not text.startswith("---\n"):
        raise FrontmatterError(
            "file does not open with a YAML frontmatter block "
            "(`---` line); the plugin's templates always lead with "
            "frontmatter."
        )
    closing = text.find("\n---\n", 4)
    if closing == -1:
        # Tolerate a doc whose final line is the closing `---` without a
        # trailing newline.
        if text.endswith("\n---"):
            closing = len(text) - len("\n---")
            raw = text[4:closing]
            body = ""
        else:
            raise FrontmatterError(
                "frontmatter block is unterminated (no closing `---` "
                "line found)."
            )
    else:
        raw = text[4:closing]
        body = text[closing + len("\n---\n") :]

    try:
        parsed = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise FrontmatterError(f"frontmatter YAML failed to parse: {exc}")

    if parsed is None:
        parsed = {}
    if not isinstance(parsed, dict):
        raise FrontmatterError(
            f"frontmatter parsed to {type(parsed).__name__}, expected a "
            "mapping (YAML object)."
        )
    return parsed, body


def classify_path(campaign_root: Path, file_path: Path) -> str:
    """Return the schema kind to apply based on path relative to root.

    Returns one of `"adventure"`, `"thread"`, `"consequence"`, `"beat"`,
    `"rule"`, or `"unspecified"`. Paths outside the campaign root or
    that don't match any of the lifecycle-object / rule conventions
    fall through to `"unspecified"`.
    """
    try:
        rel = file_path.resolve().relative_to(campaign_root.resolve())
    except ValueError:
        return "unspecified"

    parts = rel.parts
    if not parts:
        return "unspecified"

    head = parts[0]
    if head == "adventures" and rel.name == "adventure.md":
        return "adventure"
    if head == "threads" and rel.name.endswith(".md"):
        return "thread"
    if head == "consequences" and rel.name.endswith(".md"):
        return "consequence"
    if head == "beats" and rel.name.endswith(".md"):
        return "beat"
    if (
        len(parts) >= 3
        and parts[0] == ".claude"
        and parts[1] == "rules"
        and rel.name.endswith(".md")
    ):
        return "rule"
    return "unspecified"


def validate_schema(schema: str, frontmatter: dict, body: str) -> None:
    """Apply per-kind constraints. Raise `FrontmatterError` on violation."""
    if schema == "adventure":
        _require_status_enum(frontmatter, "status", ADVENTURE_STATUSES)
    elif schema == "thread":
        _require_status_enum(frontmatter, "status", THREAD_STATUSES)
    elif schema == "consequence":
        if "status" in frontmatter:
            raise FrontmatterError(
                "Consequence files must not carry a `status` field — "
                "Consequences are persistent world facts (no lifecycle)."
            )
    elif schema == "beat":
        _require_status_enum(frontmatter, "status", BEAT_STATUSES)
    elif schema == "rule":
        if "paths" not in frontmatter:
            raise FrontmatterError(
                "rule file frontmatter is missing required `paths:` "
                "scope list."
            )
        paths = frontmatter["paths"]
        if not isinstance(paths, list) or not paths:
            raise FrontmatterError(
                "rule file `paths:` must be a non-empty list of glob "
                "patterns."
            )
        if not body.strip():
            raise FrontmatterError(
                "rule file body is empty; the rule has no instructions "
                "to scope."
            )


def _require_status_enum(
    frontmatter: dict,
    key: str,
    allowed: frozenset,
) -> None:
    if key not in frontmatter:
        raise FrontmatterError(
            f"required field `{key}:` missing from frontmatter."
        )
    value = frontmatter[key]
    if value not in allowed:
        raise FrontmatterError(
            f"`{key}: {value!r}` is not in the allowed enum "
            f"{sorted(allowed)}."
        )


def validate_file(campaign_root: Path, file_path: Path) -> dict:
    """Read, parse, validate. Return the structured result on success."""
    if not file_path.is_file():
        raise FrontmatterError(f"file not found: {file_path}")

    text = file_path.read_text(encoding="utf-8")

    try:
        frontmatter, body = split_frontmatter(text)
    except FrontmatterError as exc:
        raise FrontmatterError(f"{file_path}: {exc}") from None

    schema = classify_path(campaign_root, file_path)

    try:
        validate_schema(schema, frontmatter, body)
    except FrontmatterError as exc:
        raise FrontmatterError(f"{file_path}: {exc}") from None

    return {
        "path": str(file_path.resolve()),
        "schema": schema,
        "frontmatter": frontmatter,
        "body": body,
    }


# --------------------------------------------------------------------------
# Test fixture helper.
# --------------------------------------------------------------------------


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text), encoding="utf-8")
    return path


# --------------------------------------------------------------------------
# Shape-level validation (applies to every file kind).
# --------------------------------------------------------------------------


class TestShapeValidation:
    """Frontmatter shape rules independent of per-kind schema."""

    def test_missing_frontmatter_raises(self) -> None:
        with pytest.raises(FrontmatterError) as exc:
            split_frontmatter("# Hello\n\nNo frontmatter.\n")
        assert "frontmatter" in str(exc.value).lower()

    def test_unterminated_frontmatter_raises(self) -> None:
        with pytest.raises(FrontmatterError):
            split_frontmatter("---\npaths: [foo]\n\n# Body\n")

    def test_malformed_yaml_raises(self) -> None:
        with pytest.raises(FrontmatterError) as exc:
            split_frontmatter("---\npaths: [unclosed\n---\n\nBody\n")
        assert "parse" in str(exc.value).lower()

    def test_non_mapping_yaml_raises(self) -> None:
        with pytest.raises(FrontmatterError) as exc:
            split_frontmatter("---\n- one\n- two\n---\n\nBody\n")
        assert "mapping" in str(exc.value).lower()

    def test_well_formed_returns_dict_and_body(self) -> None:
        fm, body = split_frontmatter(
            "---\nstatus: open\n---\n\n# Hook\n\nThe party promised something.\n"
        )
        assert fm == {"status": "open"}
        assert body.startswith("\n# Hook")


# --------------------------------------------------------------------------
# Path-based schema dispatch.
# --------------------------------------------------------------------------


class TestSchemaDispatch:
    """`classify_path` routes files to the right per-kind validator."""

    @pytest.mark.parametrize(
        ("rel_path", "expected_schema"),
        [
            ("adventures/lost-mines/adventure.md", "adventure"),
            ("threads/find-rulfs-killer.md", "thread"),
            ("consequences/temple-burned.md", "consequence"),
            ("beats/dream-of-the-veiled-court.md", "beat"),
            (".claude/rules/sessions.md", "rule"),
            (".claude/rules/adventures.md", "rule"),
            ("npcs/sera.md", "unspecified"),
            ("locations/phandalin.md", "unspecified"),
            ("campaign.md", "unspecified"),
            # Subordinate Adventure files (not the canonical
            # `adventure.md`) are not lifecycle objects per the
            # references/frontmatter-schemas.md file convention.
            ("adventures/lost-mines/scene-1.md", "unspecified"),
        ],
    )
    def test_classify_path(
        self, tmp_path: Path, rel_path: str, expected_schema: str
    ) -> None:
        target = tmp_path / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("---\n---\n\nplaceholder\n", encoding="utf-8")
        assert classify_path(tmp_path, target) == expected_schema


# --------------------------------------------------------------------------
# Per-kind constraints (the constants come from
# references/frontmatter-schemas.md).
# --------------------------------------------------------------------------


class TestAdventureSchema:
    @pytest.mark.parametrize("status", sorted(ADVENTURE_STATUSES))
    def test_valid_status_accepted(self, tmp_path: Path, status: str) -> None:
        adv = _write(
            tmp_path / "adventures" / "lost-mines" / "adventure.md",
            f"""\
            ---
            status: {status}
            order: ~
            ---

            # Lost Mines
            """,
        )
        result = validate_file(tmp_path, adv)
        assert result["schema"] == "adventure"
        assert result["frontmatter"]["status"] == status

    def test_missing_status_rejected(self, tmp_path: Path) -> None:
        adv = _write(
            tmp_path / "adventures" / "lost-mines" / "adventure.md",
            """\
            ---
            order: 1
            ---

            # Lost Mines
            """,
        )
        with pytest.raises(FrontmatterError):
            validate_file(tmp_path, adv)

    def test_invalid_status_rejected(self, tmp_path: Path) -> None:
        adv = _write(
            tmp_path / "adventures" / "lost-mines" / "adventure.md",
            """\
            ---
            status: paused
            ---

            # Lost Mines
            """,
        )
        with pytest.raises(FrontmatterError) as exc:
            validate_file(tmp_path, adv)
        assert "paused" in str(exc.value)


class TestThreadSchema:
    @pytest.mark.parametrize("status", sorted(THREAD_STATUSES))
    def test_valid_status_accepted(self, tmp_path: Path, status: str) -> None:
        thr = _write(
            tmp_path / "threads" / "find-rulfs-killer.md",
            f"""\
            ---
            status: {status}
            ---

            # Find Rulf's killer
            """,
        )
        result = validate_file(tmp_path, thr)
        assert result["schema"] == "thread"

    def test_invalid_status_rejected(self, tmp_path: Path) -> None:
        thr = _write(
            tmp_path / "threads" / "find-rulfs-killer.md",
            """\
            ---
            status: pending
            ---

            # Find Rulf's killer
            """,
        )
        with pytest.raises(FrontmatterError):
            validate_file(tmp_path, thr)


class TestConsequenceSchema:
    def test_status_field_rejected(self, tmp_path: Path) -> None:
        # Consequences are world facts; they have no lifecycle status.
        cons = _write(
            tmp_path / "consequences" / "temple-burned.md",
            """\
            ---
            status: closed
            created: ~
            ---

            # The temple burned.
            """,
        )
        with pytest.raises(FrontmatterError) as exc:
            validate_file(tmp_path, cons)
        assert "status" in str(exc.value)

    def test_consequence_without_status_accepted(self, tmp_path: Path) -> None:
        cons = _write(
            tmp_path / "consequences" / "temple-burned.md",
            """\
            ---
            created: ~
            ---

            # The temple burned.
            """,
        )
        result = validate_file(tmp_path, cons)
        assert result["schema"] == "consequence"


class TestBeatSchema:
    @pytest.mark.parametrize("status", sorted(BEAT_STATUSES))
    def test_valid_status_accepted(self, tmp_path: Path, status: str) -> None:
        beat = _write(
            tmp_path / "beats" / "dream.md",
            f"""\
            ---
            status: {status}
            created: ~
            ---

            # A dream.
            """,
        )
        result = validate_file(tmp_path, beat)
        assert result["schema"] == "beat"


class TestRuleSchema:
    def test_valid_rule_file_accepted(self, tmp_path: Path) -> None:
        rule = _write(
            tmp_path / ".claude" / "rules" / "sessions.md",
            """\
            ---
            paths: ["sessions/**/*.md"]
            ---

            # Session conventions

            Body text describing the conventions.
            """,
        )
        result = validate_file(tmp_path, rule)
        assert result["schema"] == "rule"
        assert result["frontmatter"]["paths"] == ["sessions/**/*.md"]

    def test_missing_paths_rejected(self, tmp_path: Path) -> None:
        rule = _write(
            tmp_path / ".claude" / "rules" / "sessions.md",
            """\
            ---
            description: missing paths
            ---

            # Body
            """,
        )
        with pytest.raises(FrontmatterError) as exc:
            validate_file(tmp_path, rule)
        assert "paths" in str(exc.value)

    def test_empty_paths_rejected(self, tmp_path: Path) -> None:
        rule = _write(
            tmp_path / ".claude" / "rules" / "sessions.md",
            """\
            ---
            paths: []
            ---

            # Body
            """,
        )
        with pytest.raises(FrontmatterError):
            validate_file(tmp_path, rule)

    def test_empty_body_rejected(self, tmp_path: Path) -> None:
        rule = _write(
            tmp_path / ".claude" / "rules" / "sessions.md",
            """\
            ---
            paths: ["foo/**"]
            ---

            """,
        )
        with pytest.raises(FrontmatterError):
            validate_file(tmp_path, rule)
