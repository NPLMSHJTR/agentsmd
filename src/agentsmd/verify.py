"""Verify an existing AGENTS.md against the repository as it is now.

This is the part that earns the tool its place. Generating a document is a
one-time convenience; keeping it true is the recurring problem. A file that says
`pnpm test` after the script was renamed to `pnpm t` is actively harmful,
because the agent will run it, fail, and then improvise.

Checks, in order of how often they catch something real:

    AG001  a command in backticks has no runnable first word
    AG002  a path in backticks does not exist
    AG003  the file names a package manager the repo does not use
    AG004  a fenced command block references a missing file
    AG005  the file is stale relative to the build files
    AG006  advice-shaped lines that an agent cannot act on
    AG007  the file is missing sections that this repo needs
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .detect import Repo, command_exists

SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2}

# A command in backticks. Deliberately narrow: no spaces-only phrases, must
# look like an invocation.
INLINE_CODE = re.compile(r"`([^`\n]+)`")

# Only treat backticked text as a command if it starts with one of these or is a
# bare filename. This keeps prose like `--flag` from being reported as a missing
# binary.
COMMAND_HINTS = (
    "npm", "pnpm", "yarn", "bun", "npx", "node", "deno",
    "python", "python3", "pip", "pip3", "uv", "poetry", "pdm", "pytest",
    "cargo", "rustc", "go", "make", "just", "task",
    "docker", "docker-compose", "podman",
    "git", "gh",
    "eslint", "prettier", "biome", "ruff", "black", "mypy", "flake8", "pylint",
    "tsc", "vite", "webpack", "rollup", "turbo",
    "bash", "sh", "pwsh", "powershell",
    "bundle", "rake", "rspec", "mvn", "gradle", "dotnet",
)

PATH_HINTS = ("/", ".", "\\")

ADVICE_PATTERNS = (
    re.compile(r"\b(write|keep|ensure|make sure)\b.{0,40}\b(clean|readable|simple|clear|good)\b", re.I),
    re.compile(r"\bfollow (best|good) practices\b", re.I),
    re.compile(r"\bprefer (small|simple|clean)\b", re.I),
    re.compile(r"\bbe (kind|nice|careful)\b", re.I),
    re.compile(r"\bthink (carefully|step by step)\b", re.I),
    re.compile(r"\bdo not hallucinate\b", re.I),
)

PACKAGE_MANAGER_COMMANDS = {
    "npm", "pnpm", "yarn", "bun", "pip", "pip3", "poetry", "uv", "pdm",
    "cargo", "go", "bundle",
}

REQUIRED_IF = {
    "test_command": "a test command",
    "package_manager": "the package manager",
    "top_dirs": "the directory layout",
}


@dataclass(frozen=True)
class Issue:
    rule: str
    severity: str
    message: str
    hint: str = ""
    line: int | None = None


@dataclass
class VerifyResult:
    path: Path
    issues: list[Issue]
    checked_items: int = 0
    skipped_missing_tools: list[str] = field(default_factory=list)

    @property
    def errors(self) -> int:
        return sum(1 for i in self.issues if i.severity == "error")

    @property
    def warnings(self) -> int:
        return sum(1 for i in self.issues if i.severity == "warning")

    def sorted_issues(self) -> list[Issue]:
        return sorted(
            self.issues, key=lambda i: (SEVERITY_ORDER.get(i.severity, 9), i.rule)
        )


def _looks_like_command(text: str) -> bool:
    stripped = text.strip()
    if not stripped or " " not in stripped and not stripped.startswith("./"):
        # A single bare word could be a filename; only treat it as a command if
        # it is a known tool.
        return stripped.split()[0] in COMMAND_HINTS if stripped else False
    first = stripped.split()[0]
    return first in COMMAND_HINTS or stripped.startswith(("./", "../"))


def _looks_like_path(text: str) -> bool:
    stripped = text.strip()
    if not stripped or " " in stripped:
        return False
    if stripped.startswith(("http://", "https://", "mailto:")):
        return False
    # A bare word with no separator and no known extension is not a path claim.
    if not any(h in stripped for h in PATH_HINTS):
        return False
    return not stripped.startswith("-")


def verify(agents_file: Path, repo: Repo) -> VerifyResult:
    result = VerifyResult(path=agents_file, issues=[])
    text = agents_file.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    root = repo.root

    # Whether the ecosystem's own tool is installed decides how to treat a
    # missing binary. The check is deliberately per-command rather than
    # per-ecosystem: having `npm` on the machine says nothing about whether
    # `pnpm` is installed, and conflating the two turns a missing tool into a
    # false accusation that the document is stale.
    toolchain_probe = {
        "node": "node",
        "python": "python",
        "rust": "cargo",
        "go": "go",
        "ruby": "bundle",
    }.get(repo.ecosystem or "", None)
    toolchain_present = True
    if toolchain_probe:
        found, _ = command_exists(toolchain_probe, root)
        toolchain_present = found

    def classify_missing(tool: str) -> str:
        """Decide whether a missing tool means 'stale doc' or 'not installed'."""
        if tool == repo.package_manager:
            # The project's own package manager should be present; if it is not,
            # this machine cannot build the project at all, so the document is
            # not the problem.
            return "unavailable"
        if not toolchain_present:
            return "unavailable"
        return "missing"

    # ---- inline code: commands and paths ----------------------------------
    for index, line in enumerate(lines, start=1):
        for match in INLINE_CODE.finditer(line):
            token = match.group(1).strip()
            if not token:
                continue

            if _looks_like_command(token):
                result.checked_items += 1
                first = token.split()[0]
                found, detail = command_exists(token, root)
                if not found:
                    if classify_missing(first) == "missing":
                        result.issues.append(
                            Issue(
                                "AG001",
                                "error",
                                f"`{token}` is presented as a command, but "
                                f"`{first}` cannot be run: {detail}",
                                "Either the tool is not installed in this "
                                "environment, or the file is out of date. Confirm "
                                "the command works before leaving it in the file.",
                                index,
                            )
                        )
                    else:
                        # Cannot tell stale from uninstalled. Say which.
                        if first not in result.skipped_missing_tools:
                            result.skipped_missing_tools.append(first)
                        result.issues.append(
                            Issue(
                                "AG001",
                                "info",
                                f"`{token}` could not be checked: `{first}` is not "
                                "installed on this machine",
                                f"This environment has no {repo.ecosystem} "
                                "toolchain, so the command's existence is unknown "
                                "rather than wrong. Run verify where the project's "
                                "tools are installed for a real answer.",
                                index,
                            )
                        )
                if first in PACKAGE_MANAGER_COMMANDS and repo.package_manager:
                    expected = repo.package_manager
                    if first != expected and first in (
                        "npm", "pnpm", "yarn", "bun", "pip", "poetry", "uv", "pdm"
                    ):
                        result.issues.append(
                            Issue(
                                "AG003",
                                "error",
                                f"`{token}` uses {first}, but this repository "
                                f"uses {expected}",
                                f"Change the command to use {expected}, or delete "
                                "it. A wrong package manager produces a lockfile "
                                "in the wrong format.",
                                index,
                            )
                        )
                continue

            if _looks_like_path(token):
                result.checked_items += 1
                candidate = (root / token).resolve()
                if not candidate.exists():
                    result.issues.append(
                        Issue(
                            "AG002",
                            "error",
                            f"`{token}` is referenced but does not exist",
                            "This is the most common way an AGENTS.md goes stale: "
                            "a file is renamed and the reference is not updated.",
                            index,
                        )
                    )

    # ---- fenced blocks: treat first token as a command --------------------
    in_fence = False
    fence_lang = ""
    for index, line in enumerate(lines, start=1):
        if line.strip().startswith("```"):
            if not in_fence:
                fence_lang = line.strip().lstrip("`").strip().lower()
            in_fence = not in_fence
            continue
        if not in_fence:
            continue
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        # Skip output blocks: they are transcripts, not commands to run.
        if fence_lang in ("text", "output", "console-output", "log"):
            continue
        first = stripped.split()[0]
        # Any line in a shell-ish fence is meant to be runnable, whether or not
        # the tool is one this file happens to know about.
        if fence_lang in ("bash", "sh", "shell", "zsh", "console", "powershell", "pwsh", "cmd", ""):
            result.checked_items += 1
            found, detail = command_exists(stripped, root)
            if not found and classify_missing(stripped.split()[0]) == "missing":
                result.issues.append(
                    Issue(
                        "AG004",
                        "warning",
                        f"command in a fenced block cannot run here: {detail}",
                        "Fenced commands are copied verbatim by an agent. If this "
                        "line is illustrative rather than runnable, say so in the "
                        "prose above it, or tag the fence as `text`.",
                        index,
                    )
                )
            elif not found and first not in result.skipped_missing_tools:
                result.skipped_missing_tools.append(first)
            continue
        if first in COMMAND_HINTS:
            result.checked_items += 1
            found, detail = command_exists(stripped, root)
            if not found:
                result.issues.append(
                    Issue(
                        "AG004",
                        "warning",
                        f"command in a fenced block cannot run here: {detail}",
                        "Fenced commands are copied verbatim by an agent.",
                        index,
                    )
                )

    # ---- advice that cannot be acted on -----------------------------------
    for index, line in enumerate(lines, start=1):
        for pattern in ADVICE_PATTERNS:
            if pattern.search(line):
                result.issues.append(
                    Issue(
                        "AG006",
                        "warning",
                        f"line reads as advice an agent cannot verify: {line.strip()[:70]!r}",
                        "Replace it with a checkable fact or delete it. An "
                        "instruction that cannot be followed costs a turn to "
                        "disprove and teaches nothing.",
                        index,
                    )
                )
                break

    # ---- missing sections the repo actually needs -------------------------
    lowered = text.lower()
    if repo.test_command and "test" not in lowered:
        result.issues.append(
            Issue(
                "AG007",
                "warning",
                "the repository has a test command but the file never mentions tests",
                f"Add `{repo.test_command}`. Not knowing how to run tests is the "
                "single most expensive gap for an agent working in this repo.",
            )
        )
    if repo.generated_markers and "do not edit" not in lowered:
        result.issues.append(
            Issue(
                "AG007",
                "info",
                f"{len(repo.generated_markers)} generated file(s) exist but the "
                "file does not warn against editing them",
                "An agent that edits generated code wastes the change.",
            )
        )

    return result