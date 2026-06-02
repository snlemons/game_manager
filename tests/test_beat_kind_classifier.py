"""Beat `kind:` classifier — section-heading + body-content recognizers.

This file is a reference implementation of the heuristic specified in
`references/beat-kind-classification.md`. The skills (`/ingest` Phase 3
and `/wrap-session` Pass 7) consult that reference to draft a `kind:`
value at extraction time; this test module encodes the heuristic as
Python so the per-kind recognizer rules can be regression-tested.

The reference implementation here intentionally mirrors the prose of
the spec — it is NOT a runtime helper the skills import. The skills run
on prose instruction; this code is the deterministic mirror used by the
test suite to catch drift between the spec and a future runtime helper
(or, today, between the spec and our shared mental model of what the
LLM should produce).

The puzzle recognizers were added in v0.3 slice J (issue #86, closes
#60). The starter enum, body-content table, and heading -> kind mapping
all gained puzzle entries; this file covers the new entries plus the
precedence rule (heading > body > unset) for the existing kinds.
"""

from __future__ import annotations

from typing import Optional

import pytest


# --------------------------------------------------------------------------
# Starter enum — sourced from references/beat-kind-classification.md and
# CONTEXT.md. The enum is open; this set is the documented starter values.
# --------------------------------------------------------------------------

STARTER_KINDS = frozenset(
    {
        "news",
        "handout",
        "character-moment",
        "set-piece",
        "clue",
        "escalation",
        "puzzle",
    }
)


# --------------------------------------------------------------------------
# Body-content classifier — mirrors the "Heuristic by prose shape" table
# in references/beat-kind-classification.md. Order matters: the table is
# documented as "apply in order — the first match wins". The puzzle row
# is placed above set-piece intentionally (per the reference file's
# precedence note).
# --------------------------------------------------------------------------


# Each entry is `(kind, list_of_lowercase_signal_substrings)`. Matches are
# case-insensitive substring matches against the Beat body. The order of
# this list is the precedence order.
BODY_CONTENT_RULES: list[tuple[str, list[str]]] = [
    (
        "clue",
        [
            "reveal",
            "discover",
            "find out",
            "the party learns that",
            "clue that",
        ],
    ),
    (
        "escalation",
        [
            "escalation",
            "if things go badly",
            "if the timer runs out",
            "back-pocket",
            "raise the stakes",
        ],
    ),
    (
        "puzzle",
        [
            "puzzle",
            "riddle",
            "the trick is",
            "the solution is",
            "to solve this",
            "the riddle is",
            "solving the",
        ],
    ),
    (
        "set-piece",
        [
            "set up",
            "set-piece",
            "ambush",
            "chase",
            "ritual",
            "heist",
        ],
    ),
    (
        "handout",
        [
            "give them",
            "hand the party",
            "they receive",
            "physical item",
        ],
    ),
    (
        "news",
        [
            "drop the news",
            "they hear",
            "messenger arrives",
            "rumor",
            "word reaches them",
            "poster",
        ],
    ),
]


def classify_by_body(body: str) -> Optional[str]:
    """Return the kind suggested by body-content signals, or None.

    Apply BODY_CONTENT_RULES in order — first signal hit wins.
    Returns None (unclassified) when no signal matches.

    The character-moment rule isn't in this list because its signal is
    structural (a named PC scoped attribution) rather than a substring
    match; that case is handled by the broader heuristic at the calling
    site (or surfaces as an ASK at staging review).
    """
    haystack = body.lower()
    for kind, signals in BODY_CONTENT_RULES:
        for signal in signals:
            if signal in haystack:
                return kind
    return None


# --------------------------------------------------------------------------
# Section-heading classifier — mirrors the "Heading -> kind mapping" table
# in the same reference. Matches an enclosing section heading (`##`, `###`,
# etc.) against the documented module-section conventions.
# --------------------------------------------------------------------------


