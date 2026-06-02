"""Reference-Python coverage of the v0.3 slice L+M PC creation paths.

This file follows the v0.1 test convention (see test_secret_store.py,
test_pc_roster_proposal.py, test_wrap_session_idempotency.py): the
reference Python below is a thin near-translation of the prose
algorithms documented in:

  - `references/prep-session-questions.md` "GM Focus Check" →
    "New-PC disclosure handling": recognizing new-PC disclosures in
    free-form GM responses to the always-fires final question, creating
    `pcs/<slug>.md` via the canonical stub shape, and adding the new PC
    to relevant Brief sections.
  - `references/reference-note-extraction.md` "PC-actor narrative
    framing as wrap-time discriminator": the wrap-time Pass 2 / Step 3
    discrimination heuristic that inverts the ingest-time
    `PC source:` classification path. Confident PC-actor framings
    stage at `pcs/<slug>.md` directly; ambiguous framings default to
    NPC and surface a Step 3 PC-or-NPC ASK; Step 4 review supports
    moving the staged file between `pcs/` and `npcs/`.

The reference impl is **not** a runtime helper — skills follow the
prose in the references at runtime. The tests exist so the spec and
the per-skill prose can't silently drift apart. Per ADR-0018 (refined
by ADR-0022), the PC stub shape is fixed: `kind: pc` frontmatter,
optional `aliases:`, H1 from canonical name, optional one-line body.

Slice L (prep-time) and slice M (wrap-time) ship together as two
prose extensions to existing surfaces — no new steps or categories.
"""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Slug normalization rule (mirrored from test_pc_roster_proposal.py /
# references/dedup-matching.md). The new-PC creation path slugifies any
# free-form name the GM states.
# ---------------------------------------------------------------------------


_LEADING_THE_RE = re.compile(r"^the[\s\-_]+", flags=re.IGNORECASE)
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")


def slugify(name: str) -> str:
    s = name.lower()
    if s.endswith(".md"):
        s = s[:-3]
    fold = str.maketrans({"é": "e", "è": "e", "ê": "e", "ç": "c", "ñ": "n"})
    s = s.translate(fold)
    s = _LEADING_THE_RE.sub("", s)
    s = _NON_ALNUM_RE.sub("-", s)
    return s.strip("-")


# ---------------------------------------------------------------------------
# PC stub shape (mirrored from references/pc-roster-proposal.md and
# references/frontmatter-schemas.md "Worked example: PC stub"). The
# /prep-session new-PC disclosure path and the /wrap-session Pass 2
# direct-PC-route path produce the same shape.
# ---------------------------------------------------------------------------


@dataclass
class PCStubSpec:
    slug: str
    canonical_name: str = ""
    aliases: list[str] = field(default_factory=list)
    body: str = ""


def render_pc_stub(spec: PCStubSpec) -> str:
    """Render the canonical PC stub per pc-roster-proposal.md.

    Frontmatter: `kind: pc` always; `aliases:` only if non-empty.
    Body: H1 from canonical_name (fallback: title-cased slug tokens);
    optional one-line body if the disclosure / notes supplied one.
    """
    fm_lines = ["---", "kind: pc"]
    if spec.aliases:
        fm_lines.append(f"aliases: [{', '.join(spec.aliases)}]")
    fm_lines.append("---")
    fm = "\n".join(fm_lines)
    h1 = spec.canonical_name or " ".join(
        t.capitalize() for t in spec.slug.split("-")
    )
    body = ""
    if spec.body:
        body = f"\n{spec.body}\n"
    return f"{fm}\n\n# {h1}\n{body}"


# ---------------------------------------------------------------------------
# /prep-session GM Focus Check — new-PC disclosure recognition
# (references/prep-session-questions.md "New-PC disclosure handling").
# ---------------------------------------------------------------------------


# Bringing-a-PC and PC-introduce phrasings the recognition cue matches.
# Per the reference, GM phrasings vary but cluster around three shapes:
#   - "X is bringing PC in tonight" / "X's bringing PC tonight"
#   - "new player tonight, his/her PC's <name>"
#   - "new PC: <name>" / "add a PC: <name>"
_BRINGING_RE = re.compile(
    r"\b(?:bringing|brings|brought)\s+([A-Z][A-Za-z'\-]+)"
    r"(?:\s+in)?\s+(?:tonight|in)\b",
    flags=re.IGNORECASE,
)
_NEW_PLAYER_RE = re.compile(
    r"\bnew\s+player\b[^.]*?(?:PC|character)(?:'s|\s+is)\s+([A-Z][A-Za-z'\-]+)",
    flags=re.IGNORECASE,
)
_EXPLICIT_PC_RE = re.compile(
    r"\b(?:new\s+PC|add\s+a\s+PC)\s*[:,]\s*([A-Z][A-Za-z'\-]+)",
    flags=re.IGNORECASE,
)


@dataclass
class DisclosureMatch:
    """A new-PC recognition outcome.

    `name` is the GM-stated name. Optional `role_oneliner` carries any
    short role description from the rest of the GM utterance — the
    reference allows the stub body to be enriched from such hints
    ("elf ranger", "half-orc warlock; patron's the Reborn Flame Cult").
    """

    name: str
    role_oneliner: str = ""


def recognize_new_pc_disclosure(utterance: str) -> DisclosureMatch | None:
    """Recognize a new-PC disclosure in a GM's free-form Focus Check reply.

    Returns the matched PC name (and optional role one-liner) if the
    utterance contains one of the bringing/new-player/explicit-PC
    phrasings; None otherwise. The reference says borderline phrasings
    like "Maya's going to meet the party tonight" do NOT route through
    here (Maya could be a player whose PC needs naming, or an NPC —
    the agent should ask, not silently create).
    """
    for pat in (_BRINGING_RE, _NEW_PLAYER_RE, _EXPLICIT_PC_RE):
        m = pat.search(utterance)
        if m:
            name = m.group(1).strip()
            # Crude role-oneliner extraction: any descriptor clause
            # following the name up to the next sentence break.
            role = _extract_role_oneliner(utterance, m.end())
            return DisclosureMatch(name=name, role_oneliner=role)
    return None


def _extract_role_oneliner(utterance: str, after_idx: int) -> str:
    """Pull a short role hint from the GM utterance, if any.

    Looks for "— <role>" or ", <role>" patterns after the PC name and
    truncates at sentence boundaries. The role is optional; an empty
    string means the stub body stays empty.
    """
    tail = utterance[after_idx:]
    # Trim leading separators.
    m = re.match(r"\s*[—,–:-]\s*([^.\n]+)", tail)
    if not m:
        return ""
    role = m.group(1).strip()
    # Truncate at the first " — " inside the role clause if the GM
    # chained another thought.
    role = re.split(r"\s+—\s+", role, maxsplit=1)[0].strip()
    return role


# ---------------------------------------------------------------------------
# Brief revision shapes for the new-PC disclosure path.
# Per the reference, the minimum revision is a GM-scratchpad nudge
# naming the new PC; additional section surfacings are GM-directed.
# ---------------------------------------------------------------------------


@dataclass
class BriefRevision:
    """Diff-style record of Brief revisions for the new-PC path."""

    scratchpad_lines: list[str] = field(default_factory=list)


def draft_brief_revision_for_new_pc(
    pc_slug: str,
    pc_name: str,
    role_oneliner: str = "",
    brought_by: str = "",
) -> BriefRevision:
    """Draft the Brief revision shape per the reference's step 4.

    The minimum revision is the scratchpad nudge:
      `- New PC this session: [[pcs/<slug>]] (<Name>)<, brought by <player>>.<role tail>`
    Optional role tail surfaces the role one-liner where relevant.
    """
    parts = [f"- New PC this session: [[pcs/{pc_slug}]] ({pc_name})"]
    if brought_by:
        parts.append(f", brought by {brought_by}")
    parts.append(".")
    if role_oneliner:
        parts.append(f" {role_oneliner}.")
    line = "".join(parts)
    return BriefRevision(scratchpad_lines=[line])


def stage_and_promote_disclosure(
    match: DisclosureMatch,
    campaign_root: Path,
) -> tuple[Path | None, str]:
    """Stage and promote a new PC from a GM Focus Check disclosure.

    Returns (final_path, slug). `final_path` is the on-disk
    `pcs/<slug>.md` if the promotion succeeded, or None on collision
    (caller asks the GM to disambiguate). Slug is always returned so
    the caller can also reference it in the Brief revision.

    Per the reference, promotion is **immediate** on disclosure (not
    gated by Brief approval) — if the GM later cancels the Brief at
    Step 4, the PC file persists.
    """
    slug = slugify(match.name)
    pcs_dir = campaign_root / "pcs"
    existing = pcs_dir / f"{slug}.md"
    if existing.exists():
        # Collision — caller surfaces an ASK rather than overwriting.
        return None, slug

    staging_dir = campaign_root / ".ttrpg-staging" / "pcs"
    staging_dir.mkdir(parents=True, exist_ok=True)
    staged_path = staging_dir / f"{slug}.md"
    spec = PCStubSpec(
        slug=slug,
        canonical_name=match.name,
        body=match.role_oneliner,
    )
    staged_path.write_text(render_pc_stub(spec), encoding="utf-8")

    pcs_dir.mkdir(parents=True, exist_ok=True)
    final_path = pcs_dir / f"{slug}.md"
    final_path.write_text(staged_path.read_text(encoding="utf-8"), encoding="utf-8")
    staged_path.unlink()
    try:
        staging_dir.rmdir()
    except OSError:
        pass
    return final_path, slug


# ---------------------------------------------------------------------------
# /wrap-session Pass 2 — PC-actor narrative framing as wrap-time
# discriminator (references/reference-note-extraction.md).
# ---------------------------------------------------------------------------


# Strong PC-actor signals: the named character performs PC-shaped
# actions or is grouped with the party via shared pronouns. The
# reference enumerates three signal families; we encode lightweight
# patterns that the LLM agent would apply with richer judgment.
_PC_ACTOR_VERBS = [
    "drew", "drew his", "drew her",
    "charged", "rolled", "cast", "fired", "swung", "shot",
    "picked the lock", "searched", "climbed",
]
_NPC_SUBJECT_PATTERNS = [
    re.compile(r"\bthe party met\b", re.IGNORECASE),
    re.compile(r"\barrived at\b", re.IGNORECASE),
    re.compile(r"\brefused to talk\b", re.IGNORECASE),
    re.compile(r"\b(?:is|was|seemed|remained)\s+(?:wary|hostile|skeptical|friendly)", re.IGNORECASE),
    re.compile(r"\bthe (?:blacksmith|innkeeper|captain|priest)\b", re.IGNORECASE),
]


def score_pc_actor_framing(name: str, notes: str) -> tuple[int, int]:
    """Score PC-actor vs NPC framing signals for a named character.

    Returns (pc_signals, npc_signals). The reference says:
      - PC-actor signals → route to `pcs/` directly (no ASK).
      - NPC signals dominate → default NPC.
      - Mixed / ambiguous → default NPC, but surface PC-or-NPC ASK at
        Step 3. The "default NPC if ambiguous" rule is explicit.

    The agent applies richer judgment than this reference encoder; the
    point of this function is to pin the *shape* of the heuristic so a
    drift between prose and spec is detectable.
    """
    pc = 0
    npc = 0
    # PC signal 1: subject-of-party-action ("Theron drew his sword").
    for verb in _PC_ACTOR_VERBS:
        if re.search(
            rf"\b{re.escape(name)}\b[^.]*\b{re.escape(verb)}\b",
            notes,
            flags=re.IGNORECASE,
        ):
            pc += 1
    # PC signal 2: party-pronoun grouping. The name appears inside a
    # parenthesized party list ("party (Silas, Rae, Theron)") or in a
    # "X and <name>" grouping with another PC-shaped name. We
    # approximate with parenthesized-list detection here; the LLM
    # applies richer judgment at runtime.
    if re.search(
        rf"\bparty\s*\([^)]*\b{re.escape(name)}\b[^)]*\)",
        notes,
        flags=re.IGNORECASE,
    ):
        pc += 1
    # PC signal 3: player-attribution shorthand ("Maya described Theron's spell").
    if re.search(
        rf"\b[A-Z][a-z]+\s+(?:described|narrated|said|rolled for)\s+{re.escape(name)}",
        notes,
    ):
        pc += 1
    # NPC signals: any of the subject-framing patterns.
    for pat in _NPC_SUBJECT_PATTERNS:
        if pat.search(notes):
            npc += 1
    # Stance-toward-party framing for the named character.
    if re.search(
        rf"\b{re.escape(name)}\s+(?:is|was|seemed|remained)\s+"
        r"(?:wary|hostile|skeptical|friendly|pleased|displeased)",
        notes,
        flags=re.IGNORECASE,
    ):
        npc += 1
    return pc, npc


@dataclass
class Pass2Routing:
    """How Pass 2's PC-actor discriminator routes a candidate.

    `route`: "pcs" (confident PC-actor — no ASK), "npcs" (default,
    including confident NPC framing), or "ask" (ambiguous — Step 3
    surfaces the PC-or-NPC ASK).
    """

    name: str
    route: str  # "pcs" | "npcs" | "ask"
    pc_signals: int = 0
    npc_signals: int = 0


def route_pass2_candidate(name: str, notes: str) -> Pass2Routing:
    """Per the reference's "PC-actor heuristic for Pass 2":
      - Strong PC signals AND no NPC signals → "pcs"
      - Mixed signals (both > 0) → "ask"
      - All other cases (including no signals) → "npcs" (default)

    The default-to-NPC rule absorbs the "False-positive NPCs are
    cheap; false-positive PCs are not cheap" reasoning from the
    reference.
    """
    pc, npc = score_pc_actor_framing(name, notes)
    if pc > 0 and npc == 0:
        route = "pcs"
    elif pc > 0 and npc > 0:
        route = "ask"
    else:
        route = "npcs"
    return Pass2Routing(name=name, route=route, pc_signals=pc, npc_signals=npc)


# ---------------------------------------------------------------------------
# Step 4 move-to-correct-directory affordance.
# References/reference-note-extraction.md: when the GM moves a staged
# file across kinds (npcs ↔ pcs), Step 5 promotion reads from whichever
# path the GM left the file in.
# ---------------------------------------------------------------------------


def gm_moves_staged_file_across_kind(
    staging_root: Path,
    slug: str,
    from_kind: str,
    to_kind: str,
) -> Path:
    """Simulate the GM moving a staged file from one kind to another.

    `staging_root` is `.ttrpg-staging/wrap/` in the wrap-session
    workflow. The GM does this in their IDE; we mirror it here so the
    test can assert Step 5 promotion reads from the new location.
    """
    src = staging_root / from_kind / f"{slug}.md"
    dst = staging_root / to_kind / f"{slug}.md"
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))
    return dst


