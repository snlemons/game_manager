"""Reference-Python coverage of the BidiLinkManager spec.

This file follows the v0.1 test convention: the reference Python below
is a thin near-translation of the bidirectional-link maintenance
algorithm that the SKILL.md prose in `/wrap-session`, `/prep-session`,
and `/ingest` will describe at runtime (downstream slices #37, #38, #39).
Skills perform the link updates inline via Edit / MultiEdit calls; this
reference impl is the executable spec they must agree with.

Per [ADR-0014](../docs/adr/0014-secrets-as-multi-container-lifecycle-objects.md),
every container listed in a Secret's `belongs_to:` carries a
`## Secrets` section in its body wiki-linking back to the Secret file.
The Secret file is the source of truth; the container's section is a
derived view the agent maintains on every Secret write.

Two operations covered here:

  - **`apply_belongs_to`** — given a Secret, ensure every container in
    its `belongs_to:` has a `## Secrets` section with the wiki-link.
    Idempotent: re-applying on an already-linked container is a no-op.
    The "back-reference present?" check accepts either canonical
    slug-path form (`[[secrets/<slug>]]`) or canonical-title
    display-name form (`[[<title>]]` where `<title>` is the Secret's
    H1) — v0.1/v0.2-era campaigns may carry display-name back-
    references and the linker must recognize them. The writer authors
    new back-references in canonical slug-path form only.
  - **`lint`** — walk the campaign, find three failure modes:
      * **orphan wiki-link** — a `[[secrets/<slug>]]` link in some
        container's `## Secrets` section pointing at a non-existent
        Secret file.
      * **missing back-reference** — a Secret lists `npcs/maren.md` in
        `belongs_to:` but `npcs/maren.md` has no `## Secrets` section
        (or has one but doesn't link back to the Secret in either
        slug-path or display-name form).
      * **cross-kind name collision** — a container body contains a
        display-name wiki-link whose normalized title matches the H1
        of more than one container across kind boundaries
        (e.g. `[[Lore of Lurue]]` could refer to either
        `adventures/lore-of-lurue/adventure.md` or
        `items/lore-of-lurue.md`); the link is ambiguous and surfaces
        for GM resolution.

The lint operation is the agent's reconciliation surface when GM hand-
edits break the symmetry; `apply_belongs_to` is the maintenance path
that keeps it intact on every Secret write.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import pytest
import yaml


# ---------------------------------------------------------------------------
# Reference implementation — mirrors ADR-0014 ("Bidirectional linking").
# Kept in-file per the v0.1 convention.
# ---------------------------------------------------------------------------


SECRETS_HEADING = "## Secrets"
WIKI_LINK_RE = re.compile(r"\[\[secrets/([^\[\]\|\s]+?)\]\]")
# Any wiki-link, slug-path or display-name, possibly with a piped label.
# Group 1 captures the link target text (the part before any `|`).
ANY_WIKI_LINK_RE = re.compile(r"\[\[([^\[\]\|]+?)(?:\|[^\[\]]+)?\]\]")
H1_RE = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)


def _normalize_title(title: str) -> str:
    """Normalize a title for case-insensitive, whitespace-collapsed match."""
    return " ".join(title.strip().lower().split())


def _read_h1(path: Path) -> str:
    """Return the first H1 heading from a file, or empty string if none.

    Skips frontmatter via the same `---\\n...---\\n` delimiters used
    elsewhere; the H1 is read from the body.
    """
    if not path.is_file():
        return ""
    text = path.read_text(encoding="utf-8")
    _, body = _split_frontmatter(text)
    m = H1_RE.search(body)
    return m.group(1).strip() if m else ""


@dataclass(frozen=True)
class LintFinding:
    """One bidi-link drift case the linter surfaces.

    `kind` is `"orphan"` (a container wiki-links to a nonexistent
    Secret) or `"missing-back-reference"` (a Secret claims a container
    but the container has no `## Secrets` link back).
    """

    kind: str
    container: str  # Container path relative to campaign root.
    secret_slug: str  # The slug at issue.
    message: str


# --- Frontmatter helper (same minimal parser used in test_frontmatter.py) ---


def _split_frontmatter(text: str) -> tuple[dict, str]:
    if not text.startswith("---\n"):
        return {}, text
    closing = text.find("\n---\n", 4)
    if closing == -1:
        return {}, text
    raw = text[4:closing]
    body = text[closing + len("\n---\n") :]
    parsed = yaml.safe_load(raw) or {}
    if not isinstance(parsed, dict):
        return {}, text
    return parsed, body


def _container_file_path(campaign_root: Path, container: str) -> Path:
    """Resolve a `belongs_to:` entry to the file the linker should edit.

    For a Reference-note container (`npcs/maren.md`, `locations/foo.md`,
    etc.) the file IS the container. For an Adventure container
    (`adventures/the-prism/`, ending in `/`) the file is
    `adventures/<slug>/adventure.md` per the Adventure schema.
    """
    if container.endswith("/"):
        # Directory-form container: Adventures, the only kind today.
        slug = container.rstrip("/").split("/", 1)[1]
        head = container.rstrip("/").split("/", 1)[0]
        return campaign_root / head / slug / "adventure.md"
    return campaign_root / container


def _has_back_reference(
    body: str, secret_slug: str, secret_title: str = ""
) -> bool:
    """True if the body contains a wiki-link to the given Secret.

    Accepts two forms (per `references/bidi-link-maintenance.md`):
      * canonical slug-path — `[[secrets/<slug>]]`
      * canonical-title display-name — `[[<title>]]` where <title>
        normalizes (case-insensitive, whitespace-collapsed) to the
        Secret's H1.

    The spec requires the link to live under a `## Secrets` heading,
    but the minimal-reference linter accepts any body-position match
    (the section grouping is editorial). The link presence is the
    load-bearing property. If `secret_title` is empty (caller didn't
    look it up), only the slug-path form matches — the display-name
    path silently degrades to no-match, which is safe (worst case the
    writer adds a slug-path bullet next to an unrecognized display-
    name one; the spec's accept-either-form rule then applies on the
    next pass).
    """
    for match in WIKI_LINK_RE.finditer(body):
        if match.group(1) == secret_slug:
            return True
    if secret_title:
        norm_title = _normalize_title(secret_title)
        for match in ANY_WIKI_LINK_RE.finditer(body):
            target = match.group(1)
            # Skip slug-path-form links — already covered above.
            if "/" in target:
                continue
            if _normalize_title(target) == norm_title:
                return True
    return False


def _ensure_secrets_section(
    body: str, secret_slug: str, summary: str, secret_title: str = ""
) -> str:
    """Return a body that includes a `## Secrets` section linking the slug.

    Idempotent: if the body already wiki-links the slug **in either
    canonical slug-path form or canonical-title display-name form**,
    returns the body unchanged. Otherwise appends a `## Secrets`
    section (or adds an entry to an existing one) with a single bullet
    of the form `- [[secrets/<slug>]] — <summary>` — canonical slug-
    path is the only write form.
    """
    if _has_back_reference(body, secret_slug, secret_title):
        return body
    bullet = f"- [[secrets/{secret_slug}]] — {summary}"
    if SECRETS_HEADING in body:
        # Insert the bullet at the end of the existing section. We find
        # the line after the heading and walk until we hit the next H2 or
        # EOF; the bullet lands at the end of the section.
        lines = body.splitlines(keepends=False)
        out: list[str] = []
        i = 0
        while i < len(lines):
            out.append(lines[i])
            if lines[i].strip() == SECRETS_HEADING:
                # Collect existing section content up to next H2 / EOF.
                j = i + 1
                section_end = len(lines)
                while j < len(lines):
                    if lines[j].startswith("## ") and lines[j].strip() != SECRETS_HEADING:
                        section_end = j
                        break
                    j += 1
                # Append intervening lines, then the new bullet before
                # the next section starts.
                for k in range(i + 1, section_end):
                    out.append(lines[k])
                out.append(bullet)
                i = section_end
                continue
            i += 1
        result = "\n".join(out)
        if body.endswith("\n") and not result.endswith("\n"):
            result += "\n"
        return result
    # No existing section — append a fresh one.
    suffix = "" if body.endswith("\n") else "\n"
    return body + suffix + f"\n{SECRETS_HEADING}\n\n{bullet}\n"


def apply_belongs_to(
    campaign_root: Path,
    secret_slug: str,
    belongs_to: list[str],
    summary: str = "",
) -> dict[str, bool]:
    """For each container in `belongs_to`, ensure it back-links the Secret.

    Returns a dict mapping container path -> bool, where True means the
    container's file was modified (back-link added) and False means the
    file was already correct (idempotent no-op).

    Raises `FileNotFoundError` if any container file is missing — the
    SKILL.md prose surfaces that to the GM rather than silently
    creating containers from a Secret write.
    """
    summary = summary or "see Secret file for details"
    # Look up the Secret's H1 title — needed to recognize existing
    # display-name back-references in v0.1/v0.2-era campaigns. If the
    # Secret file doesn't exist yet (Phase 3 staging may apply against
    # not-yet-written Secrets), degrade to slug-path-only recognition;
    # the writer's slug-path bullet still lands and a subsequent pass
    # will see it.
    secret_path = campaign_root / "secrets" / f"{secret_slug}.md"
    secret_title = _read_h1(secret_path)
    results: dict[str, bool] = {}
    for container in belongs_to:
        path = _container_file_path(campaign_root, container)
        if not path.is_file():
            raise FileNotFoundError(
                f"container file does not exist: {path} (referenced by "
                f"belongs_to entry {container!r})"
            )
        original = path.read_text(encoding="utf-8")
        fm, body = _split_frontmatter(original)
        new_body = _ensure_secrets_section(
            body, secret_slug, summary, secret_title
        )
        if new_body == body:
            results[container] = False
            continue
        # Rebuild file: preserve frontmatter exactly if present.
        if original.startswith("---\n"):
            closing = original.find("\n---\n", 4)
            if closing != -1:
                fm_block = original[: closing + len("\n---\n")]
                path.write_text(fm_block + new_body, encoding="utf-8")
            else:
                path.write_text(new_body, encoding="utf-8")
        else:
            path.write_text(new_body, encoding="utf-8")
        results[container] = True
    return results


def _enumerate_secret_slugs(campaign_root: Path) -> set[str]:
    """All Secret slugs from `<campaign>/secrets/*.md`."""
    secrets_dir = campaign_root / "secrets"
    if not secrets_dir.is_dir():
        return set()
    return {
        p.stem
        for p in secrets_dir.iterdir()
        if p.is_file() and p.name.endswith(".md")
    }


def _enumerate_containers_with_secrets_links(
    campaign_root: Path,
) -> dict[Path, set[str]]:
    """Walk every potential container file, collect Secret slugs each links.

    Containers are files under the documented non-ephemeral folder roots
    (`adventures/`, `npcs/`, `pcs/`, `locations/`, `factions/`,
    `items/`). For Adventures, the container file is
    `adventures/<slug>/adventure.md` per the Adventure schema; nested
    files are not containers.
    """
    out: dict[Path, set[str]] = {}
    for folder in ("npcs", "pcs", "locations", "factions", "items"):
        d = campaign_root / folder
        if not d.is_dir():
            continue
        for p in d.iterdir():
            if not p.is_file() or not p.name.endswith(".md"):
                continue
            text = p.read_text(encoding="utf-8")
            _, body = _split_frontmatter(text)
            slugs = {m.group(1) for m in WIKI_LINK_RE.finditer(body)}
            out[p] = slugs
    adv_dir = campaign_root / "adventures"
    if adv_dir.is_dir():
        for sub in adv_dir.iterdir():
            adv_md = sub / "adventure.md"
            if not adv_md.is_file():
                continue
            text = adv_md.read_text(encoding="utf-8")
            _, body = _split_frontmatter(text)
            slugs = {m.group(1) for m in WIKI_LINK_RE.finditer(body)}
            out[adv_md] = slugs
    return out


def _enumerate_container_display_link_titles(
    campaign_root: Path,
) -> dict[Path, set[str]]:
    """Walk every container file, collect normalized display-name wiki-link
    titles in the body (non-slug-path-form, non-piped link targets).

    Used by both the missing-back-reference recognizer (to accept
    `[[<Secret title>]]` as a valid back-reference) and the cross-kind
    collision detector (to surface ambiguous display-name links).

    A "display-name" link is a wiki-link whose target contains no `/`
    (excluding slug-path-form `[[kind/slug]]` links and piped
    `[[kind/slug|label]]` links, where the link target is the part
    before the `|`).
    """
    out: dict[Path, set[str]] = {}
    container_paths: list[Path] = []
    for folder in ("npcs", "pcs", "locations", "factions", "items"):
        d = campaign_root / folder
        if not d.is_dir():
            continue
        for p in d.iterdir():
            if p.is_file() and p.name.endswith(".md"):
                container_paths.append(p)
    adv_dir = campaign_root / "adventures"
    if adv_dir.is_dir():
        for sub in adv_dir.iterdir():
            adv_md = sub / "adventure.md"
            if adv_md.is_file():
                container_paths.append(adv_md)
    for p in container_paths:
        text = p.read_text(encoding="utf-8")
        _, body = _split_frontmatter(text)
        titles: set[str] = set()
        for m in ANY_WIKI_LINK_RE.finditer(body):
            target = m.group(1)
            if "/" in target:
                continue  # slug-path form, not a display-name link
            titles.add(_normalize_title(target))
        out[p] = titles
    return out


def _enumerate_container_titles(
    campaign_root: Path,
) -> dict[str, list[tuple[Path, str]]]:
    """Build the title index: normalized H1 -> list of (path, kind) pairs.

    Walks every container file (Reference notes + `adventures/<slug>/
    adventure.md`), reads its H1, and groups by normalized title.
    Used by the cross-kind collision detector to spot titles that
    resolve ambiguously across kind directories.
    """
    out: dict[str, list[tuple[Path, str]]] = {}
    kinds = [
        ("npcs", "npc"),
        ("pcs", "pc"),
        ("locations", "location"),
        ("factions", "faction"),
        ("items", "item"),
    ]
    for folder, kind in kinds:
        d = campaign_root / folder
        if not d.is_dir():
            continue
        for p in d.iterdir():
            if not p.is_file() or not p.name.endswith(".md"):
                continue
            title = _read_h1(p)
            if not title:
                continue
            out.setdefault(_normalize_title(title), []).append((p, kind))
    adv_dir = campaign_root / "adventures"
    if adv_dir.is_dir():
        for sub in adv_dir.iterdir():
            adv_md = sub / "adventure.md"
            if not adv_md.is_file():
                continue
            title = _read_h1(adv_md)
            if not title:
                continue
            out.setdefault(_normalize_title(title), []).append(
                (adv_md, "adventure")
            )
    return out


def lint(campaign_root: Path) -> list[LintFinding]:
    """Return every bidi-link drift case in the campaign.

    Three categories surfaced:
      * `"orphan"` — container links a Secret slug that has no
        corresponding `secrets/<slug>.md` file.
      * `"missing-back-reference"` — a Secret's `belongs_to:` claims a
        container, but the container's body has no wiki-link back to
        the Secret in either canonical slug-path or canonical-title
        display-name form.
      * `"cross-kind-collision"` — a container body contains a
        display-name wiki-link (`[[<title>]]`, non-slug-path form)
        whose normalized title matches the H1 of more than one
        container across kind boundaries; the link is ambiguous.
    """
    findings: list[LintFinding] = []
    secret_slugs = _enumerate_secret_slugs(campaign_root)
    container_links = _enumerate_containers_with_secrets_links(campaign_root)
    display_links = _enumerate_container_display_link_titles(campaign_root)

    # Look up every Secret's H1 title so the missing-back-reference
    # check can recognize `[[<Secret title>]]` display-name back-refs.
    secrets_dir = campaign_root / "secrets"
    secret_titles: dict[str, str] = {}
    if secrets_dir.is_dir():
        for sp in secrets_dir.iterdir():
            if sp.is_file() and sp.name.endswith(".md"):
                title = _read_h1(sp)
                if title:
                    secret_titles[sp.stem] = _normalize_title(title)

    # 1. Orphan wiki-links: container links a slug with no file.
    for container_path, linked_slugs in container_links.items():
        rel = container_path.relative_to(campaign_root).as_posix()
        for slug in sorted(linked_slugs):
            if slug not in secret_slugs:
                findings.append(
                    LintFinding(
                        kind="orphan",
                        container=rel,
                        secret_slug=slug,
                        message=(
                            f"{rel} wiki-links [[secrets/{slug}]] but no "
                            f"secrets/{slug}.md exists; the container is "
                            "referencing a deleted or renamed Secret."
                        ),
                    )
                )

    # 2. Missing back-references: Secret claims a container, container
    #    doesn't link back. Accept either canonical slug-path or
    #    canonical-title display-name form.
    if secrets_dir.is_dir():
        for sp in sorted(
            (p for p in secrets_dir.iterdir() if p.name.endswith(".md")),
            key=lambda p: p.name,
        ):
            text = sp.read_text(encoding="utf-8")
            fm, _ = _split_frontmatter(text)
            slug = sp.stem
            norm_title = secret_titles.get(slug, "")
            for container in fm.get("belongs_to", []) or []:
                container_path = _container_file_path(
                    campaign_root, str(container)
                )
                if not container_path.is_file():
                    findings.append(
                        LintFinding(
                            kind="missing-back-reference",
                            container=str(container),
                            secret_slug=slug,
                            message=(
                                f"secrets/{slug}.md belongs_to {container!r} "
                                "but that container file does not exist."
                            ),
                        )
                    )
                    continue
                linked = container_links.get(container_path, set())
                display_titles = display_links.get(container_path, set())
                has_slug_back_ref = slug in linked
                has_display_back_ref = (
                    bool(norm_title) and norm_title in display_titles
                )
                if not has_slug_back_ref and not has_display_back_ref:
                    rel = container_path.relative_to(
                        campaign_root
                    ).as_posix()
                    findings.append(
                        LintFinding(
                            kind="missing-back-reference",
                            container=rel,
                            secret_slug=slug,
                            message=(
                                f"secrets/{slug}.md belongs_to {container!r} "
                                f"but {rel} has no `## Secrets` wiki-link "
                                "back to the Secret."
                            ),
                        )
                    )

    # 3. Cross-kind name collisions: display-name wiki-links whose
    #    title resolves to more than one container across kind
    #    boundaries.
    container_titles = _enumerate_container_titles(campaign_root)
    collision_titles = {
        title: candidates
        for title, candidates in container_titles.items()
        if len({kind for _, kind in candidates}) > 1
    }
    for container_path, used_titles in display_links.items():
        rel = container_path.relative_to(campaign_root).as_posix()
        for norm_title in sorted(used_titles):
            if norm_title not in collision_titles:
                continue
            candidates = collision_titles[norm_title]
            candidate_paths = sorted(
                c.relative_to(campaign_root).as_posix()
                for c, _ in candidates
            )
            # Re-read the link's original-case title from the source
            # body for the message — the reader is more forgiving of
            # case-preserved quoting than of the normalized form.
            text = container_path.read_text(encoding="utf-8")
            _, body = _split_frontmatter(text)
            original_title = norm_title
            for m in ANY_WIKI_LINK_RE.finditer(body):
                target = m.group(1)
                if "/" in target:
                    continue
                if _normalize_title(target) == norm_title:
                    original_title = target.strip()
                    break
            findings.append(
                LintFinding(
                    kind="cross-kind-collision",
                    container=rel,
                    secret_slug="",
                    message=(
                        f"`[[{original_title}]]` in {rel} could refer to "
                        + " or ".join(candidate_paths)
                        + ". Pick one, or rewrite to slug-path form."
                    ),
                )
            )
    return findings


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def secrets_fixture_src(fixtures_dir: Path) -> Path:
    """Path to the static `secrets/` fixture source tree."""
    return fixtures_dir / "secrets"


@pytest.fixture
def secrets_fixture(tmp_path: Path, secrets_fixture_src: Path) -> Path:
    """A freshly materialized writable copy of the secrets fixture.

    Both apply_belongs_to and the lint mutation paths need a fresh tmp
    copy per test so one test's writes don't pollute another's view of
    the fixture.
    """
    import shutil

    dest = tmp_path / "campaign"
    shutil.copytree(secrets_fixture_src, dest)
    return dest


# ---------------------------------------------------------------------------
# Tests — apply_belongs_to
# ---------------------------------------------------------------------------


class TestApplyBelongsTo:
    """`apply_belongs_to` writes back-references and is idempotent on re-run."""

    def test_adds_missing_back_reference(
        self, secrets_fixture: Path
    ) -> None:
        # `npcs/jhera.md` is the intentional lint case: it's in
        # `secrets/jhera-survived.md`'s belongs_to but has no `## Secrets`
        # section. apply_belongs_to must add the link.
        jhera = secrets_fixture / "npcs" / "jhera.md"
        before = jhera.read_text(encoding="utf-8")
        assert SECRETS_HEADING not in before, (
            "fixture precondition: npcs/jhera.md must start without a "
            "Secrets section to exercise the add-from-scratch path"
        )

        result = apply_belongs_to(
            secrets_fixture,
            secret_slug="jhera-survived",
            belongs_to=["npcs/jhera.md", "factions/silent-court.md"],
            summary="the purge was incomplete",
        )

        after = jhera.read_text(encoding="utf-8")
        assert "[[secrets/jhera-survived]]" in after, (
            "apply_belongs_to did not add the back-link to npcs/jhera.md"
        )
        assert SECRETS_HEADING in after
        assert result["npcs/jhera.md"] is True, (
            "jhera.md should have been modified"
        )
        # factions/silent-court.md was already correct — should be a no-op.
        assert result["factions/silent-court.md"] is False, (
            "factions/silent-court.md already had the back-link; "
            "apply_belongs_to should report no-modification"
        )

    def test_is_idempotent_on_rerun(
        self, secrets_fixture: Path
    ) -> None:
        # First call adds the back-link to jhera.md; second call must
        # report no change AND leave the file byte-identical.
        apply_belongs_to(
            secrets_fixture,
            secret_slug="jhera-survived",
            belongs_to=["npcs/jhera.md"],
            summary="the purge was incomplete",
        )
        jhera = secrets_fixture / "npcs" / "jhera.md"
        first = jhera.read_bytes()

        result = apply_belongs_to(
            secrets_fixture,
            secret_slug="jhera-survived",
            belongs_to=["npcs/jhera.md"],
            summary="the purge was incomplete",
        )
        assert result["npcs/jhera.md"] is False, (
            "second apply_belongs_to should be a no-op; got a write"
        )
        assert jhera.read_bytes() == first, (
            "second apply_belongs_to changed bytes on disk — operation "
            "is not idempotent"
        )

    def test_already_correct_container_is_noop(
        self, secrets_fixture: Path
    ) -> None:
        # `npcs/maren.md` already back-links the Maren-spy Secret;
        # apply_belongs_to must not touch the file at all.
        maren = secrets_fixture / "npcs" / "maren.md"
        before = maren.read_bytes()
        result = apply_belongs_to(
            secrets_fixture,
            secret_slug="maren-is-the-spy",
            belongs_to=["npcs/maren.md"],
            summary="cult's inside contact",
        )
        assert result["npcs/maren.md"] is False
        assert maren.read_bytes() == before

    def test_multi_container_apply_writes_each_missing_link(
        self, secrets_fixture: Path
    ) -> None:
        # Apply against a fresh Secret-like slug to a multi-container
        # belongs_to list. Both containers should be written.
        # Use existing container files but a novel slug so neither
        # already has the link.
        result = apply_belongs_to(
            secrets_fixture,
            secret_slug="new-test-secret",
            belongs_to=[
                "npcs/halric.md",
                "locations/old-temple.md",
            ],
            summary="a brand new Secret for the test",
        )
        assert result["npcs/halric.md"] is True
        assert result["locations/old-temple.md"] is True

        halric = (secrets_fixture / "npcs" / "halric.md").read_text(
            encoding="utf-8"
        )
        temple = (
            secrets_fixture / "locations" / "old-temple.md"
        ).read_text(encoding="utf-8")
        assert "[[secrets/new-test-secret]]" in halric
        assert "[[secrets/new-test-secret]]" in temple
        # Pre-existing Secrets section on the temple must be preserved.
        assert "[[secrets/vault-key-in-temple]]" in temple, (
            "apply_belongs_to overwrote the pre-existing Secret link "
            "on locations/old-temple.md — must preserve existing entries"
        )

    def test_adventure_directory_container_resolves_to_adventure_md(
        self, secrets_fixture: Path
    ) -> None:
        # `adventures/the-prism/` is the canonical container form for
        # Adventures; the linker must resolve it to
        # `adventures/the-prism/adventure.md`.
        # Use a novel slug so the operation is exercised even though
        # the.adventure.md already has the original Secrets.
        result = apply_belongs_to(
            secrets_fixture,
            secret_slug="prism-novel-test",
            belongs_to=["adventures/the-prism/"],
            summary="test entry",
        )
        assert result["adventures/the-prism/"] is True
        adv = (
            secrets_fixture / "adventures" / "the-prism" / "adventure.md"
        ).read_text(encoding="utf-8")
        assert "[[secrets/prism-novel-test]]" in adv

    def test_missing_container_file_raises(
        self, secrets_fixture: Path
    ) -> None:
        with pytest.raises(FileNotFoundError):
            apply_belongs_to(
                secrets_fixture,
                secret_slug="any",
                belongs_to=["npcs/does-not-exist.md"],
            )


# ---------------------------------------------------------------------------
# Tests — lint
# ---------------------------------------------------------------------------


class TestLint:
    """`lint` finds orphan links and missing back-references in the fixture.

    The fixture has been crafted with exactly two intentional drift cases:
      1. `npcs/orin.md` contains an orphan wiki-link to
         `[[secrets/orin-betrayed-us]]` (no such Secret file).
      2. `npcs/jhera.md` is in `secrets/jhera-survived.md`'s belongs_to
         but has no `## Secrets` section linking back.

    Everything else in the fixture is internally consistent; the lint
    must find these two cases and only these two.
    """

    def test_finds_orphan_wiki_link(self, secrets_fixture: Path) -> None:
        findings = lint(secrets_fixture)
        orphans = [f for f in findings if f.kind == "orphan"]
        assert len(orphans) == 1, (
            f"expected exactly one orphan finding; got {orphans}"
        )
        f = orphans[0]
        assert f.container == "npcs/orin.md"
        assert f.secret_slug == "orin-betrayed-us"

    def test_finds_missing_back_reference(
        self, secrets_fixture: Path
    ) -> None:
        findings = lint(secrets_fixture)
        missing = [
            f for f in findings if f.kind == "missing-back-reference"
        ]
        assert len(missing) == 1, (
            f"expected exactly one missing-back-reference finding; "
            f"got {missing}"
        )
        f = missing[0]
        assert f.container == "npcs/jhera.md"
        assert f.secret_slug == "jhera-survived"

    def test_total_findings_match_fixture_drift_count(
        self, secrets_fixture: Path
    ) -> None:
        # Belt-and-suspenders: the fixture has exactly two drift cases.
        # If new findings appear, either the fixture grew a new drift
        # (update the fixture README) or the linter false-positived
        # (the bug to surface).
        findings = lint(secrets_fixture)
        assert len(findings) == 2, (
            f"expected exactly two lint findings against the crafted "
            f"fixture; got {len(findings)}:\n"
            + "\n".join(f"  - {f.kind}: {f.message}" for f in findings)
        )

    def test_clean_after_apply_belongs_to_heals_missing_back_reference(
        self, secrets_fixture: Path
    ) -> None:
        # Healing the missing back-reference via apply_belongs_to should
        # remove that lint finding (the orphan one is unrelated and
        # remains).
        apply_belongs_to(
            secrets_fixture,
            secret_slug="jhera-survived",
            belongs_to=["npcs/jhera.md"],
            summary="the purge was incomplete",
        )
        findings = lint(secrets_fixture)
        missing = [
            f for f in findings if f.kind == "missing-back-reference"
        ]
        assert missing == [], (
            "apply_belongs_to did not clear the missing-back-reference "
            f"finding; still: {missing}"
        )
        # Orphan finding still there — it's unrelated.
        orphans = [f for f in findings if f.kind == "orphan"]
        assert len(orphans) == 1

    def test_returns_empty_when_no_secrets_dir(
        self, tmp_path: Path
    ) -> None:
        # A campaign with no `secrets/` directory has nothing to lint.
        assert lint(tmp_path) == []

    def test_finding_message_is_actionable(
        self, secrets_fixture: Path
    ) -> None:
        # Every finding should carry a self-contained message naming
        # the container path and (for orphan / missing-back-reference)
        # the Secret slug. The GM reading the lint output needs the
        # file path to act on it.
        for f in lint(secrets_fixture):
            assert f.container in f.message, (
                f"finding message {f.message!r} does not name the "
                f"container {f.container!r}"
            )
            if f.secret_slug:
                assert f.secret_slug in f.message, (
                    f"finding message {f.message!r} does not name the "
                    f"secret slug {f.secret_slug!r}"
                )


# ---------------------------------------------------------------------------
# Tests — display-name (canonical-title) back-reference recognition
# (Issue #70: campaigns in v0.1/v0.2 wrote `[[<Secret title>]]` rather than
# `[[secrets/<slug>]]`. The linker accepts either; the writer continues to
# author canonical slug-path form only.)
# ---------------------------------------------------------------------------


class TestDisplayNameBackReferenceRecognition:
    """`apply_belongs_to` and `lint` recognize display-name back-references."""

    def test_apply_belongs_to_is_noop_on_display_name_back_reference(
        self, secrets_fixture: Path, tmp_path: Path
    ) -> None:
        # Fixture: write a Secret with H1 "The Secret Title" and an
        # NPC container whose body already back-references the Secret
        # in display-name form `[[The Secret Title]]`. apply_belongs_to
        # must recognize it and NOT add a duplicate slug-path bullet.
        secret_path = secrets_fixture / "secrets" / "the-display-secret.md"
        secret_path.write_text(
            "---\n"
            "status: hidden\n"
            "belongs_to:\n"
            "  - npcs/halric.md\n"
            "revealed_by: []\n"
            "---\n"
            "\n"
            "# The Secret Title\n"
            "\n"
            "Body of the Secret.\n",
            encoding="utf-8",
        )
        # Overwrite halric.md with a display-name back-reference.
        halric = secrets_fixture / "npcs" / "halric.md"
        halric.write_text(
            "# Halric\n"
            "\n"
            "An NPC with a display-name back-reference.\n"
            "\n"
            "## Secrets\n"
            "\n"
            "- [[The Secret Title]]\n",
            encoding="utf-8",
        )
        before = halric.read_bytes()

        result = apply_belongs_to(
            secrets_fixture,
            secret_slug="the-display-secret",
            belongs_to=["npcs/halric.md"],
            summary="display-form back-ref test",
        )
        assert result["npcs/halric.md"] is False, (
            "apply_belongs_to should recognize the display-name "
            "back-reference and report no-modification"
        )
        assert halric.read_bytes() == before, (
            "apply_belongs_to wrote bytes when the display-name "
            "back-reference already satisfied the symmetry"
        )

    def test_writer_authors_canonical_slug_path_form(
        self, secrets_fixture: Path
    ) -> None:
        # When NO back-reference exists, the writer must add one in
        # canonical slug-path form (never display-name form), per the
        # `references/bidi-link-maintenance.md` step-6 rule.
        secret_path = (
            secrets_fixture / "secrets" / "writer-form-test.md"
        )
        secret_path.write_text(
            "---\n"
            "status: hidden\n"
            "belongs_to:\n"
            "  - npcs/halric.md\n"
            "revealed_by: []\n"
            "---\n"
            "\n"
            "# Writer Form Test Title\n"
            "\n"
            "Body.\n",
            encoding="utf-8",
        )
        apply_belongs_to(
            secrets_fixture,
            secret_slug="writer-form-test",
            belongs_to=["npcs/halric.md"],
            summary="canonical slug-path bullet",
        )
        halric_after = (
            secrets_fixture / "npcs" / "halric.md"
        ).read_text(encoding="utf-8")
        # The bullet must use slug-path form, not display-name form.
        assert "[[secrets/writer-form-test]]" in halric_after, (
            "writer did not author the canonical slug-path bullet"
        )
        assert "[[Writer Form Test Title]]" not in halric_after, (
            "writer authored a display-name bullet — must use slug-path "
            "form only per references/bidi-link-maintenance.md step 6"
        )

    def test_lint_accepts_display_name_back_reference_as_satisfying(
        self, secrets_fixture: Path
    ) -> None:
        # A Secret whose claimed container back-references it via
        # display-name form should NOT show up as a missing-back-
        # reference lint finding.
        secret_path = (
            secrets_fixture / "secrets" / "display-form-ok.md"
        )
        secret_path.write_text(
            "---\n"
            "status: hidden\n"
            "belongs_to:\n"
            "  - npcs/halric.md\n"
            "revealed_by: []\n"
            "---\n"
            "\n"
            "# Display Form Is Fine\n"
            "\n"
            "Body.\n",
            encoding="utf-8",
        )
        halric = secrets_fixture / "npcs" / "halric.md"
        halric.write_text(
            "# Halric\n"
            "\n"
            "## Secrets\n"
            "\n"
            "- [[Display Form Is Fine]]\n",
            encoding="utf-8",
        )
        findings = lint(secrets_fixture)
        missing = [
            f
            for f in findings
            if f.kind == "missing-back-reference"
            and f.secret_slug == "display-form-ok"
        ]
        assert missing == [], (
            f"lint flagged display-name back-reference as missing: "
            f"{missing}"
        )

    def test_mixed_form_campaign_idempotency(
        self, secrets_fixture: Path
    ) -> None:
        # Two containers in the same Secret's belongs_to: one with
        # display-name form, one with slug-path form. apply_belongs_to
        # must be a no-op against both.
        secret_path = (
            secrets_fixture / "secrets" / "mixed-form-secret.md"
        )
        secret_path.write_text(
            "---\n"
            "status: hidden\n"
            "belongs_to:\n"
            "  - npcs/halric.md\n"
            "  - locations/old-temple.md\n"
            "revealed_by: []\n"
            "---\n"
            "\n"
            "# Mixed Form Secret\n"
            "\n"
            "Body.\n",
            encoding="utf-8",
        )
        halric = secrets_fixture / "npcs" / "halric.md"
        halric.write_text(
            "# Halric\n"
            "\n"
            "## Secrets\n"
            "\n"
            "- [[Mixed Form Secret]]\n",  # display-name form
            encoding="utf-8",
        )
        temple = secrets_fixture / "locations" / "old-temple.md"
        # Preserve the existing Secret bullet and append a slug-path
        # back-reference to the new Secret.
        original_temple = temple.read_text(encoding="utf-8")
        temple.write_text(
            original_temple.rstrip() + "\n- [[secrets/mixed-form-secret]] — slug form\n",
            encoding="utf-8",
        )
        halric_before = halric.read_bytes()
        temple_before = temple.read_bytes()

        result = apply_belongs_to(
            secrets_fixture,
            secret_slug="mixed-form-secret",
            belongs_to=["npcs/halric.md", "locations/old-temple.md"],
            summary="mixed-form idempotency",
        )
        assert result["npcs/halric.md"] is False, (
            "display-name container should be a no-op"
        )
        assert result["locations/old-temple.md"] is False, (
            "slug-path container should be a no-op"
        )
        assert halric.read_bytes() == halric_before, (
            "display-name container's bytes changed on no-op apply"
        )
        assert temple.read_bytes() == temple_before, (
            "slug-path container's bytes changed on no-op apply"
        )


# ---------------------------------------------------------------------------
# Tests — cross-kind collision lint finding
# (Issue #70 follow-on: when display-name links could resolve to multiple
# containers across kind boundaries — e.g. `[[Lore of Lurue]]` matching
# both `adventures/lore-of-lurue/` and `items/lore-of-lurue.md` — the
# linter surfaces the ambiguity rather than silently picking.)
# ---------------------------------------------------------------------------


class TestCrossKindCollisionLintFinding:
    """`lint` emits cross-kind-collision findings for ambiguous display links."""

    def test_collision_finding_names_both_candidates(
        self, secrets_fixture: Path
    ) -> None:
        # Set up the *Lore of Lurue* case: an Adventure and an Item
        # both have H1 `# Lore of Lurue`. An NPC body wiki-links
        # `[[Lore of Lurue]]` in display-name form — ambiguous.
        adv_dir = secrets_fixture / "adventures" / "lore-of-lurue"
        adv_dir.mkdir()
        (adv_dir / "adventure.md").write_text(
            "---\nstatus: introduced\norder: 5\n---\n\n"
            "# Lore of Lurue\n\nAn Adventure about the lore.\n",
            encoding="utf-8",
        )
        item = secrets_fixture / "items" / "lore-of-lurue.md"
        item.write_text(
            "# Lore of Lurue\n\nAn Item — a tome.\n",
            encoding="utf-8",
        )
        # An NPC body uses the ambiguous display-name link.
        halric = secrets_fixture / "npcs" / "halric.md"
        halric.write_text(
            "# Halric\n\nHalric studies the [[Lore of Lurue]] in his spare time.\n",
            encoding="utf-8",
        )
        findings = lint(secrets_fixture)
        collisions = [
            f for f in findings if f.kind == "cross-kind-collision"
        ]
        assert len(collisions) == 1, (
            f"expected exactly one cross-kind-collision finding; got "
            f"{collisions}"
        )
        msg = collisions[0].message
        assert "Lore of Lurue" in msg
        assert "adventures/lore-of-lurue/adventure.md" in msg
        assert "items/lore-of-lurue.md" in msg
        assert collisions[0].container == "npcs/halric.md"

    def test_unique_display_name_link_is_not_flagged(
        self, secrets_fixture: Path
    ) -> None:
        # A display-name link whose title is unique across containers
        # is not ambiguous and must not surface as a collision.
        halric = secrets_fixture / "npcs" / "halric.md"
        halric.write_text(
            "# Halric\n\nHalric knows [[Maren]] from the docks.\n",
            encoding="utf-8",
        )
        findings = lint(secrets_fixture)
        collisions = [
            f for f in findings if f.kind == "cross-kind-collision"
        ]
        assert collisions == [], (
            f"unique-title display-name link was flagged as collision: "
            f"{collisions}"
        )

    def test_same_kind_title_overlap_is_not_a_cross_kind_collision(
        self, secrets_fixture: Path
    ) -> None:
        # Two containers in the SAME kind directory with the same H1
        # would be a different problem (slug collision is already
        # impossible at the filesystem level; H1 duplication within
        # one kind is a GM-judgement case but not the cross-kind
        # ambiguity this finding addresses).
        # Confirm: if both colliders are NPCs, no cross-kind finding.
        halric = secrets_fixture / "npcs" / "halric.md"
        halric.write_text(
            "# Same Title\n\nA character.\n",
            encoding="utf-8",
        )
        orin = secrets_fixture / "npcs" / "orin.md"
        orin.write_text(
            "# Same Title\n\nA different character.\n",
            encoding="utf-8",
        )
        # A faction body uses the display-name link.
        factions_dir = secrets_fixture / "factions"
        sc = factions_dir / "silent-court.md"
        existing = sc.read_text(encoding="utf-8")
        sc.write_text(
            existing.rstrip() + "\n\nNotes on [[Same Title]] who matters.\n",
            encoding="utf-8",
        )
        findings = lint(secrets_fixture)
        collisions = [
            f for f in findings if f.kind == "cross-kind-collision"
        ]
        assert collisions == [], (
            "same-kind H1 duplication surfaced as a cross-kind collision; "
            "the finding should fire only on cross-kind boundary"
        )
