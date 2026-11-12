"""Detect facts about a repository from the files on disk.

The rule for this module: every value it returns must be checkable against a
file. No guessing from the repository name, no inferring a framework from a
dependency that might be transitive, no "probably uses jest".

If it cannot be determined, it returns None rather than a plausible default.
A generated AGENTS.md that contains a wrong command is worse than one that
contains no command, because an agent will follow it and then fail.
"""

from __future__ import annotations

import json
import re
import shutil
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Ecosystem detection
# ---------------------------------------------------------------------------

NODE_LOCKFILES = {
    "pnpm-lock.yaml": "pnpm",
    "yarn.lock": "yarn",
    "package-lock.json": "npm",
    "bun.lockb": "bun",
    "bun.lock": "bun",
}

PYTHON_LOCKFILES = {
    "uv.lock": "uv",
    "poetry.lock": "poetry",
    "Pipfile.lock": "pipenv",
    "pdm.lock": "pdm",
}

RUST_LOCKFILES = {"Cargo.lock": "cargo"}
GO_LOCKFILES = {"go.sum": "go"}
RUBY_LOCKFILES = {"Gemfile.lock": "bundler"}

JS_TEST_FRAMEWORKS = (
    ("vitest", "vitest run"),
    ("jest", "jest"),
    ("mocha", "mocha"),
    ("ava", "ava"),
    ("jasmine", "jasmine"),
)

PY_TEST_FRAMEWORKS = (
    ("pytest", "pytest"),
    ("nose2", "nose2"),
)

LINT_CONFIGS = {
    ".eslintrc": "eslint",
    ".eslintrc.js": "eslint",
    ".eslintrc.cjs": "eslint",
    ".eslintrc.json": "eslint",
    ".eslintrc.yml": "eslint",
    "eslint.config.js": "eslint",
    "eslint.config.mjs": "eslint",
    "eslint.config.ts": "eslint",
    ".prettierrc": "prettier",
    ".prettierrc.json": "prettier",
    "prettier.config.js": "prettier",
    "ruff.toml": "ruff",
    ".ruff.toml": "ruff",
    ".flake8": "flake8",
    "mypy.ini": "mypy",
    ".pylintrc": "pylint",
    "biome.json": "biome",
    "rustfmt.toml": "rustfmt",
    "clippy.toml": "clippy",
    "golangci.yml": "golangci-lint",
    ".golangci.yml": "golangci-lint",
}

FORMATTER_CONFIGS = {
    ".prettierrc": "prettier",
    ".prettierrc.json": "prettier",
    "prettier.config.js": "prettier",
    "rustfmt.toml": "rustfmt",
    "biome.json": "biome",
    ".editorconfig": "editorconfig",
}

# Directories that exist in almost every repo and say nothing about structure.
NOISE_DIRS = {
    ".git",
    ".github",
    ".gitlab",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "dist",
    "build",
    "target",
    ".next",
    ".nuxt",
    ".idea",
    ".vscode",
    ".DS_Store",
    "coverage",
    "htmlcov",
    ".tox",
    ".cache",
}


@dataclass
class Repo:
    """Everything detected about one repository."""

    root: Path
    ecosystem: str | None = None
    package_manager: str | None = None
    test_command: str | None = None
    test_framework: str | None = None
    lint_tools: list[str] = field(default_factory=list)
    formatters: list[str] = field(default_factory=list)
    entrypoints: list[str] = field(default_factory=list)
    top_dirs: list[str] = field(default_factory=list)
    # Files that carry a "do not edit" signal, e.g. generated code.
    generated_markers: list[str] = field(default_factory=list)
    ci_files: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _read_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return None


def _read_toml(path: Path) -> dict | None:
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, OSError, UnicodeDecodeError):
        return None


def detect_node(root: Path, repo: Repo) -> None:
    package_json = root / "package.json"
    data = _read_json(package_json)
    if data is None:
        repo.notes.append("package.json exists but could not be parsed")
        return

    for lockfile, manager in NODE_LOCKFILES.items():
        if (root / lockfile).exists():
            repo.package_manager = manager
            break

    scripts = data.get("scripts") or {}
    if isinstance(scripts, dict) and scripts:
        # Prefer an explicit test script over guessing from dependencies,
        # because the script is what the project actually runs.
        if "test" in scripts:
            prefix = {
                "pnpm": "pnpm test",
                "yarn": "yarn test",
                "npm": "npm test",
                "bun": "bun test",
            }.get(repo.package_manager or "npm", "npm test")
            repo.test_command = prefix
            repo.notes.append("test command comes from package.json scripts.test")

    deps = {}
    for key in ("dependencies", "devDependencies"):
        value = data.get(key)
        if isinstance(value, dict):
            deps.update(value)

    for framework, command in JS_TEST_FRAMEWORKS:
        if framework in deps:
            repo.test_framework = framework
            if repo.test_command is None:
                runner = repo.package_manager or "npx"
                if repo.package_manager in ("pnpm", "yarn", "bun"):
                    repo.test_command = f"{runner} {command}"
                else:
                    repo.test_command = f"npx {command}"
                repo.notes.append(
                    f"test command inferred from the {framework} dependency; "
                    "there is no scripts.test entry"
                )
            break

    if data.get("type") == "module":
        repo.notes.append("package.json sets type: module (ESM)")