def step5_promote_from_staging(
    staging_root: Path,
    campaign_root: Path,
    slug: str,
) -> Path:
    """Translate the staged path to the final campaign path and write.

    Per skills/wrap-session/SKILL.md Step 5: "files inside `wrap/`
    mirror the campaign repo, so the move is a path translation."
    The promotion uses whichever kind directory the file currently
    lives in (so a GM move across kinds is respected).
    """
    # Find the file under any kind directory in staging.
    candidates = list(staging_root.glob(f"*/{slug}.md"))
    assert len(candidates) == 1, (
        f"expected exactly one staged file for slug={slug!r}, "
        f"found {len(candidates)}"
    )
    staged = candidates[0]
    kind = staged.parent.name
    final = campaign_root / kind / f"{slug}.md"
    final.parent.mkdir(parents=True, exist_ok=True)
    final.write_text(staged.read_text(encoding="utf-8"), encoding="utf-8")
    return final


# ---------------------------------------------------------------------------
# Tests — slice L (prep-time GM Focus Check new-PC disclosure)
# ---------------------------------------------------------------------------


class TestRecognizeNewPCDisclosure:
    """Recognition cues per references/prep-session-questions.md."""

    def test_bringing_phrasing_matches(self) -> None:
        m = recognize_new_pc_disclosure(
            "Maya's bringing Theron in tonight — half-orc warlock."
        )
        assert m is not None
        assert m.name == "Theron"

    def test_explicit_new_pc_phrasing_matches(self) -> None:
        m = recognize_new_pc_disclosure("new PC: Veshenna, elf ranger.")
        assert m is not None
        assert m.name == "Veshenna"

    def test_add_a_pc_phrasing_matches(self) -> None:
        m = recognize_new_pc_disclosure("add a PC: Tarn, dwarf fighter.")
        assert m is not None
        assert m.name == "Tarn"

    def test_new_player_phrasing_matches(self) -> None:
        m = recognize_new_pc_disclosure(
            "We have a new player tonight, his PC's Korben."
        )
        assert m is not None
        assert m.name == "Korben"

    def test_ambiguous_phrasing_does_not_match(self) -> None:
        # The reference says "Maya's going to meet the party tonight"
        # is a borderline phrasing — should NOT silently route to PC
        # creation. Maya is treated as ambiguous (the agent asks
        # rather than guessing).
        m = recognize_new_pc_disclosure(
            "Maya's going to meet the party tonight."
        )
        assert m is None

    def test_role_oneliner_is_extracted_when_present(self) -> None:
        m = recognize_new_pc_disclosure(
            "Maya's bringing Theron in tonight — half-orc warlock."
        )
        assert m is not None
        assert "half-orc warlock" in m.role_oneliner

    def test_role_oneliner_truncates_at_secondary_clause(self) -> None:
        # GM dumps multiple thoughts; role-oneliner pulls only the
        # immediate descriptor.
        m = recognize_new_pc_disclosure(
            "new PC: Veshenna, elf ranger. We also need to revisit Locations."
        )
        assert m is not None
        assert "elf ranger" in m.role_oneliner
        assert "revisit" not in m.role_oneliner


