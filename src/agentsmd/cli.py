"""Command line interface.

    agentsmd detect <repo>        print what was detected, as JSON
    agentsmd generate <repo>      write AGENTS.md (or print with --stdout)
    agentsmd verify <repo>        check the existing AGENTS.md

Exit codes:
    0  success / no blocking issues
    1  verify found an error
    2  usage error
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from . import __version__
from .detect import detect
from .generate import render
from .verify import verify

SEVERITY_RANK = {"error": 0, "warning": 1, "info": 2}


def cmd_detect(args: argparse.Namespace) -> int:
    repo = detect(Path(args.path))
    payload = asdict(repo)
    payload["root"] = str(repo.root)
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


def cmd_generate(args: argparse.Namespace) -> int:
    root = Path(args.path)
    repo = detect(root)
    text = render(repo)

    if args.stdout:
        print(text)
        return 0

    target = root / "AGENTS.md"
    if target.exists() and not args.force:
        print(
            f"agentsmd: {target} already exists; use --force to overwrite, "
            "or --stdout to preview",
            file=sys.stderr,
        )
        return 2

    target.write_text(text, encoding="utf-8")
    print(f"agentsmd: wrote {target}")
    print(
        "agentsmd: the last section lists what detection cannot know. "
        "Fill it in; that part is the value.",
        file=sys.stderr,
    )
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    root = Path(args.path)
    candidates = [root / "AGENTS.md", root / "agents.md", root / ".agents.md"]
    if args.file:
        target = Path(args.file)
    else:
        target = next((c for c in candidates if c.exists()), None)

    if target is None or not target.exists():
        print(f"agentsmd: no AGENTS.md found in {root}", file=sys.stderr)
        return 2

    repo = detect(root)
    result = verify(target, repo)

    if args.format == "json":
        payload = {
            "path": str(result.path),
            "checked_items": result.checked_items,
            "summary": {
                "errors": result.errors,
                "warnings": result.warnings,
                "info": sum(1 for i in result.issues if i.severity == "info"),
            },
            "issues": [asdict(i) for i in result.sorted_issues()],
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        _print_human(result, root, no_color=args.no_color)

    threshold = SEVERITY_RANK["warning"] if args.strict else SEVERITY_RANK["error"]
    worst = min(
        (SEVERITY_RANK.get(i.severity, 9) for i in result.issues),
        default=SEVERITY_RANK["info"],
    )
    return 1 if worst <= threshold else 0


def _print_human(result, root: Path, no_color: bool) -> None:
    def paint(text: str, code: str) -> str:
        return text if no_color else f"\033[{code}m{text}\033[0m"

    red = lambda t: paint(t, "31")  # noqa: E731
    yellow = lambda t: paint(t, "33")  # noqa: E731
    blue = lambda t: paint(t, "36")  # noqa: E731
    dim = lambda t: paint(t, "2")  # noqa: E731
    green = lambda t: paint(t, "32")  # noqa: E731

    try:
        display = result.path.relative_to(root)
    except ValueError:
        display = result.path

    if not result.issues:
        print(green(f"P {display}"))
        print(f"    {dim(f'{result.checked_items} references checked, none broken')}")
        return

    marker = red("E") if result.errors else (yellow("W") if result.warnings else blue("I"))
    counts = []
    if result.errors:
        counts.append(red(f"{result.errors} error"))
    if result.warnings:
        counts.append(yellow(f"{result.warnings} warning"))
    print(f"{marker} {display} — {', '.join(counts)}")

    for issue in result.sorted_issues():
        if issue.severity == "error":
            label = red("error")
        elif issue.severity == "warning":
            label = yellow("warn")
        else:
            label = blue("info")
        location = f" {dim(f'line {issue.line}')}" if issue.line else ""
        print(f"    {label} {dim(issue.rule)} {issue.message}{location}")
        if issue.hint:
            for chunk in issue.hint.split("\n"):
                print(f"         {dim(chunk)}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agentsmd",
        description="Generate and verify AGENTS.md against the repository as it "
        "actually is.",
    )
    parser.add_argument("--version", action="version", version=f"agentsmd {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_detect = sub.add_parser("detect", help="print what was detected, as JSON")
    p_detect.add_argument("path", nargs="?", default=".")
    p_detect.set_defaults(func=cmd_detect)

    p_gen = sub.add_parser("generate", help="write AGENTS.md")
    p_gen.add_argument("path", nargs="?", default=".")
    p_gen.add_argument("--stdout", action="store_true", help="print instead of writing")
    p_gen.add_argument("--force", action="store_true", help="overwrite an existing file")
    p_gen.set_defaults(func=cmd_generate)

    p_ver = sub.add_parser("verify", help="check an existing AGENTS.md")
    p_ver.add_argument("path", nargs="?", default=".")
    p_ver.add_argument("--file", help="path to the file to check")
    p_ver.add_argument("--format", choices=("text", "json"), default="text")
    p_ver.add_argument("--strict", action="store_true", help="warnings fail the run")
    p_ver.add_argument("--no-color", action="store_true")
    p_ver.set_defaults(func=cmd_verify)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())