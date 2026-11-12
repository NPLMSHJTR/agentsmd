"""Tests for AGENTS.md verification.

These are the tests that matter. Detection is a convenience; verification is the
reason the tool exists, so each rule gets a case that must fire and a case that
must stay quiet.
"""

from __future__ import annotations

from pathlib import Path

from agentsmd.detect import detect
from agentsmd.verify import verify


def _write(root: Path, text: str) -> Path:
    target = root / "AGENTS.md"
    target.write_text(text, encoding="utf-8")
    return target


def test_clean_file_has_no_errors(node_repo: Path):
    """A correct file must produce no errors, whatever tools this machine has.

    `pnpm` may not be installed here. That is a fact about the machine, not
    about the document, so the tool must not report it as a document error.
    """
    path = _write(
        node_repo,
        "# AGENTS.md\n\n"
        "## Commands\n\n"
        "- Test: `pnpm test`\n\n"
        "## Layout\n\n- `src/` holds the source\n- `tests/` holds the tests\n",
    )
    result = verify(path, detect(node_repo))
    assert result.errors == 0
    assert result.checked_items >= 3


def test_missing_project_package_manager_is_not_a_document_error(node_repo: Path):
    """If the project's own package manager is absent, say so as info."""
    path = _write(node_repo, "# AGENTS.md\n\nRun `pnpm test`.\n")
    result = verify(path, detect(node_repo))
    ag001 = [i for i in result.issues if i.rule == "AG001"]
    for issue in ag001:
        assert issue.severity == "info", (
            "a tool missing from this machine must not be reported as a "
            "document error"
        )


def test_missing_binary_is_an_error(node_repo: Path):
    path = _write(node_repo, "# AGENTS.md\n\nRun `npm test`.\n")
    result = verify(path, detect(node_repo))
    rules = {i.rule for i in result.issues}
    # npm is not the package manager here, so AG003 fires; it also may not exist.
    assert "AG003" in rules or "AG001" in rules


def test_wrong_package_manager_is_an_error(node_repo: Path):
    path = _write(node_repo, "# AGENTS.md\n\nInstall with `npm install`.\n")
    result = verify(path, detect(node_repo))
    ag003 = [i for i in result.issues if i.rule == "AG003"]
    assert ag003, "expected a wrong-package-manager finding"
    assert "pnpm" in ag003[0].message


def test_missing_path_is_an_error(node_repo: Path):
    path = _write(node_repo, "# AGENTS.md\n\nSee `src/main.ts` for the entry.\n")
    result = verify(path, detect(node_repo))
    ag002 = [i for i in result.issues if i.rule == "AG002"]
    assert ag002, "expected a missing-path finding"
    assert "src/main.ts" in ag002[0].message


def test_existing_path_passes(node_repo: Path):
    (node_repo / "src" / "main.ts").write_text("export {}\n", encoding="utf-8")
    path = _write(node_repo, "# AGENTS.md\n\nSee `src/main.ts`.\n")
    result = verify(path, detect(node_repo))
    assert not [i for i in result.issues if i.rule == "AG002"]


def test_external_url_is_not_a_path(node_repo: Path):
    path = _write(
        node_repo, "# AGENTS.md\n\nDocs: `https://example.com/a/b/c/d`.\n"
    )
    result = verify(path, detect(node_repo))
    assert not [i for i in result.issues if i.rule == "AG002"]


def test_fenced_command_missing_binary(node_repo: Path):
    """A made-up tool name in a shell fence is flagged when the toolchain exists.

    Skipped when the machine has no Node at all, because then "missing" cannot
    be distinguished from "not installed here" and the tool says so instead of
    guessing.
    """
    from agentsmd.detect import command_exists

    node_present, _ = command_exists("node", node_repo)
    path = _write(
        node_repo,
        "# AGENTS.md\n\n```bash\nnotarealtool --build\n```\n",
    )
    result = verify(path, detect(node_repo))
    if node_present:
        assert any(i.rule == "AG004" for i in result.issues)
    else:
        assert "notarealtool" in result.skipped_missing_tools


def test_advice_line_is_flagged(node_repo: Path):
    path = _write(
        node_repo,
        "# AGENTS.md\n\n"
        "Please write clean readable code at all times.\n\n"
        "Follow best practices.\n",
    )
    result = verify(path, detect(node_repo))
    ag006 = [i for i in result.issues if i.rule == "AG006"]
    assert len(ag006) >= 2


def test_actionable_line_is_not_flagged(node_repo: Path):
    path = _write(
        node_repo,
        "# AGENTS.md\n\n"
        "Run `pnpm test` before every commit. The build fails if any test is "
        "skipped.\n",
    )
    result = verify(path, detect(node_repo))
    assert not [i for i in result.issues if i.rule == "AG006"]


def test_missing_test_mention_when_repo_has_tests(node_repo: Path):
    path = _write(node_repo, "# AGENTS.md\n\nThis project is a demo.\n")
    result = verify(path, detect(node_repo))
    assert any(i.rule == "AG007" for i in result.issues)


def test_generated_files_without_warning(node_repo: Path):
    (node_repo / "gen.ts").write_text("// DO NOT EDIT. Generated.\n", encoding="utf-8")
    path = _write(node_repo, "# AGENTS.md\n\nRun `pnpm test`.\n")
    result = verify(path, detect(node_repo))
    assert any(i.rule == "AG007" for i in result.issues)


def test_flags_are_not_treated_as_paths(node_repo: Path):
    path = _write(
        node_repo,
        "# AGENTS.md\n\nRun `pnpm test` with `--reporter=verbose` enabled.\n",
    )
    result = verify(path, detect(node_repo))
    assert not [i for i in result.issues if i.rule == "AG002"]


def test_error_count_separates_from_warnings(node_repo: Path):
    path = _write(
        node_repo,
        "# AGENTS.md\n\nSee `src/nope.ts`. Also write clean code.\n",
    )
    result = verify(path, detect(node_repo))
    assert result.errors >= 1
    assert result.warnings >= 1