class TestStageAndPromoteDisclosure:
    """The disclosure → `pcs/<slug>.md` creation path."""

    def test_creates_pc_file_via_stub_shape(self, tmp_path: Path) -> None:
        match = DisclosureMatch(
            name="Theron", role_oneliner="half-orc warlock"
        )
        final, slug = stage_and_promote_disclosure(match, tmp_path)
        assert slug == "theron"
        assert final is not None
        assert final == tmp_path / "pcs" / "theron.md"
        content = final.read_text(encoding="utf-8")
        # Canonical PC stub shape per references/frontmatter-schemas.md
        # "Worked example: PC stub": kind: pc frontmatter + H1.
        assert content.startswith("---\nkind: pc\n---")
        assert "# Theron" in content

    def test_role_oneliner_lands_in_stub_body(self, tmp_path: Path) -> None:
        match = DisclosureMatch(
            name="Theron", role_oneliner="half-orc warlock"
        )
        final, _ = stage_and_promote_disclosure(match, tmp_path)
        content = final.read_text(encoding="utf-8")
        assert "half-orc warlock" in content

    def test_empty_role_omits_body(self, tmp_path: Path) -> None:
        match = DisclosureMatch(name="Korben", role_oneliner="")
        final, _ = stage_and_promote_disclosure(match, tmp_path)
        content = final.read_text(encoding="utf-8")
        # The stub is frontmatter + H1 only (per the "Silas" example in
        # frontmatter-schemas.md's worked example).
        assert content.rstrip().endswith("# Korben")

    def test_collision_does_not_overwrite_existing_pc(
        self, tmp_path: Path
    ) -> None:
        # GM says "bringing Theron tonight" but pcs/theron.md already
        # exists. Per the reference's collision check, don't silently
        # overwrite; return None so the caller asks the GM.
        pcs = tmp_path / "pcs"
        pcs.mkdir()
        existing = pcs / "theron.md"
        existing.write_text(
            "---\nkind: pc\n---\n\n# Theron\n\nHand-authored body.\n",
            encoding="utf-8",
        )
        original = existing.read_text(encoding="utf-8")

        match = DisclosureMatch(name="Theron")
        final, slug = stage_and_promote_disclosure(match, tmp_path)
        assert final is None
        assert slug == "theron"
        # Existing file preserved byte-for-byte.
        assert existing.read_text(encoding="utf-8") == original

    def test_promotion_persists_through_staging_cleanup(
        self, tmp_path: Path
    ) -> None:
        # The reference says promotion is immediate; the staging
        # directory should be cleaned up after.
        match = DisclosureMatch(name="Veshenna")
        final, _ = stage_and_promote_disclosure(match, tmp_path)
        assert final.exists()
        assert not (tmp_path / ".ttrpg-staging" / "pcs").exists()