def detect_python(root: Path, repo: Repo) -> None:
    for lockfile, manager in PYTHON_LOCKFILES.items():
        if (root / lockfile).exists():
            repo.package_manager = manager
            break

    if repo.package_manager is None and (root / "requirements.txt").exists():
        repo.package_manager = "pip"

    pyproject = root / "pyproject.toml"
    declared_test_tool = None
    if pyproject.exists():
        data = _read_toml(pyproject)
        if data:
            tool = data.get("tool") or {}
            if isinstance(tool, dict):
                if "pytest" in tool:
                    declared_test_tool = "pytest"
                if "ruff" in tool:
                    repo.lint_tools.append("ruff")
                if "mypy" in tool:
                    repo.lint_tools.append("mypy")
                if "black" in tool:
                    repo.formatters.append("black")
            project = data.get("project") or {}
            scripts = project.get("scripts") if isinstance(project, dict) else None
            if isinstance(scripts, dict):
                for name in sorted(scripts):
                    repo.entrypoints.append(f"`{name}` (pyproject script)")
            if project.get("requires-python"):
                repo.notes.append(f"requires-python: {project['requires-python']}")

    has_pytest_ini = (root / "pytest.ini").exists() or (root / "conftest.py").exists()
    has_tests_dir = (root / "tests").is_dir() or (root / "test").is_dir()

    if declared_test_tool or has_pytest_ini or (root / "tox.ini").exists():
        repo.test_framework = "pytest"
    if has_tests_dir and repo.test_framework is None:
        repo.notes.append(
            "a tests directory exists but no test runner was detected from "
            "configuration; the test command is left blank on purpose"
        )

    if repo.test_framework == "pytest" and repo.test_command is None:
        runner = "uv run pytest" if repo.package_manager == "uv" else "pytest"
        if repo.package_manager == "poetry":
            runner = "poetry run pytest"
        repo.test_command = runner


def detect_rust(root: Path, repo: Repo) -> None:
    if (root / "Cargo.toml").exists():
        repo.package_manager = "cargo"
        repo.test_command = "cargo test"
        repo.test_framework = "cargo test"
        repo.formatters.append("rustfmt")
        data = _read_toml(root / "Cargo.toml")
        if data and isinstance(data.get("workspace"), dict):
            repo.notes.append("Cargo workspace (multiple crates)")


def detect_go(root: Path, repo: Repo) -> None:
    if (root / "go.mod").exists():
        repo.package_manager = "go"
        repo.test_command = "go test ./..."
        repo.test_framework = "go test"


def detect_ruby(root: Path, repo: Repo) -> None:
    if (root / "Gemfile").exists():
        repo.ecosystem = repo.ecosystem or "ruby"
        repo.package_manager = "bundler"
        if (root / "spec").is_dir():
            repo.test_framework = "rspec"
            repo.test_command = "bundle exec rspec"
        elif (root / "test").is_dir():
            repo.test_command = "bundle exec rake test"


def detect_ecosystem(root: Path, repo: Repo) -> None:
    """Pick the primary ecosystem. Order matters when a repo has several."""
    signals = [
        ("node", root / "package.json"),
        ("rust", root / "Cargo.toml"),
        ("python", root / "pyproject.toml"),
        ("python", root / "requirements.txt"),
        ("go", root / "go.mod"),
        ("ruby", root / "Gemfile"),
    ]
    for ecosystem, marker in signals:
        if marker.exists():
            repo.ecosystem = ecosystem
            return


def detect_lint(root: Path, repo: Repo) -> None:
    for filename, tool in LINT_CONFIGS.items():
        if (root / filename).exists() and tool not in repo.lint_tools:
            repo.lint_tools.append(tool)
    for filename, tool in FORMATTER_CONFIGS.items():
        if (root / filename).exists() and tool not in repo.formatters:
            repo.formatters.append(tool)


