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
  - **`lint`** — walk the campaign, find two failure modes:
      * **orphan wiki-link** — a `[[secrets/<slug>]]` link in some
        container's `## Secrets` section pointing at a non-existent
        Secret file.
      * **missing back-reference** — a Secret lists `npcs/maren.md` in
        `belongs_to:` but `npcs/maren.md` has no `## Secrets` section
        (or has one but doesn't link back to the Secret).

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


def _has_back_reference(body: str, secret_slug: str) -> bool:
    """True if the body contains a wiki-link to the given Secret slug
    inside its `## Secrets` section.

    The match looks for any `[[secrets/<slug>]]` token in the body; the
    spec requires it to live under a `## Secrets` heading, but the
    minimal-reference linter accepts any body-position match (the
    section grouping is editorial). The link presence is the
    load-bearing property.
    """
    for match in WIKI_LINK_RE.finditer(body):
        if match.group(1) == secret_slug:
            return True
    return False


def _ensure_secrets_section(body: str, secret_slug: str, summary: str) -> str:
    """Return a body that includes a `## Secrets` section linking the slug.

    Idempotent: if the body already wiki-links the slug, returns the
    body unchanged. Otherwise appends a `## Secrets` section (or adds
    an entry to an existing one) with a single bullet of the form
    `- [[secrets/<slug>]] — <summary>`.
    """
    if _has_back_reference(body, secret_slug):
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
        new_body = _ensure_secrets_section(body, secret_slug, summary)
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


def lint(campaign_root: Path) -> list[LintFinding]:
    """Return every bidi-link drift case in the campaign.

    Two categories surfaced:
      * `"orphan"` — container links a Secret slug that has no
        corresponding `secrets/<slug>.md` file.
      * `"missing-back-reference"` — a Secret's `belongs_to:` claims a
        container, but the container's body has no wiki-link back to
        the Secret.
    """
    findings: list[LintFinding] = []
    secret_slugs = _enumerate_secret_slugs(campaign_root)
    container_links = _enumerate_containers_with_secrets_links(campaign_root)

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
    #    doesn't link back.
    secrets_dir = campaign_root / "secrets"
    if secrets_dir.is_dir():
        for sp in sorted(
            (p for p in secrets_dir.iterdir() if p.name.endswith(".md")),
            key=lambda p: p.name,
        ):
            text = sp.read_text(encoding="utf-8")
            fm, _ = _split_frontmatter(text)
            slug = sp.stem
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
                if slug not in linked:
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
        # the container path and the Secret slug. The GM reading the
        # lint output needs the file path to act on it.
        for f in lint(secrets_fixture):
            assert f.container in f.message, (
                f"finding message {f.message!r} does not name the "
                f"container {f.container!r}"
            )
            assert f.secret_slug in f.message, (
                f"finding message {f.message!r} does not name the "
                f"secret slug {f.secret_slug!r}"
            )