class TestBriefRevisionForNewPC:
    """Brief active-PCs surface revision per the reference's step 4."""

    def test_scratchpad_nudge_is_minimum_revision(self) -> None:
        rev = draft_brief_revision_for_new_pc(
            pc_slug="theron",
            pc_name="Theron",
            brought_by="Maya",
        )
        assert any("[[pcs/theron]]" in line for line in rev.scratchpad_lines)
        assert any("Theron" in line for line in rev.scratchpad_lines)
        assert any("Maya" in line for line in rev.scratchpad_lines)

    def test_role_oneliner_surfaces_in_scratchpad(self) -> None:
        rev = draft_brief_revision_for_new_pc(
            pc_slug="theron",
            pc_name="Theron",
            role_oneliner="half-orc warlock; patron is the Reborn Flame Cult",
        )
        joined = "\n".join(rev.scratchpad_lines)
        assert "half-orc warlock" in joined

    def test_brought_by_is_optional(self) -> None:
        rev = draft_brief_revision_for_new_pc(
            pc_slug="korben", pc_name="Korben"
        )
        joined = "\n".join(rev.scratchpad_lines)
        assert "[[pcs/korben]]" in joined
        assert "brought by" not in joined


# ---------------------------------------------------------------------------
# Tests — slice M (wrap-time Pass 2 PC discrimination)
# ---------------------------------------------------------------------------