def detect_structure(root: Path, repo: Repo) -> None:
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        name = child.name
        if name in NOISE_DIRS:
            continue
        # Virtualenvs named anything (`env`, `.venv311`) and packaging output
        # directories (`*.egg-info`, `*.dist-info`) are never source. Detecting
        # them as layout is the kind of noise that makes a generated file
        # useless, because it describes the developer's machine rather than the
        # project.
        if name.startswith("."):
            continue
        if name.endswith((".egg-info", ".dist-info")):
            continue
        if (child / "pyvenv.cfg").exists() or (child / "Scripts").is_dir():
            continue
        if (child / "node_modules").is_dir():
            continue
        repo.top_dirs.append(name + "/")

    for candidate in ("main.py", "cli.py", "__main__.py", "index.js", "main.rs", "main.go"):
        if (root / candidate).exists():
            repo.entrypoints.append(f"`{candidate}`")

    for ci in (
        ".github/workflows",
        ".gitlab-ci.yml",
        ".circleci/config.yml",
        "azure-pipelines.yml",
        "Jenkinsfile",
    ):
        if (root / ci).exists():
            repo.ci_files.append(ci)


def detect_generated(root: Path, repo: Repo) -> None:
    """Find files that announce they are generated, up to a small depth.

    These are the highest-value lines in a generated AGENTS.md: an agent that
    edits a generated file wastes a whole turn and the change is overwritten.

    The marker must look like a directive, not like prose that mentions
    generation. A documentation file explaining generated code is not itself
    generated, and flagging it as off-limits is worse than missing a real one.
    """
    # A real marker is a directive at the top of the file, in a comment. Text
    # that merely mentions the phrase — documentation explaining generated code,
    # or a code sample inside a fence — is not a directive and must not be
    # flagged, because marking a hand-written doc as off-limits is worse than
    # missing a generated file.
    comment_line = re.compile(r"^\s*(#|//|/\*|\*|--|<!--)\s*(.{0,80})")
    marker_words = re.compile(
        r"(DO NOT EDIT|@generated|AUTO[- ]?GENERATED|CODE GENERATED|"
        r"This file (is|was) (auto[- ]?)?generated)",
        re.IGNORECASE,
    )

    for path in root.rglob("*"):
        if len(path.relative_to(root).parts) > 3:
            continue
        if any(part in NOISE_DIRS for part in path.relative_to(root).parts):
            continue
        if not path.is_file() or path.stat().st_size > 64_000:
            continue
        if path.suffix not in (".py", ".js", ".ts", ".rs", ".go", ".md", ".toml", ".yaml", ".yml"):
            continue
        try:
            head = path.read_text(encoding="utf-8", errors="replace")[:1500]
        except OSError:
            continue

        # Only the first ten lines: generated files announce it immediately.
        # Fenced blocks in Markdown are skipped, because a doc that *shows* an
        # example marker is documentation, not generated output.
        in_fence = False
        for line in head.split("\n")[:10]:
            if line.strip().startswith("```"):
                in_fence = not in_fence
                continue
            if in_fence:
                continue
            match = comment_line.match(line)
            if not match:
                continue
            if marker_words.search(match.group(2)):
                repo.generated_markers.append(
                    str(path.relative_to(root)).replace("\\", "/")
                )
                break
        if len(repo.generated_markers) >= 10:
            break


def detect(root: Path) -> Repo:
    """Run every detector against a repository root."""
    repo = Repo(root=root)

    detect_ecosystem(root, repo)

    if repo.ecosystem == "node":
        detect_node(root, repo)
    elif repo.ecosystem == "python":
        detect_python(root, repo)
    elif repo.ecosystem == "rust":
        detect_rust(root, repo)
    elif repo.ecosystem == "go":
        detect_go(root, repo)
    elif repo.ecosystem == "ruby":
        detect_ruby(root, repo)
    else:
        repo.notes.append(
            "no recognised project manifest found; only structure was detected"
        )

    # Python can appear alongside another ecosystem, so check it separately.
    if repo.ecosystem != "python" and (root / "pyproject.toml").exists():
        detect_python(root, repo)

    detect_lint(root, repo)
    detect_structure(root, repo)
    detect_generated(root, repo)

    return repo


def command_exists(command: str, root: Path) -> tuple[bool, str]:
    """Check whether the first word of a command is runnable.

    Returns (found, detail). This is the primitive the verifier is built on: it
    cannot prove a command succeeds, only that the binary is present.
    """
    first = command.strip().split()[0] if command.strip() else ""
    if not first:
        return False, "empty command"

    # A path into the repo: check the file.
    if "/" in first or first.startswith("."):
        target = (root / first).resolve()
        if target.exists():
            return True, "path exists in the repository"
        return False, "no such file in the repository"

    resolved = shutil.which(first)
    if resolved:
        return True, f"found at {resolved}"
    return False, "not found on PATH"