# Each entry is `(kind, list_of_lowercase_heading_phrases)`. A match is a
# case-insensitive substring of the heading text (with the leading `#`
# markers and surrounding whitespace stripped).
SECTION_HEADING_RULES: list[tuple[str, list[str]]] = [
    (
        "set-piece",
        [
            "scenes",
            "set pieces",
            "set-pieces",
            "encounters",
            "random encounters",
            "wandering monsters",
        ],
    ),
    (
        "news",
        [
            "lore",
            "rumors",
            "tavern talk",
            "what the party hears",
            "news",
        ],
    ),
    (
        "handout",
        [
            "handouts",
            "player handouts",
            "props",
        ],
    ),
    (
        "clue",
        [
            "hidden information for the dm",
            "hidden information",
            "gm reveals",
            "adventure reveals",
        ],
    ),
    (
        "escalation",
        [
            "triggers",
            "escalations",
            "what happens if",
            "the clock",
            "if the party doesn't act",
        ],
    ),
    (
        "character-moment",
        [
            "personal hooks",
            "pc hooks",
            "spotlight beats",
        ],
    ),
    (
        "puzzle",
        [
            "puzzles",
            "riddles",
            "brain-teasers",
        ],
    ),
]


# Subsection-suffix recognizers: when a `###` (or deeper) heading names a
# specific puzzle / scene / clue by name, the suffix word is the kind
# signal. These run after the enclosing-section table and refine.
SUBSECTION_SUFFIX_RULES: list[tuple[str, list[str]]] = [
    (
        "puzzle",
        ["puzzle", "riddle"],
    ),
]


def _normalize_heading(heading: str) -> str:
    """Strip leading `#`s and whitespace, lowercase, collapse spaces."""
    text = heading.lstrip("#").strip().lower()
    # Drop a trailing `:` that authors sometimes add ("## Scenes:").
    if text.endswith(":"):
        text = text[:-1].rstrip()
    return text


def _contains_word(text: str, word: str) -> bool:
    """Case-insensitive whole-word match within `text`.

    Word boundaries are non-alphanumeric / non-`-` characters. This
    lets `"riddle"` match in `"### The Riddle of the Three Doors"` (as
    a token) without falsely matching `"riddler"` (suffix-extension).
    """
    text_lower = text.lower()
    word_lower = word.lower()
    start = 0
    while True:
        idx = text_lower.find(word_lower, start)
        if idx == -1:
            return False
        before_ok = idx == 0 or not (
            text_lower[idx - 1].isalnum() or text_lower[idx - 1] == "-"
        )
        end = idx + len(word_lower)
        after_ok = end == len(text_lower) or not (
            text_lower[end].isalnum() or text_lower[end] == "-"
        )
        # Allow a plural `s` after the word as a still-matching boundary.
        if not after_ok and end < len(text_lower) and text_lower[end] == "s":
            after_s = end + 1
            after_ok = after_s == len(text_lower) or not (
                text_lower[after_s].isalnum() or text_lower[after_s] == "-"
            )
        if before_ok and after_ok:
            return True
        start = idx + 1


def classify_by_heading(heading: str) -> Optional[str]:
    """Return the kind suggested by an enclosing section heading.

    The argument is the raw heading line (e.g., `"## Puzzles"` or
    `"### The Mirror Room Puzzle"`). Returns None when no rule matches.

    Matching is case-insensitive substring against the normalized
    heading text. Subsection-suffix rules ("Puzzle" / "Riddle"
    appearing as a word anywhere in a named subsection heading)
    refine an enclosing heading; they're applied by `classify` below
    when both signals are available.
    """
    text = _normalize_heading(heading)
    if not text:
        return None
    for kind, phrases in SECTION_HEADING_RULES:
        for phrase in phrases:
            if phrase in text:
                return kind
    # No top-level section match; check for a name-token recognizer
    # (e.g., "### The Mirror Room Puzzle" or "### The Riddle of the
    # Three Doors" with no enclosing "## Puzzles" section above —
    # the named puzzle / riddle is the signal).
    for kind, keywords in SUBSECTION_SUFFIX_RULES:
        for keyword in keywords:
            if _contains_word(text, keyword):
                return kind
    return None


