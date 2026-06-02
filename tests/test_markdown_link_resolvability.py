"""Markdown link resolvability across SKILL.md prose, references/, docs/, and root.

Issue #115. Today `tests/test_plugin_manifest.py::TestRelativePathsInProse`
checks that the forbidden absolute-install-path form
(`~/.claude/skills/ttrpg-gm/...`) doesn't appear in skill or reference
prose, but it never confirms that the relative paths the prose *does*
use actually resolve to a real file on disk. A typo (`../references/foo`
when the file is at `../../references/foo`) or a rename that misses
some callsites still silently passes the existing discipline.

This test walks every `*.md` file under `skills/`, `references/`,
`docs/`, and the four documented root markdown files (`CLAUDE.md`,
`CONTEXT.md`, `README.md`, `DESIGN_NOTES.md`), extracts every
relative-path link it can spot — both standard `[text](path)` form and
bare backtick-quoted path citations like `` `../../references/foo.md` ``
— resolves the path against the containing file, and asserts the
target exists.

Two link shapes are extracted:

1. **Standard markdown links** — `[text](path)`. Absolute URLs
   (`http://`, `https://`, `mailto:`) and anchor-only fragments
   (`#foo`) are skipped. A `path#fragment` suffix is stripped before
   resolution.
2. **Bare backtick paths** — `` `path` `` where the path starts with
   `./` or `../` (an explicit-relative-path prefix). This catches the
   citation form skill prose uses for sibling-reference reads (e.g.,
   `` `../../references/extraction-pipeline.md` `` inline in prose, or
   `` `../docs/adr/0014-…md` `` from a `references/` file). Conservative
   on purpose: a bare backtick like `` `references/foo.md` `` in ADR
   prose is descriptive (citing where the file lives in the repo,
   *given* the repo layout) rather than a clickable reference from the
   ADR's own directory — those land as prose, not as broken links.
   Likewise `` `pcs/` `` names a campaign-side directory the agent
   creates lazily, not a plugin filesystem path.

Fenced code blocks (triple-backtick) are skipped — they hold sample
snippets (commit message templates, JSON, shell), not citations.

An allowlist accommodates intentional non-resolvable references (e.g.,
`<placeholder>` syntax). Each entry carries a comment explaining why.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Allowlist: intentional non-resolvable references.
#
# Each entry is a `(containing_md_path_relative_to_repo, link_target)`
# tuple — i.e., "this link from this file does not need to resolve."
# Add a comment per entry naming the reason. Keep this list short; the
# point of the test is to catch real bugs, not to paper over them.
# ---------------------------------------------------------------------------
ALLOWLIST: set[tuple[str, str]] = {
    # No entries today. Real exceptions land here with a comment per
    # entry naming why the link target legitimately does not resolve
    # (e.g., placeholder syntax inside a `<slug>` example).
}


# Markdown link form: `[text](target)`. The `text` may contain balanced
# brackets in practice but the repo's prose never nests; a non-greedy
# bracket body is sufficient. The target is anything up to the first
# unescaped `)`.
MD_LINK_RE = re.compile(r"\[(?P<text>[^\]]*)\]\((?P<target>[^)]+)\)")

# Bare backtick path: `` `<path>` ``. The path must not contain a
# backtick (so we don't span across code spans) and must not be empty.
BACKTICK_RE = re.compile(r"`(?P<path>[^`\n]+)`")

# Fenced code blocks: lines starting with three backticks open/close a
# fence. Content between fences is excluded from link extraction.
FENCE_RE = re.compile(r"^(?P<fence>`{3,}|~{3,})")

# URL schemes we never resolve as filesystem paths.
URL_PREFIXES = ("http://", "https://", "mailto:", "ftp://", "//")

# (No top-level-prefix allowlists are needed — `_looks_like_path_citation`
# below only treats explicit-relative-path bare-backtick content as a
# citation. Bare repo-root-relative paths like `` `references/foo.md` ``
# read as descriptive prose in this codebase, not as click targets; the
# author uses the `[text](path)` form when a clickable link is intended.)


def _scope_paths(repo_root: Path) -> list[Path]:
    """The set of `*.md` files this audit walks.

    Per #115: `skills/`, `references/`, `docs/`, and the four root
    markdown files. Excludes `tests/` (fixtures intentionally hold
    illustrative-but-invalid content) and any pytest cache directories.
    """
    paths: list[Path] = []
    for sub in ("skills", "references", "docs"):
        paths.extend((repo_root / sub).rglob("*.md"))
    for root_md in ("CLAUDE.md", "CONTEXT.md", "README.md", "DESIGN_NOTES.md"):
        candidate = repo_root / root_md
        if candidate.is_file():
            paths.append(candidate)
    return sorted(paths)


def _strip_fenced_code(text: str) -> str:
    """Return `text` with fenced code blocks blanked out (lines kept).

    We preserve line count and number so any later error message can
    still cite the original line number; only the content of fenced
    blocks is replaced with blank lines.
    """
    out_lines: list[str] = []
    in_fence = False
    fence_marker: str | None = None
    for line in text.splitlines():
        stripped = line.lstrip()
        match = FENCE_RE.match(stripped)
        if match:
            if not in_fence:
                in_fence = True
                fence_marker = match.group("fence")[0]
                out_lines.append("")
                continue
            # Closing fence must use the same character.
            if fence_marker is not None and stripped.startswith(fence_marker * 3):
                in_fence = False
                fence_marker = None
                out_lines.append("")
                continue
        if in_fence:
            out_lines.append("")
        else:
            out_lines.append(line)
    return "\n".join(out_lines)


def _looks_like_path_citation(candidate: str) -> bool:
    """Is this bare backtick content a markdown-link-style path citation?

    Conservative on purpose: only **explicit-relative-path** bare-
    backtick content is treated as a citation — i.e., content that
    starts with `./` or `../`. This is the form SKILL.md and references
    use when they want the agent to follow the path (e.g.,
    `` `../../references/extraction-pipeline.md` ``).

    Bare repo-root-relative paths (e.g., `` `references/foo.md` `` or
    `` `skills/ingest/SKILL.md` ``) appear in ADR prose as *descriptive*
    citations — they tell the reader where a file lives in the repo
    layout, not where to click from the current file. The repo's
    convention is that clickable citations use the `[text](path)` form
    and explicit `./`-prefixed bare backticks; un-prefixed bare-backtick
    paths are prose mentions and not flagged.

    Backtick content that holds spaces, placeholder `<…>` syntax, or
    starts with a CLI flag / shell sigil is rejected — those are
    inline-code samples, not paths.
    """
    if not candidate:
        return False
    if " " in candidate or "\t" in candidate:
        return False
    if "<" in candidate or ">" in candidate:
        return False
    if candidate.startswith(("-", "--", "$", "#", "!")):
        return False
    # Wiki-link syntax: `[[npcs/maren]]` — not a markdown-link citation,
    # and the inner path names a campaign-side file by convention.
    if candidate.startswith("[[") and candidate.endswith("]]"):
        return False

    # Only explicit-relative-prefix bare-backtick paths are treated as
    # citations the test should resolve.
    if candidate.startswith(("./", "../")):
        return True

    return False


def _resolve_target(md_path: Path, target: str, repo_root: Path) -> Path:
    """Resolve a link target relative to `md_path`, stripping any anchor."""
    # Drop fragment / query suffix.
    cleaned = target.split("#", 1)[0].split("?", 1)[0].strip()
    # Normalize trailing slash off — Path resolution treats `foo/` and
    # `foo` the same, but we want the existence check to accept either.
    resolved = (md_path.parent / cleaned).resolve()
    return resolved


def _extract_links(md_path: Path, repo_root: Path) -> list[tuple[int, str, str]]:
    """Return `[(line_number, raw_target, kind)]` for every link in `md_path`.

    `kind` is `"markdown"` or `"backtick"` for diagnostics.
    """
    text = md_path.read_text(encoding="utf-8")
    scrubbed = _strip_fenced_code(text)
    links: list[tuple[int, str, str]] = []
    for line_no, line in enumerate(scrubbed.splitlines(), start=1):
        for match in MD_LINK_RE.finditer(line):
            target = match.group("target").strip()
            if not target:
                continue
            if target.startswith(URL_PREFIXES):
                continue
            if target.startswith("#"):
                # Anchor within the same file; trust the prose.
                continue
            links.append((line_no, target, "markdown"))
        for match in BACKTICK_RE.finditer(line):
            candidate = match.group("path").strip()
            if not _looks_like_path_citation(candidate):
                continue
            links.append((line_no, candidate, "backtick"))
    return links


@pytest.fixture(scope="module")
def scoped_md_files(repo_root: Path) -> list[Path]:
    """Every `*.md` file the link audit walks."""
    return _scope_paths(repo_root)


class TestMarkdownLinkResolvability:
    """Every relative markdown link in scope resolves to a real file.

    The audit covers two link shapes (standard `[text](path)` and bare
    backtick `` `path` `` citations the agent reads as references), one
    scope (`skills/` + `references/` + `docs/` + the four documented
    root markdown files), and one rule (resolve against the containing
    file's directory; the target must exist on disk).
    """

    def test_every_relative_link_resolves(
        self,
        repo_root: Path,
        scoped_md_files: list[Path],
    ) -> None:
        broken: list[tuple[Path, int, str, str, Path]] = []
        for md_path in scoped_md_files:
            rel_md = md_path.relative_to(repo_root)
            for line_no, target, kind in _extract_links(md_path, repo_root):
                if (str(rel_md), target) in ALLOWLIST:
                    continue
                resolved = _resolve_target(md_path, target, repo_root)
                if not resolved.exists():
                    broken.append((rel_md, line_no, target, kind, resolved))

        if broken:
            lines = [
                f"  {rel}:{lineno} [{kind}] `{target}` -> "
                f"{resolved}"
                for rel, lineno, target, kind, resolved in broken
            ]
            pytest.fail(
                "Markdown link targets that do not resolve on disk "
                f"({len(broken)} broken):\n"
                + "\n".join(lines)
                + "\n\nEither fix the path in the source file, rename "
                "the target so the path resolves, or — if the link is "
                "intentionally non-resolvable (placeholder syntax, "
                "future-file citation) — add a `(source_path, target)` "
                "tuple to `ALLOWLIST` with a comment naming the reason."
            )

    def test_audit_actually_walked_files(
        self,
        scoped_md_files: list[Path],
    ) -> None:
        """Sanity check: the scope is non-empty.

        If a future refactor moves the documented directories or rename
        the root markdown files, this test fails loudly rather than
        silently passing with zero files walked.
        """
        assert scoped_md_files, (
            "Markdown link audit walked zero files. The scope "
            "(`skills/`, `references/`, `docs/`, root markdown) is "
            "expected to contain at least the SKILL.md files and the "
            "ADR set."
        )

    def test_audit_finds_at_least_one_link(
        self,
        repo_root: Path,
        scoped_md_files: list[Path],
    ) -> None:
        """Sanity check: link extraction isn't silently dropping everything.

        A regex regression that captured nothing would leave the main
        test trivially-passing. Confirm at least one link was extracted
        from the corpus.
        """
        total = 0
        for md_path in scoped_md_files:
            total += len(_extract_links(md_path, repo_root))
        assert total > 0, (
            "Link extraction returned zero links across the entire "
            "audit scope. The regex or fence-stripping logic likely "
            "regressed."
        )
