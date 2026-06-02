"""Tests for the `## Party` section in `campaign.md` (slice I, issue #85).

The composer spec at `references/campaign-overview-composer.md` mandates a
`## Party` section between the header and the `## Where the party might go
next session` menu. The section reads `pcs/<slug>.md` and renders one bullet
per PC with the canonical name (H1) plus an optional one-line body.

This module pins:

  (a) The Party section renders for campaigns with populated `pcs/`, one
      bullet per PC, deterministic alphabetical-by-slug ordering.
  (b) `_None._` renders when `pcs/` is empty or absent.
  (c) The section is skill-variant-identical: `/wrap-session`,
      `/prep-session`, and `/ingest` Phase 4 all produce the same Party
      rendering for the same `pcs/` state.
  (d) The Party section sits between the header and the
      `## Where the party might go next session` menu, per the spec's
      "Section ordering."

The composer is a prompt-driven LLM workflow at runtime; the executable
reference implementation below is the spec, mirroring the pattern used in
`test_wrap_session_idempotency.py::compose_campaign_md`. Given identical
campaign state, the function must return byte-identical output across
calls and across the three consuming skill variants for the Party section.
"""

from __future__ import annotations

from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Spec-derived helpers (mirrors the helpers in test_wrap_session_idempotency)
# ---------------------------------------------------------------------------


def parse_frontmatter(path: Path) -> tuple[dict[str, str], str]:
    """Tiny frontmatter parser: returns ({key: raw_value}, body_after_fm).

    Values are kept as raw strings. Mirrors the parser in
    `test_wrap_session_idempotency.py` so the two test modules apply the
    same parse rules to the composer's inputs.
    """
    text = path.read_text()
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}, text
    fm_block = text[4:end]
    body = text[end + len("\n---\n") :]
    fm: dict[str, str] = {}
    for line in fm_block.splitlines():
        if ":" not in line:
            continue
        k, _, v = line.partition(":")
        fm[k.strip()] = v.strip()
    return fm, body


def first_heading_title(path: Path) -> str | None:
    """Return the text of the first `# ` heading in a markdown file, if any.

    Mirrors the helper in `test_wrap_session_idempotency.py`. The composer
    spec calls the H1 the "canonical name" for a PC.
    """
    in_frontmatter = False
    saw_frontmatter_open = False
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if stripped == "---":
            if not saw_frontmatter_open:
                in_frontmatter = True
                saw_frontmatter_open = True
                continue
            if in_frontmatter:
                in_frontmatter = False
                continue
        if in_frontmatter:
            continue
        if stripped.startswith("# "):
            return stripped[2:].strip()
    return None


def first_body_line(path: Path) -> str | None:
    """Return the first non-empty body line after the H1, if any.

    Mirrors the composer spec: "the first non-empty line of the PC file's
    body (after the frontmatter and H1, skipping blank lines). Truncate at
    the first period for terseness if the body is multi-sentence."
    Returns None if the PC file is a bare frontmatter + H1 stub — the
    composer renders the bullet without an em-dash trailer in that case.
    """
    _, body = parse_frontmatter(path)
    saw_h1 = False
    for line in body.splitlines():
        stripped = line.strip()
        if not saw_h1:
            if stripped.startswith("# "):
                saw_h1 = True
            continue
        if not stripped:
            continue
        # Truncate at first period (spec: "for terseness if multi-sentence").
        if "." in stripped:
            stripped = stripped.split(".", 1)[0].strip()
        return stripped or None
    return None


# ---------------------------------------------------------------------------
# Reference composer for the `## Party` section
# ---------------------------------------------------------------------------


def compose_party_section(campaign: Path) -> str:
    """Render the `## Party` section per the composer spec.

    Skill-variant-free: `/wrap-session`, `/prep-session`, and `/ingest`
    Phase 4 all produce identical output for the same `pcs/` state.

    Ordering: alphabetical by slug (the `<slug>` portion of
    `pcs/<slug>.md`). Never relies on filesystem enumeration order.

    Renders `_None._` when `pcs/` is empty or does not exist.
    """
    lines: list[str] = ["## Party", ""]
    pcs_dir = campaign / "pcs"
    if not pcs_dir.is_dir():
        lines.append("_None._")
        lines.append("")
        return "\n".join(lines)

    pc_files = sorted(
        (p for p in pcs_dir.iterdir() if p.is_file() and p.name.endswith(".md")),
        key=lambda p: p.stem,
    )
    if not pc_files:
        lines.append("_None._")
        lines.append("")
        return "\n".join(lines)

    for p in pc_files:
        canonical = first_heading_title(p) or p.stem
        body_line = first_body_line(p)
        if body_line:
            lines.append(f"- **[[{canonical}]]** — {body_line}")
        else:
            lines.append(f"- **[[{canonical}]]**")
    lines.append("")
    return "\n".join(lines)