class TestPass2PCActorRouting:
    """PC-actor framing routing per references/reference-note-extraction.md."""

    def test_clear_pc_actor_framing_routes_to_pcs(self) -> None:
        notes = "Theron drew his sword and charged the cultist."
        result = route_pass2_candidate("Theron", notes)
        assert result.route == "pcs"
        assert result.pc_signals > 0

    def test_clear_npc_framing_routes_to_npcs(self) -> None:
        notes = "The party met Maren at the docks. She was wary."
        result = route_pass2_candidate("Maren", notes)
        assert result.route == "npcs"

    def test_ambiguous_framing_routes_to_ask(self) -> None:
        # Mixed signals: Marisa is the actor in one sentence and the
        # subject of NPC-shaped framing in another.
        notes = (
            "Marisa drew her bow as the party met Maren at the docks. "
            "Later, Marisa was wary of the deal."
        )
        result = route_pass2_candidate("Marisa", notes)
        assert result.route == "ask"
        assert result.pc_signals > 0
        assert result.npc_signals > 0

    def test_default_npc_when_no_signals(self) -> None:
        # Per the reference: "Default to NPC if framing is ambiguous."
        # A bare mention with no clear signal falls through to NPC.
        notes = "Someone named Korben was in the room."
        result = route_pass2_candidate("Korben", notes)
        assert result.route == "npcs"

    def test_party_pronoun_grouping_is_a_pc_signal(self) -> None:
        notes = "The party (Silas, Rae, and Theron) approached the gate."
        result = route_pass2_candidate("Theron", notes)
        assert result.pc_signals > 0

    def test_player_attribution_is_a_pc_signal(self) -> None:
        notes = "Maya described Theron's spell — chains of fire."
        result = route_pass2_candidate("Theron", notes)
        assert result.pc_signals > 0

    def test_stance_toward_party_is_an_npc_signal(self) -> None:
        notes = "Sera was wary of the party after the deal fell through."
        result = route_pass2_candidate("Sera", notes)
        assert result.npc_signals > 0


