"""Shared fixtures: build small synthetic repositories."""

from __future__ import annotations

import json
import sys
import textwrap
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


@pytest.fixture
def node_repo(tmp_path: Path) -> Path:
    """A pnpm project with a test script, eslint and prettier."""
    (tmp_path / "package.json").write_text(
        json.dumps(
            {
                "name": "demo",
                "scripts": {"test": "vitest run", "build": "tsc"},
                "devDependencies": {"vitest": "^1.0.0", "typescript": "^5.0.0"},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "pnpm-lock.yaml").write_text("lockfileVersion: 6\n", encoding="utf-8")
    (tmp_path / ".eslintrc.json").write_text("{}", encoding="utf-8")
    (tmp_path / ".prettierrc").write_text("{}", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    return tmp_path


@pytest.fixture
def python_repo(tmp_path: Path) -> Path:
    """A Python project with pytest configured in pyproject."""
    (tmp_path / "pyproject.toml").write_text(
        textwrap.dedent(
            """
            [project]
            name = "demo"
            requires-python = ">=3.11"

            [project.scripts]
            demo = "demo.cli:main"

            [tool.pytest.ini_options]
            testpaths = ["tests"]

            [tool.ruff]
            line-length = 88
            """
        ).strip(),
        encoding="utf-8",
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    return tmp_path


@pytest.fixture
def empty_repo(tmp_path: Path) -> Path:
    (tmp_path / "README.md").write_text("# hello\n", encoding="utf-8")
    return tmp_path