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
        _validate_beat_optional_fields(frontmatter)
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


def _validate_beat_optional_fields(frontmatter: dict) -> None:
    """Shape-check the two optional Beat-only fields added in slice 3.

    - `kind:` is an **open enum** — when present it must be a string
      (starter values `news | handout | character-moment | set-piece |
      clue | escalation`), but any string value is accepted so new
      kinds can be introduced without a schema change. Absence is fine
      (unclassified Beat).
    - `linked_secrets:` when present must be a list of strings (Secret
      slugs). Absence and `[]` are both fine.
    """
    if "kind" in frontmatter:
        value = frontmatter["kind"]
        # YAML `~` parses to None — treat as "unclassified", same as
        # an absent key. Otherwise the value must be a string.
        if value is not None and not isinstance(value, str):
            raise FrontmatterError(
                f"Beat `kind:` must be a string (open enum) or null; "
                f"got {type(value).__name__}."
            )
    if "linked_secrets" in frontmatter:
        value = frontmatter["linked_secrets"]
        if not isinstance(value, list):
            raise FrontmatterError(
                f"Beat `linked_secrets:` must be a list of Secret "
                f"slugs; got {type(value).__name__}."
            )
        for item in value:
            if not isinstance(item, str):
                raise FrontmatterError(
                    f"Beat `linked_secrets:` entries must be strings "
                    f"(Secret slugs); got {type(item).__name__}."
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

    # ----- `kind:` open-enum + `linked_secrets:` — slice 3 (#35) -----

    def test_beat_without_kind_or_linked_secrets_accepted(
        self, tmp_path: Path
    ) -> None:
        """Backward compat: v0.1 Beats with neither field still validate."""
        beat = _write(
            tmp_path / "beats" / "legacy.md",
            """\
            ---
            status: pending
            created: ~
            delivered: ~
            linked_pcs: []
            linked_npcs: []
            linked_adventures: []
            linked_locations: []
            ---

            # A v0.1-shaped Beat.
            """,
        )
        result = validate_file(tmp_path, beat)
        assert result["schema"] == "beat"
        assert "kind" not in result["frontmatter"]
        assert "linked_secrets" not in result["frontmatter"]

    @pytest.mark.parametrize(
        "kind",
        [
            # Starter values documented in references/frontmatter-schemas.md.
            "news",
            "handout",
            "character-moment",
            "set-piece",
            "clue",
            "escalation",
            # Open-enum: any string value passes — `gm-aside` is a
            # plausible future kind, but the test doesn't depend on it
            # ever being added.
            "gm-aside",
            "totally-made-up",
        ],
    )
    def test_beat_kind_open_enum_accepts_any_string(
        self, tmp_path: Path, kind: str
    ) -> None:
        beat = _write(
            tmp_path / "beats" / f"kind-{kind}.md",
            f"""\
            ---
            status: pending
            created: ~
            kind: {kind}
            ---

            # A classified Beat.
            """,
        )
        result = validate_file(tmp_path, beat)
        assert result["frontmatter"]["kind"] == kind

    def test_beat_kind_null_accepted(self, tmp_path: Path) -> None:
        """`kind: ~` (explicit null) means unclassified — accepted."""
        beat = _write(
            tmp_path / "beats" / "kind-null.md",
            """\
            ---
            status: pending
            created: ~
            kind: ~
            ---

            # Explicitly unclassified.
            """,
        )
        result = validate_file(tmp_path, beat)
        assert result["frontmatter"]["kind"] is None

    def test_beat_kind_non_string_rejected(self, tmp_path: Path) -> None:
        """`kind:` must be a string (or null); a list is a schema bug."""
        beat = _write(
            tmp_path / "beats" / "kind-list.md",
            """\
            ---
            status: pending
            created: ~
            kind: [clue, escalation]
            ---

            # `kind:` is single-valued.
            """,
        )
        with pytest.raises(FrontmatterError) as exc:
            validate_file(tmp_path, beat)
        assert "kind" in str(exc.value)

    def test_beat_with_linked_secrets_accepted(self, tmp_path: Path) -> None:
        beat = _write(
            tmp_path / "beats" / "clue-the-statue-weeps.md",
            """\
            ---
            status: pending
            created: ~
            kind: clue
            linked_secrets: [the-statue-is-alive, maren-is-the-spy]
            ---

            # The statue weeps when Maren walks past.
            """,
        )
        result = validate_file(tmp_path, beat)
        assert result["frontmatter"]["kind"] == "clue"
        assert result["frontmatter"]["linked_secrets"] == [
            "the-statue-is-alive",
            "maren-is-the-spy",
        ]

    def test_beat_with_empty_linked_secrets_accepted(
        self, tmp_path: Path
    ) -> None:
        """Empty list (key present, no entries) is honest and allowed."""
        beat = _write(
            tmp_path / "beats" / "no-secrets.md",
            """\
            ---
            status: pending
            created: ~
            linked_secrets: []
            ---

            # No Secret revealed.
            """,
        )
        result = validate_file(tmp_path, beat)
        assert result["frontmatter"]["linked_secrets"] == []

    def test_beat_linked_secrets_non_list_rejected(
        self, tmp_path: Path
    ) -> None:
        beat = _write(
            tmp_path / "beats" / "bad-linked-secrets.md",
            """\
            ---
            status: pending
            created: ~
            linked_secrets: the-statue-is-alive
            ---

            # Should have been a list.
            """,
        )
        with pytest.raises(FrontmatterError) as exc:
            validate_file(tmp_path, beat)
        assert "linked_secrets" in str(exc.value)

    def test_beat_linked_secrets_non_string_entry_rejected(
        self, tmp_path: Path
    ) -> None:
        beat = _write(
            tmp_path / "beats" / "bad-linked-secrets-entry.md",
            """\
            ---
            status: pending
            created: ~
            linked_secrets: [the-statue-is-alive, 42]
            ---

            # Entries must be slugs (strings).
            """,
        )
        with pytest.raises(FrontmatterError) as exc:
            validate_file(tmp_path, beat)
        assert "linked_secrets" in str(exc.value)

    def test_beat_kind_escalation_with_linked_secrets_roundtrips(
        self, tmp_path: Path
    ) -> None:
        """Acceptance-criteria fixture: `kind: escalation` + `linked_secrets`
        validate and round-trip through a second parse intact.
        """
        beat = _write(
            tmp_path / "beats" / "escalation.md",
            """\
            ---
            status: pending
            created: ~
            kind: escalation
            linked_secrets: [example-secret]
            ---

            # The cult moves on the temple this session.
            """,
        )
        result = validate_file(tmp_path, beat)
        assert result["frontmatter"]["kind"] == "escalation"
        assert result["frontmatter"]["linked_secrets"] == ["example-secret"]

        # Round-trip: re-validate via a second read to confirm the fields
        # survive a second parse (no in-place mutation, no lossy coercion).
        second = validate_file(tmp_path, beat)
        assert second["frontmatter"]["kind"] == "escalation"
        assert second["frontmatter"]["linked_secrets"] == ["example-secret"]


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


class TestPcStubShape:
    """`/ingest` Phase 2 PC stub file shape (ADR-0018 + #73).

    Per `~/.claude/skills/ttrpg-gm/references/frontmatter-schemas.md`'s
    "Worked example: PC stub" subsection and ADR-0018:

    - Files land at `pcs/<slug>.md`.
    - Frontmatter carries `kind: pc` explicitly.
    - `aliases:` is optional; when present, it's a list of strings.
    - Body is optional — an H1-only file (no prose body) is the agent
      default when the survey annotation wasn't enriched.

    Reference-note paths still classify as `"unspecified"` for path-
    based schema dispatch (Reference notes don't carry a lifecycle
    schema, per `~/.claude/skills/ttrpg-gm/references/frontmatter-schemas.md`
    "Reference note" section). These tests verify the stub's
    structural shape — the frontmatter parses, the H1 is present,
    `kind: pc` reads correctly, and `aliases:` round-trips as a list
    of strings when present.
    """

    def test_minimal_stub_no_body_no_aliases(self, tmp_path: Path) -> None:
        """The H1-only default: `kind: pc`, no `aliases:`, no body prose."""
        pc = _write(
            tmp_path / "pcs" / "silas.md",
            """\
            ---
            kind: pc
            ---

            # Silas
            """,
        )
        result = validate_file(tmp_path, pc)
        # Reference notes have no lifecycle schema — unspecified.
        assert result["schema"] == "unspecified"
        assert result["frontmatter"]["kind"] == "pc"
        # No aliases key when none were captured at survey time.
        assert "aliases" not in result["frontmatter"]
        # H1 is the canonical name; body has no prose past the H1.
        assert result["body"].strip() == "# Silas"

    def test_stub_with_aliases_and_one_line_body(self, tmp_path: Path) -> None:
        """The GM-enriched shape: `aliases:` list + one-line body."""
        pc = _write(
            tmp_path / "pcs" / "helerel.md",
            """\
            ---
            kind: pc
            aliases: [Helly]
            ---

            # Helerel

            Dwarf cleric.
            """,
        )
        result = validate_file(tmp_path, pc)
        assert result["schema"] == "unspecified"
        assert result["frontmatter"]["kind"] == "pc"
        assert result["frontmatter"]["aliases"] == ["Helly"]
        assert "# Helerel" in result["body"]
        assert "Dwarf cleric." in result["body"]

    def test_stub_with_multiple_aliases(self, tmp_path: Path) -> None:
        """`aliases:` accepts multiple entries (e.g., nickname + given-name)."""
        pc = _write(
            tmp_path / "pcs" / "annika-marra.md",
            """\
            ---
            kind: pc
            aliases: [Captain Marra, Annika]
            ---

            # Annika Marra
            """,
        )
        result = validate_file(tmp_path, pc)
        assert result["frontmatter"]["kind"] == "pc"
        assert result["frontmatter"]["aliases"] == ["Captain Marra", "Annika"]

    def test_stub_aliases_round_trip_as_strings(self, tmp_path: Path) -> None:
        """`aliases:` entries are strings (the dedup-matching pass slugifies)."""
        pc = _write(
            tmp_path / "pcs" / "marisa.md",
            """\
            ---
            kind: pc
            aliases: [Mari]
            ---

            # Marisa
            """,
        )
        result = validate_file(tmp_path, pc)
        aliases = result["frontmatter"]["aliases"]
        assert isinstance(aliases, list)
        assert all(isinstance(a, str) for a in aliases)
        assert aliases == ["Mari"]