def compose_campaign_md_with_party(
    campaign: Path,
    campaign_name: str,
    system: str,
    *,
    variant: str,
) -> str:
    """Reference composer including the Party section, for the three
    consuming-skill variants.

    The `variant` argument selects between the skill-specific shapes
    documented under "Skill-specific variants" in the composer spec:

      * "wrap"   → `/wrap-session` shape
      * "prep"   → `/prep-session` shape
      * "ingest" → `/ingest` Phase 4 shape

    The Party section is identical across all three variants — that's the
    property test_party_section_is_identical_across_skill_variants pins.

    This is a deliberately reduced composer focused on the sections needed
    to verify Party-section behavior and ordering. The full menu-led
    "Where the party might go" surface is exercised by
    `test_wrap_session_idempotency.py::compose_campaign_md`; here we only
    need a stable downstream marker so the Party-section position
    assertion is unambiguous.
    """
    lines: list[str] = []
    lines.append(f"# {campaign_name} — Campaign Overview")
    lines.append("")
    lines.append(
        "*This file is agent-maintained. It snapshots the campaign's current "
        "state in glance-readable form and is rewritten by `/wrap-session` "
        "and `/ingest`. Manual edits will be reconciled (or overwritten with "
        "warning) at the next regeneration. For editorial campaign notes "
        "(themes, pitch, house rules), use a separate file the agent doesn't "
        "touch.*"
    )
    lines.append("")
    lines.append(f"- **Campaign:** {campaign_name}")
    lines.append(f"- **System:** {system}")
    if variant == "ingest":
        lines.append("- **Status:** active")
        lines.append("- **Last event:** 2026-06-01 (ingest)")
    lines.append("")

    # Party section — identical across all three variants.
    lines.append(compose_party_section(campaign))

    # Downstream marker so the position assertion is unambiguous.
    lines.append("## Where the party might go next session")
    lines.append("")
    lines.append("_None._")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def populated_campaign(tmp_path: Path) -> Path:
    """A campaign with a populated `pcs/` directory.

    Three PCs covering the shape variations the composer spec calls out:
      * Helerel — frontmatter + H1 + one-line body (the enriched stub case).
      * Silas — frontmatter + H1 only (the bare-stub case from ADR-0018).
      * Anya — body with multiple sentences (exercises the first-period
        truncation rule).
    """
    campaign = tmp_path / "campaign"
    pcs = campaign / "pcs"
    pcs.mkdir(parents=True)

    (pcs / "helerel.md").write_text(
        "---\nkind: pc\naliases: [Helly]\n---\n\n# Helerel\n\nDwarf cleric.\n"
    )
    (pcs / "silas.md").write_text(
        "---\nkind: pc\n---\n\n# Silas\n"
    )
    (pcs / "anya.md").write_text(
        "---\nkind: pc\n---\n\n# Anya\n\nHalf-elf rogue with a grudge "
        "against the Silent Court. Carries a stolen signet ring.\n"
    )
    return campaign


@pytest.fixture
def empty_pcs_campaign(tmp_path: Path) -> Path:
    """A campaign whose `pcs/` directory exists but is empty."""
    campaign = tmp_path / "campaign"
    (campaign / "pcs").mkdir(parents=True)
    return campaign


