# Rules

Every rule, why it exists, and a bad and good example. Severity follows the same
logic as everywhere else: **error** means the file will mislead an agent,
**warning** means it probably will.

---

## AG001 — a command's first word can run

**error**

The most direct failure. The file says to run something, and that something is
not on the machine.

```
error AG001 `pnpm test` is presented as a command, but `pnpm` cannot be run:
             not found on PATH
```

**Why it is an error and not a warning.** A document that instructs an agent to
run a missing binary does not fail loudly. The agent gets an error, then
improvises a substitute, and the substitute is usually wrong in a way that is
invisible until review. The cost is a wasted turn plus a plausible-looking wrong
change.

**When it does not fire.** If the project's own package manager is not installed,
this is a fact about the machine rather than about the document. The rule
downgrades to info and says so:

```
info AG001 `pnpm test` could not be checked: `pnpm` is not installed on this
            machine
```

That distinction is deliberate. A tool that reports "your document is broken"
every time it runs on a machine without the toolchain gets uninstalled, and then
it catches nothing.

---

## AG002 — a referenced path exists

**error**

```
# bad
See `src/main.ts` for the entry point.

# good (after src/main.ts exists)
See `src/main.ts` for the entry point.
```

This is the single most common way these files rot. A file gets renamed or a
directory gets restructured, and the reference stays behind. The agent follows
the reference into nothing.

**What counts as a path claim.** Only backticked text with no spaces that contains
a path separator or starts with `.`, and does not begin with a hyphen. That
excludes prose (`--verbose` is a flag, not a path) and URLs.

---

## AG003 — the package manager is the one the repo uses

**error**

```
# bad, in a pnpm repository
Install with `npm install`.

# good
Install with `pnpm install`.
```

Three package managers in the Node ecosystem produce three incompatible lockfiles.
An agent told to use the wrong one will either overwrite your lockfile or create a
second one, and the conflict surfaces much later as a CI failure that looks
unrelated.

The repository's package manager is detected from the lockfile, which is a fact,
not from the presence of a config entry, which can be aspirational.

---

## AG004 — commands in a fenced block can run

**warning**

Fenced code is copied verbatim. When an agent sees this, it runs the line:

```bash
pnpm run build
```

If the fence is illustrative rather than runnable, say so, or tag it:

````
```text
pnpm run build
```
````

**Why a warning.** Some fences legitimately contain output, pseudo-code, or a
command for another platform. The rule cannot tell intent from content. Tagging
the fence as `text` is the escape hatch, and it costs one word.

---

## AG006 — no advice an agent cannot verify

**warning**

```
# bad
Write clean, readable, maintainable code at all times.
Follow best practices.
Be careful with edge cases.

# good
The parser in `src/parse.py` handles user input; it must never raise. Return
an error value instead and let the caller decide.
```

The bad lines are not wrong. They are unusable. An agent cannot check whether it
was careful enough, so the instruction produces no behaviour change while making
the author feel covered.

**The good version is longer and that is the point.** It names a file, a
constraint, and the required behaviour at the boundary. That is something an
agent can follow and something a reviewer can check.

Detected patterns include `write/keep/ensure ... clean/readable/simple`,
`follow best/good practices`, `prefer small/simple`, `be kind/nice/careful`,
`think carefully/step by step`, and `do not hallucinate`.

---

## AG007 — the file covers what the repo has

**warning**

Two cases:

```
warn AG007 the repository has a test command but the file never mentions tests
info AG007 3 generated file(s) exist but the file does not warn against editing them
```

Not knowing how to run the test suite is the most expensive gap an agent can hit:
it will either skip testing or invent a command. Not knowing which files are
generated means every edit to them is thrown away.

The generated draft covers both automatically, which is why a file created by
`agentsmd generate` never trips this rule.

---

## Where the rules come from

Not from a style guide. Each one corresponds to a failure that produces a
concrete cost:

| rule | failure | cost |
| --- | --- | --- |
| AG001 | missing binary | wasted turn, improvised substitute |
| AG002 | stale path | agent reads nothing, guesses |
| AG003 | wrong package manager | duplicate lockfile, late CI failure |
| AG004 | unrunnable fenced command | immediate error, lost context |
| AG006 | unverifiable advice | no behaviour change, false coverage |
| AG007 | missing test instructions | tests skipped or faked |

The unifying idea: an agent's time is spent on discovery. A repository file is
worth writing exactly to the extent it removes discovery that would otherwise
cost a turn. Anything that does not remove discovery is decoration.