class TestStep4MoveAcrossKind:
    """The Step 4 GM correction affordance — move staged file."""

    def test_gm_move_from_npcs_to_pcs_lands_at_pcs(
        self, tmp_path: Path
    ) -> None:
        # Agent staged npcs/marisa.md under .ttrpg-staging/wrap/.
        staging_root = tmp_path / ".ttrpg-staging" / "wrap"
        (staging_root / "npcs").mkdir(parents=True)
        staged = staging_root / "npcs" / "marisa.md"
        staged.write_text(
            "---\nkind: pc\n---\n\n# Marisa\n", encoding="utf-8"
        )

        # GM moves to pcs/ in their IDE.
        moved = gm_moves_staged_file_across_kind(
            staging_root, "marisa", "npcs", "pcs"
        )
        assert moved == staging_root / "pcs" / "marisa.md"
        assert moved.exists()
        assert not staged.exists()

        # Step 5 promotion lands the file at pcs/, not npcs/.
        campaign_root = tmp_path / "campaign"
        final = step5_promote_from_staging(
            staging_root, campaign_root, "marisa"
        )
        assert final == campaign_root / "pcs" / "marisa.md"
        assert final.exists()
        assert not (campaign_root / "npcs" / "marisa.md").exists()

    def test_gm_move_from_pcs_to_npcs_lands_at_npcs(
        self, tmp_path: Path
    ) -> None:
        # Inverse: agent confidently staged pcs/theron.md, GM realizes
        # Theron was actually an NPC ally and moves to npcs/.
        staging_root = tmp_path / ".ttrpg-staging" / "wrap"
        (staging_root / "pcs").mkdir(parents=True)
        staged = staging_root / "pcs" / "theron.md"
        staged.write_text(
            "---\nkind: pc\n---\n\n# Theron\n", encoding="utf-8"
        )

        gm_moves_staged_file_across_kind(
            staging_root, "theron", "pcs", "npcs"
        )

        campaign_root = tmp_path / "campaign"
        final = step5_promote_from_staging(
            staging_root, campaign_root, "theron"
        )
        assert final == campaign_root / "npcs" / "theron.md"
        assert final.exists()
        assert not (campaign_root / "pcs" / "theron.md").exists()