@pytest.fixture
def no_pcs_dir_campaign(tmp_path: Path) -> Path:
    """A campaign with no `pcs/` directory at all (legacy / pre-v0.3 state)."""
    campaign = tmp_path / "campaign"
    campaign.mkdir(parents=True)
    return campaign


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestPartySectionRenders:
    """Acceptance criterion (a): Party section renders for campaigns with
    populated `pcs/`, one bullet per PC, with the canonical name and one-line
    body."""

    def test_one_bullet_per_pc(self, populated_campaign: Path) -> None:
        section = compose_party_section(populated_campaign)
        bullet_lines = [
            line for line in section.splitlines() if line.startswith("- ")
        ]
        assert len(bullet_lines) == 3, (
            f"expected 3 PC bullets, got {len(bullet_lines)}:\n{section}"
        )

    def test_canonical_name_is_wiki_linked(
        self, populated_campaign: Path
    ) -> None:
        """The H1 (canonical name) must be rendered inside `[[...]]` so the
        overview links to the PC's Reference note."""
        section = compose_party_section(populated_campaign)
        assert "**[[Helerel]]**" in section
        assert "**[[Silas]]**" in section
        assert "**[[Anya]]**" in section

    def test_enriched_pc_renders_with_em_dash_body(
        self, populated_campaign: Path
    ) -> None:
        section = compose_party_section(populated_campaign)
        assert "- **[[Helerel]]** — Dwarf cleric" in section

    def test_bare_stub_pc_renders_without_em_dash(
        self, populated_campaign: Path
    ) -> None:
        """Silas's stub has no body — render the bullet with just the
        canonical name, never fabricate a one-liner."""
        section = compose_party_section(populated_campaign)
        # The bullet exists.
        assert "- **[[Silas]]**" in section
        # And there's no em-dash trailer on the Silas line.
        silas_line = next(
            line for line in section.splitlines()
            if "[[Silas]]" in line
        )
        assert "—" not in silas_line, (
            f"bare-stub PC bullet should have no em-dash trailer, "
            f"got: {silas_line!r}"
        )

    def test_multi_sentence_body_truncates_at_first_period(
        self, populated_campaign: Path
    ) -> None:
        """Anya's body has two sentences — the rendered bullet keeps only
        the first, per the composer's terseness rule."""
        section = compose_party_section(populated_campaign)
        anya_line = next(
            line for line in section.splitlines()
            if "[[Anya]]" in line
        )
        assert "Half-elf rogue with a grudge against the Silent Court" in anya_line
        assert "stolen signet ring" not in anya_line, (
            f"multi-sentence body should truncate at first period, "
            f"got: {anya_line!r}"
        )


class TestEmptyPcsRendersNone:
    """Acceptance criterion (b): `_None._` for empty `pcs/`."""

    def test_empty_pcs_directory_renders_none(
        self, empty_pcs_campaign: Path
    ) -> None:
        section = compose_party_section(empty_pcs_campaign)
        assert "_None._" in section

    def test_missing_pcs_directory_renders_none(
        self, no_pcs_dir_campaign: Path
    ) -> None:
        """Pre-v0.3 campaigns may not have a `pcs/` directory at all. The
        composer must still render the section header with `_None._` — no
        crash, no skipped section."""
        section = compose_party_section(no_pcs_dir_campaign)
        assert "## Party" in section
        assert "_None._" in section


class TestDeterministicOrdering:
    """Acceptance criterion (c): deterministic alphabetical-by-slug ordering.

    The spec mandates ordering by slug (not by H1, not by filesystem
    enumeration order). A campaign whose PC H1s sort one way and slugs sort
    another exercises the rule."""

    def test_alphabetical_by_slug(self, populated_campaign: Path) -> None:
        section = compose_party_section(populated_campaign)
        bullet_lines = [
            line for line in section.splitlines() if line.startswith("- ")
        ]
        # Slugs in alphabetical order: anya, helerel, silas.
        # H1s: Anya, Helerel, Silas. They happen to align here, but the
        # next test pins ordering against H1/slug divergence explicitly.
        assert "[[Anya]]" in bullet_lines[0]
        assert "[[Helerel]]" in bullet_lines[1]
        assert "[[Silas]]" in bullet_lines[2]

    def test_ordering_uses_slug_not_h1(self, tmp_path: Path) -> None:
        """When H1 and slug sort differently, slug wins. Construct two PCs
        where slug-sort and H1-sort give opposite orders."""
        campaign = tmp_path / "campaign"
        pcs = campaign / "pcs"
        pcs.mkdir(parents=True)
        # Slug "aaron" but H1 "Zelda" — slug sorts first, H1 sorts last.
        (pcs / "aaron.md").write_text(
            "---\nkind: pc\n---\n\n# Zelda\n\nSorcerer.\n"
        )
        # Slug "zane" but H1 "Aldric" — slug sorts last, H1 sorts first.
        (pcs / "zane.md").write_text(
            "---\nkind: pc\n---\n\n# Aldric\n\nFighter.\n"
        )
        section = compose_party_section(campaign)
        bullet_lines = [
            line for line in section.splitlines() if line.startswith("- ")
        ]
        # Slug "aaron" comes first → its H1 "Zelda" appears first.
        assert "[[Zelda]]" in bullet_lines[0], (
            "ordering must be by slug, not by H1"
        )
        assert "[[Aldric]]" in bullet_lines[1]

    def test_two_runs_byte_identical(self, populated_campaign: Path) -> None:
        first = compose_party_section(populated_campaign)
        second = compose_party_section(populated_campaign)
        assert first == second, (
            "Party section must be a pure function of campaign state"
        )


