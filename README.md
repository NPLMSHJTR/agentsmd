# agentsmd

**Generate `AGENTS.md` from what your repository actually does — then keep it true.**

[![CI](https://github.com/NPLMSHJTR/agentsmd/actions/workflows/ci.yml/badge.svg)](https://github.com/NPLMSHJTR/agentsmd/actions/workflows/ci.yml)
![python](https://img.shields.io/badge/python-3.11%2B-blue)
![license](https://img.shields.io/badge/license-MIT-green)
![dependencies](https://img.shields.io/badge/dependencies-zero-brightgreen)

`AGENTS.md` is the file a coding agent reads before touching your repository:
how to run the tests, which directories matter, what not to edit. Codex, Cursor,
Claude Code and others all read it.

Two things go wrong with these files, and only one of them is about writing.

The first is that nobody writes them, so the agent rediscovers the build every
session. The second is worse: someone writes one, the build changes three months
later, and the file now instructs the agent to run a command that no longer
exists. The agent runs it, fails, and improvises. That failure is silent and it
is expensive.

`agentsmd` handles both. It generates a draft from files on disk, and it verifies
an existing file against the repository as it is now.

```console
$ agentsmd verify

E AGENTS.md — 2 error, 1 warning
    error AG002 `src/main.ts` is referenced but does not exist
         This is the most common way an AGENTS.md goes stale.
    error AG003 `npm install` uses npm, but this repository uses pnpm
         A wrong package manager produces a lockfile in the wrong format.
    warn  AG007 the repository has a test command but the file never mentions tests
         Add `pnpm test`.
```

## Why verification is the point

Generating a document is a one-time convenience. Keeping it true is the recurring
problem, and it is the one that has no tooling.

The design follows from that:

- **Every generated line traces to a file.** A line that cannot be traced is not
  written. `pnpm test` comes from `package.json`; `.eslintrc.json` is why
  `npx eslint .` appears.
- **No advice.** "Write clean code" is not checkable, so it is not generated. The
  verifier flags it when you add it by hand, because an agent cannot act on it
  and it looks like guidance.
- **Unknown is written as unknown.** If no test runner is detected, the file says
  `not detected` and tells the agent not to invent one. A plausible-looking wrong
  command costs more than a blank.
- **Missing tools are not falsely blamed on the document.** If `pnpm` is not
  installed on the machine, that is a fact about the machine. The verifier says
  "could not check" instead of "stale".

## Install

```bash
pipx install git+https://github.com/NPLMSHJTR/agentsmd
```

Or from source, with no dependencies:

```bash
git clone https://github.com/NPLMSHJTR/agentsmd
cd agentsmd
python -m agentsmd detect .
```

Python 3.11+ is required, for `tomllib`. There are no third-party dependencies.

## Use

```bash
agentsmd detect .              # what was found, as JSON
agentsmd generate .            # write AGENTS.md
agentsmd generate . --stdout   # preview without writing
agentsmd generate . --force    # overwrite an existing file
agentsmd verify .              # check the existing AGENTS.md
agentsmd verify . --strict     # let warnings fail the build
agentsmd verify . --format json
```

Exit codes:

| code | meaning |
| --- | --- |
| `0` | generated, or verify found no errors |
| `1` | verify found an error (or a warning with `--strict`) |
| `2` | usage error, or no `AGENTS.md` to verify |

## In CI

The verifier is the part worth automating. A build-file change should not be able
to silently break the agent instructions.

```yaml
name: check AGENTS.md
on: [push, pull_request]
jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install git+https://github.com/NPLMSHJTR/agentsmd
      - run: agentsmd verify . --strict
```

## The rules

| id | severity | what it checks |
| --- | --- | --- |
| AG001 | error | a command in backticks has a first word that can run |
| AG002 | error | a path in backticks exists |
| AG003 | error | the file names the package manager the repo actually uses |
| AG004 | warning | commands in fenced shell blocks can run |
| AG006 | warning | no line is advice an agent cannot verify |
| AG007 | warning | the file covers tests and generated files when they exist |

Full rationale, with a bad and a good example for each, is in
[docs/rules.md](docs/rules.md).

## What it deliberately does not do

- **It does not write your conventions.** The last section of the generated file
  lists what detection cannot know: review-only conventions, deprecated areas,
  the definition of done. That part is the value and it has to be written by
  someone who knows the project.
- **It does not check that commands succeed.** It checks that the binary exists.
  A command that exists and fails is a different problem.
- **It does not guess.** Unknown values are `None`, not defaults.

## Docs

| file | contents |
| --- | --- |
| [docs/rules.md](docs/rules.md) | every rule: why, and bad vs good |
| [docs/example.md](docs/example.md) | a full worked example, before and after |

## Status

Version 0.1.0. Rule ids are stable and never reused.

Known limits, stated plainly:

- Command existence is checked with `shutil.which`. A shell builtin, an alias, or
  a script that only works under a wrapper will be reported as missing.
- Detection covers Node, Python, Rust, Go and Ruby. Others get structure only,
  and the file says so.
- Advice detection is pattern-based. It catches the common phrasings and misses
  anything creative, which is why AG006 is a warning.

## License

MIT.