# --------------------------------------------------------------------------
# Combined classifier — the precedence rule per
# references/beat-kind-classification.md "Module-section-heading
# classification (ingest-specific)" section.
#
#   1. Section heading (strongest signal)
#   2. Body content (fallback)
#   3. Unset (None) when neither yields a confident classification
#
# When the enclosing heading and a subsection heading disagree, the more
# specific (deeper) heading's signal wins per the "Subsection refinement"
# subsection of the reference.
# --------------------------------------------------------------------------


def classify(
    body: str,
    enclosing_heading: Optional[str] = None,
    subsection_heading: Optional[str] = None,
) -> Optional[str]:
    """Apply the documented precedence: heading > body > unset.

    `subsection_heading` is the nearest `###` (or deeper) heading above
    the Beat's source paragraph. `enclosing_heading` is the `##` section
    that contains it. When both are supplied and disagree, the
    subsection wins (subsection refinement).
    """
    # Subsection beats enclosing section when both supplied.
    if subsection_heading:
        sub_kind = classify_by_heading(subsection_heading)
        if sub_kind:
            return sub_kind
    if enclosing_heading:
        head_kind = classify_by_heading(enclosing_heading)
        if head_kind:
            return head_kind
    return classify_by_body(body)


# ==========================================================================
# Tests
# ==========================================================================


class TestStarterEnum:
    """The seven starter values documented in the reference + CONTEXT.md."""

    def test_puzzle_is_in_starter_enum(self) -> None:
        assert "puzzle" in STARTER_KINDS

    def test_existing_six_kinds_still_present(self) -> None:
        # Regression: slice J adds puzzle without removing any existing kind.
        for kind in (
            "news",
            "handout",
            "character-moment",
            "set-piece",
            "clue",
            "escalation",
        ):
            assert kind in STARTER_KINDS, (
                f"starter kind {kind!r} dropped — slice J should be "
                "additive only"
            )

    def test_starter_enum_size_is_seven(self) -> None:
        assert len(STARTER_KINDS) == 7


class TestPuzzleSectionHeadingRecognizers:
    """`## Puzzles`, `## Riddles`, and adventure-specific puzzle subheadings."""

    @pytest.mark.parametrize(
        "heading",
        [
            "## Puzzles",
            "## Riddles",
            "## Brain-Teasers",
            "### Puzzles",  # deeper depth, same word
            "## puzzles",  # case-insensitive
            "## Puzzles:",  # trailing colon tolerated
        ],
    )
    def test_top_level_puzzle_section_classifies_as_puzzle(
        self, heading: str
    ) -> None:
        assert classify_by_heading(heading) == "puzzle"

    @pytest.mark.parametrize(
        "heading",
        [
            "### The Mirror Room Puzzle",
            "### The Riddle of the Three Doors",
            "### Lock-Mechanism Puzzle",
            "#### The Pressure Plate Riddle",
        ],
    )
    def test_named_subsection_with_puzzle_suffix_classifies_as_puzzle(
        self, heading: str
    ) -> None:
        assert classify_by_heading(heading) == "puzzle"

    def test_extracted_beat_under_puzzles_section_gets_kind_puzzle(self) -> None:
        # Fixture: a beat extracted from prose under `## Puzzles`. The body
        # alone is descriptive ("a room with mirrored walls...") without
        # an obvious body-content signal. The heading is what classifies.
        body = (
            "The party enters a room with mirrored walls. Each mirror "
            "shows a different time of day. Touching the mirror that "
            "shows midnight opens the door to the next chamber."
        )
        assert classify(body, enclosing_heading="## Puzzles") == "puzzle"