class TestSkillVariantIdenticalOutput:
    """Acceptance criterion (d): Party section renders identically across
    the three consuming skills.

    The composer spec explicitly calls this section "skill-variant-free." The
    header may differ across variants (`/ingest` adds Status / Last event
    lines), and downstream sections may differ in shape (truncation,
    `## Adventures` inclusion), but the Party section's bytes must match
    exactly for the same `pcs/` state.
    """

    def test_party_section_is_identical_across_skill_variants(
        self, populated_campaign: Path
    ) -> None:
        party_only = compose_party_section(populated_campaign)
        for variant_a, variant_b in (
            ("wrap", "prep"),
            ("wrap", "ingest"),
            ("prep", "ingest"),
        ):
            out_a = compose_campaign_md_with_party(
                populated_campaign,
                "Test Campaign",
                "D&D 5e",
                variant=variant_a,
            )
            out_b = compose_campaign_md_with_party(
                populated_campaign,
                "Test Campaign",
                "D&D 5e",
                variant=variant_b,
            )
            # The Party section block must appear byte-identical in both
            # full outputs — extract the slice from "## Party" through the
            # blank line before "## Where the party might go next session"
            # and compare.
            slice_a = _extract_party_slice(out_a)
            slice_b = _extract_party_slice(out_b)
            assert slice_a == slice_b, (
                f"Party section diverged between {variant_a!r} and "
                f"{variant_b!r} variants:\n--- {variant_a} ---\n{slice_a}\n"
                f"--- {variant_b} ---\n{slice_b}"
            )
            # And both slices must match the standalone Party-section
            # rendering — the composer doesn't get to mutate it in passing.
            assert slice_a.rstrip() == party_only.rstrip(), (
                f"variant {variant_a!r} mutated the Party section vs. "
                f"the standalone composer"
            )

    def test_party_section_identical_for_empty_pcs_across_variants(
        self, empty_pcs_campaign: Path
    ) -> None:
        """The `_None._` rendering must also be skill-variant-free."""
        for variant in ("wrap", "prep", "ingest"):
            out = compose_campaign_md_with_party(
                empty_pcs_campaign,
                "Test Campaign",
                "D&D 5e",
                variant=variant,
            )
            assert "## Party" in out
            party_slice = _extract_party_slice(out)
            assert "_None._" in party_slice, (
                f"variant {variant!r} did not render `_None._` for empty pcs/"
            )


class TestPartySectionPosition:
    """Acceptance criterion: Party section sits between the header and
    `## Where the party might go next session`.

    The composer spec's "Section ordering" places `## Party` at position 2,
    after the header (position 1) and before the menu (position 3).
    """

    def test_party_appears_after_header_before_menu(
        self, populated_campaign: Path
    ) -> None:
        out = compose_campaign_md_with_party(
            populated_campaign,
            "Test Campaign",
            "D&D 5e",
            variant="wrap",
        )
        header_pos = out.index("- **System:**")
        party_pos = out.index("## Party")
        menu_pos = out.index("## Where the party might go next session")
        assert header_pos < party_pos < menu_pos, (
            f"section ordering wrong: header={header_pos}, "
            f"party={party_pos}, menu={menu_pos}"
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_party_slice(rendered: str) -> str:
    """Return the substring from the `## Party` header through (exclusive)
    the next H2 heading. Used by the skill-variant equality assertions so
    the comparison is scoped to just the Party block."""
    start = rendered.index("## Party")
    rest = rendered[start:]
    # Find the next H2 heading after the Party heading.
    lines = rest.splitlines(keepends=True)
    out_lines: list[str] = [lines[0]]  # the "## Party" line itself
    for line in lines[1:]:
        if line.startswith("## "):
            break
        out_lines.append(line)
    return "".join(out_lines)