# ---------------------------------------------------------------------------
# Tests — spec-drift safety net (references must document the behavior).
# ---------------------------------------------------------------------------


class TestReferencesDocumentNewBehavior:
    """The references must call out the new prose extensions explicitly."""

    def test_prep_session_questions_documents_new_pc_disclosure(
        self, repo_root: Path
    ) -> None:
        ref = repo_root / "references" / "prep-session-questions.md"
        content = ref.read_text(encoding="utf-8")
        # The "New-PC disclosure handling" subsection must exist under
        # GM Focus Check response handling.
        assert "New-PC disclosure handling" in content, (
            "references/prep-session-questions.md GM Focus Check section "
            "must document new-PC disclosure response handling per slice L."
        )
        # The reference must cite the PC stub shape source.
        assert "pc-roster-proposal" in content, (
            "references/prep-session-questions.md new-PC disclosure "
            "handling must cite references/pc-roster-proposal.md for "
            "the canonical PC stub shape."
        )

    def test_prep_session_questions_documents_brought_in_cue(
        self, repo_root: Path
    ) -> None:
        ref = repo_root / "references" / "prep-session-questions.md"
        content = ref.read_text(encoding="utf-8")
        # The bringing-a-PC recognition cue is the canonical example.
        assert "bringing" in content.lower(), (
            "references/prep-session-questions.md new-PC disclosure "
            "must document the bringing-a-PC phrasing as a recognition cue."
        )

    def test_reference_note_extraction_documents_pc_actor_framing(
        self, repo_root: Path
    ) -> None:
        ref = repo_root / "references" / "reference-note-extraction.md"
        content = ref.read_text(encoding="utf-8")
        # The wrap-time discriminator section must exist.
        assert "PC-actor narrative framing" in content, (
            "references/reference-note-extraction.md must document "
            "PC-actor narrative framing as the wrap-time discriminator "
            "per slice M."
        )
        # The "default to NPC if ambiguous" rule is load-bearing.
        assert "Default to NPC" in content, (
            "references/reference-note-extraction.md PC-actor framing "
            "section must document the default-to-NPC fallback for "
            "ambiguous framings."
        )

    def test_reference_note_extraction_documents_step4_move(
        self, repo_root: Path
    ) -> None:
        ref = repo_root / "references" / "reference-note-extraction.md"
        content = ref.read_text(encoding="utf-8")
        # The Step 4 move-across-kind affordance is the GM's correction
        # surface for confident-but-wrong PC routing.
        assert "Step 4" in content and "move" in content.lower(), (
            "references/reference-note-extraction.md must document the "
            "Step 4 move-to-correct-directory affordance per slice M."
        )

    def test_prep_session_skill_cites_new_pc_handling(
        self, repo_root: Path
    ) -> None:
        skill = repo_root / "skills" / "prep-session" / "SKILL.md"
        content = skill.read_text(encoding="utf-8")
        # Step 3.5 GM Focus Check enumeration cites the response-handling
        # extension.
        assert "new-PC" in content or "New-PC" in content, (
            "skills/prep-session/SKILL.md Step 3.5 GM Focus Check entry "
            "must cite the new-PC disclosure handling per slice L."
        )

    def test_wrap_session_skill_cites_pc_actor_discriminator(
        self, repo_root: Path
    ) -> None:
        skill = repo_root / "skills" / "wrap-session" / "SKILL.md"
        content = skill.read_text(encoding="utf-8")
        # Pass 2 cites the wrap-time PC-actor discriminator.
        assert "PC-actor" in content, (
            "skills/wrap-session/SKILL.md Pass 2 must cite the PC-actor "
            "narrative framing discriminator per slice M."
        )