class TestPuzzleBodyContentSignals:
    """Body-content signals per the reference's prose-shape table."""

    @pytest.mark.parametrize(
        "body",
        [
            "The trick is to read the runes in reverse.",
            "The solution is a five-letter word.",
            "To solve this, the party must light four braziers in order.",
            "The riddle is: what walks on four legs in the morning?",
            "A logic puzzle with three statues.",
            "Solving the lock requires the right sequence.",
        ],
    )
    def test_body_signals_fire_for_puzzle(self, body: str) -> None:
        assert classify_by_body(body) == "puzzle"

    def test_no_signal_returns_none(self) -> None:
        body = "The party walks down a hallway. Nothing interesting happens."
        assert classify_by_body(body) is None

    def test_body_classification_falls_through_when_no_heading(self) -> None:
        # No heading supplied; body classifier alone produces the answer.
        body = "The puzzle requires solving a riddle to proceed."
        assert classify(body) == "puzzle"


class TestPrecedenceHeadingBeatsBody:
    """Heading signal wins when both heading and body apply."""

    def test_heading_overrides_body_when_both_match_same_kind(self) -> None:
        # Both signals point at puzzle; the heading is what counts.
        body = "The trick is to step on the plates in the right order."
        assert (
            classify(body, enclosing_heading="## Puzzles") == "puzzle"
        )

    def test_heading_overrides_body_when_signals_disagree(self) -> None:
        # Body reads like a news drop ("they hear a rumor"); the heading
        # places it under Puzzles. Heading wins per the documented
        # precedence rule.
        body = "They hear a rumor that the mirror shows the past."
        assert (
            classify(body, enclosing_heading="## Puzzles") == "puzzle"
        )

    def test_subsection_overrides_enclosing_section(self) -> None:
        # `## Scenes` would classify as `set-piece`; the named
        # `### The Mirror Room Puzzle` subsection wins per the
        # Subsection refinement rule.
        body = "Set up the encounter so the party enters mid-conversation."
        assert (
            classify(
                body,
                enclosing_heading="## Scenes",
                subsection_heading="### The Mirror Room Puzzle",
            )
            == "puzzle"
        )

    def test_unset_when_neither_heading_nor_body_signal_applies(self) -> None:
        body = "The corridor turns left, then right, then opens into a room."
        assert classify(body, enclosing_heading="## Notes") is None


class TestExistingKindRecognizersStillWork:
    """Regression: existing kind recognizers must not regress."""

    @pytest.mark.parametrize(
        ("body", "expected_kind"),
        [
            (
                "The party learns that the mayor is funding the cult.",
                "clue",
            ),
            (
                "If things go badly, the reinforcements arrive.",
                "escalation",
            ),
            (
                "Set up an ambush at the bridge.",
                "set-piece",
            ),
            (
                "Hand the party a sealed letter from the duke.",
                "handout",
            ),
            (
                "A messenger arrives with word from the capital.",
                "news",
            ),
        ],
    )
    def test_existing_body_signals_unchanged(
        self, body: str, expected_kind: str
    ) -> None:
        assert classify_by_body(body) == expected_kind

    @pytest.mark.parametrize(
        ("heading", "expected_kind"),
        [
            ("## Scenes", "set-piece"),
            ("## Rumors", "news"),
            ("## Handouts", "handout"),
            ("## Hidden Information for the DM", "clue"),
            ("## Triggers", "escalation"),
            ("## Personal Hooks", "character-moment"),
        ],
    )
    def test_existing_heading_recognizers_unchanged(
        self, heading: str, expected_kind: str
    ) -> None:
        assert classify_by_heading(heading) == expected_kind


class TestPuzzlePrecedenceOverSetPiece:
    """Puzzle row is documented to win over set-piece when both match.

    The reference file's prose-shape table places `puzzle` above
    `set-piece` intentionally — a Beat whose body reads as both
    ("set up the Mirror Room puzzle") should land as `puzzle`.
    """

    def test_body_with_both_signals_classifies_as_puzzle(self) -> None:
        body = "Set up the Mirror Room puzzle so the party enters at dusk."
        assert classify_by_body(body) == "puzzle"

    def test_riddle_wins_over_ritual(self) -> None:
        body = "The riddle is woven into the ritual chant."
        assert classify_by_body(body) == "puzzle"
