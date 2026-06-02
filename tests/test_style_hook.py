"""Behavioral test for `.claude/hooks/style-aware-write-gate.sh.template`.

Per [issue #121](https://github.com/snlemons/game_manager/issues/121) and
[ADR-0021](../docs/adr/0021-gm-writing-style-via-claude-rules-style.md)'s
mechanism-layer amendment, the hook is the PreToolUse backstop for the
CLAUDE.md style-Read directive. The directive is the primary mechanism
(an explicit Read of `.claude/rules/style.md` early in any drafting
session); the hook is the per-call reminder confirming the path is in
scope. Together they work around Claude Code [#23478][23478] (path-scoped
auto-load doesn't fire on the Write tool).

[23478]: https://github.com/anthropics/claude-code/issues/23478

The hook's contract is narrow and easy to pin:

1. **Empty `file_path`** -> emit allow passthrough (no `additionalContext`).
2. **`file_path` set, but `style.md` absent** -> emit allow passthrough.
   (Without a style guide the reminder is noise.)
3. **`file_path` set and `style.md` present and path matches a covered
   directory glob** -> emit allow with the documented reminder
   `additionalContext`.
4. **`file_path` set and `style.md` present but path does NOT match a
   covered glob** -> emit allow passthrough (no reminder).

The matched-glob set is anchored on `/` boundaries (`*/sessions/*`,
not `*sessions*`) so a file named `assessment.md` at the campaign root
doesn't false-match on `sessions/`. This test pins both the
anchoring and the exact path coverage.

All assertions are on the hook's stdout shape — valid JSON with the
documented `hookSpecificOutput` envelope. The test runs the
`.template` file directly through `bash`; the template carries no
`{{...}}` placeholders, so the bytes the scaffolder writes match the
bytes this test exercises.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest


REMINDER_PREFIX = (
    "Reminder: this file is in a content-bearing path steered by "
    ".claude/rules/style.md."
)


# Directory tokens that should TRIGGER the reminder. Each one anchored
# on `/` boundaries — the case statement uses `*/sessions/*` style
# globs, not bare `sessions`.
COVERED_DIR_TOKENS: tuple[str, ...] = (
    "sessions",
    "adventures",
    "npcs",
    "pcs",
    "locations",
    "factions",
    "items",
    "threads",
    "consequences",
    "beats",
    "secrets",
)


@pytest.fixture(scope="module")
def hook_template_path(templates_dir: Path) -> Path:
    """Absolute path to the raw hook template."""
    return (
        templates_dir
        / ".claude"
        / "hooks"
        / "style-aware-write-gate.sh.template"
    )


@pytest.fixture()
def project_with_style(tmp_path: Path) -> Path:
    """A scratch project dir with a `.claude/rules/style.md` present.

    The hook short-circuits to allow-passthrough when style.md is
    absent (case 2 above); most tests want the file present so the
    matching/non-matching glob branch is exercised.
    """
    project = tmp_path / "campaign-with-style"
    (project / ".claude" / "rules").mkdir(parents=True)
    (project / ".claude" / "rules" / "style.md").write_text(
        "stub", encoding="utf-8"
    )
    return project


@pytest.fixture()
def project_without_style(tmp_path: Path) -> Path:
    """A scratch project dir with NO `.claude/rules/style.md`."""
    project = tmp_path / "campaign-without-style"
    project.mkdir(parents=True)
    return project


def _run_hook(
    hook_path: Path,
    *,
    project_dir: Path,
    file_path: str,
    tool_name: str = "Write",
) -> dict:
    """Run the hook template with the given input and return parsed stdout.

    `bash` is required on PATH; `jq` is required by the hook itself
    (the script's `jq -r` and `jq -n` invocations). Both are standard
    on macOS / Linux CI runners.
    """
    if shutil.which("bash") is None:
        pytest.skip("bash not on PATH")
    if shutil.which("jq") is None:
        pytest.skip("jq not on PATH (required by hook script)")
    payload = json.dumps(
        {"tool_name": tool_name, "tool_input": {"file_path": file_path}}
    )
    env = {
        "CLAUDE_PROJECT_DIR": str(project_dir),
        "PATH": (
            "/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin"
        ),
    }
    result = subprocess.run(
        ["bash", str(hook_path)],
        input=payload,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip(), (
        f"hook produced no stdout; stderr: {result.stderr!r}"
    )
    return json.loads(result.stdout)


class TestPassthroughCases:
    """Cases where the hook emits allow passthrough (no reminder)."""

    def test_empty_file_path_passes_through(
        self,
        hook_template_path: Path,
        project_with_style: Path,
    ) -> None:
        """No `file_path` -> nothing to scope -> passthrough."""
        data = _run_hook(
            hook_template_path,
            project_dir=project_with_style,
            file_path="",
        )
        out = data["hookSpecificOutput"]
        assert out["permissionDecision"] == "allow", (
            f"expected allow, got {out['permissionDecision']!r}"
        )
        assert "additionalContext" not in out, (
            "passthrough should not carry `additionalContext`; got "
            f"{out.get('additionalContext')!r}"
        )

    def test_missing_style_file_passes_through(
        self,
        hook_template_path: Path,
        project_without_style: Path,
    ) -> None:
        """No `style.md` -> reminder would be noise -> passthrough."""
        data = _run_hook(
            hook_template_path,
            project_dir=project_without_style,
            file_path="/some/where/npcs/foo.md",
        )
        out = data["hookSpecificOutput"]
        assert out["permissionDecision"] == "allow"
        assert "additionalContext" not in out, (
            "no style.md -> no reminder; got "
            f"{out.get('additionalContext')!r}"
        )

    @pytest.mark.parametrize(
        "non_matching_path",
        [
            "/Users/x/campaign/CLAUDE.md",
            "/Users/x/campaign/campaign.md",
            "/Users/x/campaign/README.md",
            "/Users/x/campaign/.claude/rules/style.md",
            # Critical anchoring check: `assessment.md` at the campaign
            # root must NOT match `*/sessions/*` (no `/sessions/` boundary).
            "/Users/x/campaign/assessment.md",
            # Similar: a file named `sessions.md` at the root must not
            # match a `sessions/` directory glob.
            "/Users/x/campaign/sessions.md",
        ],
        ids=[
            "claude-md-at-root",
            "campaign-md-at-root",
            "readme-at-root",
            "style-rule-itself",
            "assessment-not-sessions",
            "sessions-md-at-root",
        ],
    )
    def test_non_covered_path_passes_through(
        self,
        hook_template_path: Path,
        project_with_style: Path,
        non_matching_path: str,
    ) -> None:
        data = _run_hook(
            hook_template_path,
            project_dir=project_with_style,
            file_path=non_matching_path,
        )
        out = data["hookSpecificOutput"]
        assert out["permissionDecision"] == "allow"
        assert "additionalContext" not in out, (
            f"path {non_matching_path!r} should not trigger the "
            f"reminder; got {out.get('additionalContext')!r}"
        )


class TestCoveredPathReminders:
    """Cases where the hook injects the documented reminder."""

    @pytest.mark.parametrize(
        "dir_token",
        COVERED_DIR_TOKENS,
        ids=COVERED_DIR_TOKENS,
    )
    def test_covered_directory_triggers_reminder(
        self,
        hook_template_path: Path,
        project_with_style: Path,
        dir_token: str,
    ) -> None:
        """Each documented content-bearing directory triggers the reminder."""
        file_path = f"/Users/x/campaign/{dir_token}/foo.md"
        data = _run_hook(
            hook_template_path,
            project_dir=project_with_style,
            file_path=file_path,
        )
        out = data["hookSpecificOutput"]
        assert out["permissionDecision"] == "allow"
        assert "additionalContext" in out, (
            f"path under `{dir_token}/` should trigger the reminder; "
            f"got passthrough"
        )
        assert out["additionalContext"].startswith(REMINDER_PREFIX), (
            "reminder text drifted from the documented prefix; got "
            f"{out['additionalContext']!r}"
        )

    def test_staging_path_triggers_reminder(
        self,
        hook_template_path: Path,
        project_with_style: Path,
    ) -> None:
        """`.ttrpg-staging/` paths trigger the reminder.

        The staging directory is the drafting scratchpad for skills
        that route writes through `.ttrpg-staging/wrap/...` before
        promoting to the final path. The hook's case statement
        explicitly covers `*/.ttrpg-staging/*`.
        """
        file_path = (
            "/Users/x/campaign/.ttrpg-staging/wrap/sessions/foo/log.md"
        )
        data = _run_hook(
            hook_template_path,
            project_dir=project_with_style,
            file_path=file_path,
        )
        out = data["hookSpecificOutput"]
        assert "additionalContext" in out, (
            "staging path should trigger the reminder"
        )
        assert out["additionalContext"].startswith(REMINDER_PREFIX)

    def test_hook_event_name_is_pretooluse(
        self,
        hook_template_path: Path,
        project_with_style: Path,
    ) -> None:
        """The reminder envelope identifies as a PreToolUse output."""
        data = _run_hook(
            hook_template_path,
            project_dir=project_with_style,
            file_path="/Users/x/campaign/npcs/foo.md",
        )
        out = data["hookSpecificOutput"]
        assert out["hookEventName"] == "PreToolUse", (
            f"unexpected hookEventName: {out['hookEventName']!r}"
        )
