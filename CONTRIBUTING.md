# Contributing

The most useful contribution is a false positive.

## A document this tool misjudges

If `agentsmd verify` reports a problem with a file that is actually correct, that
is a bug, and it matters more than a missing feature. A verifier's only asset is
that people believe its findings; one confident wrong answer spends that asset.

Open an issue with:

- the line from `AGENTS.md` (redact anything private)
- the rule id that fired
- why you think it is correct
- what the machine has installed, if the finding is about a command

The last point matters more than it looks. Half of all command findings are
"this machine does not have the toolchain", which is a different problem from
"this document is wrong", and the tool tries hard to tell them apart.

## A new rule

Rules are added, never renumbered, and ids are never reused. Answer four
questions in the issue before writing code:

1. What does the bad document look like?
2. What does the good version look like?
3. What does an agent do wrong because of the bad version?
4. Why can this be decided by reading files, rather than by judgment?

Question 4 disqualifies most proposals. "The document is confusing" cannot be
checked. "The document references a path that does not exist" can.

## Severity

This is the whole design, so be conservative:

- **error** — the document will actively mislead an agent. Needs a concrete
  failure story.
- **warning** — probably misleading, judgment involved.
- **info** — worth knowing, safe to ignore.

If a rule depends on a heuristic, it cannot be an error. A verifier that fails
builds over a guess gets removed from CI, and then it catches nothing.

## Adding a rule

```
1. Pick the next free AG0xx id.
2. Add the check in src/agentsmd/verify.py, returning Issue objects.
3. Add two tests: one input that fires, one that must stay quiet.
4. Document it in docs/rules.md with a bad and a good example.
5. If it reflects a real failure mode, mention it in docs/example.md.
```

## Code

- Python 3.11+ (for `tomllib`). No third-party runtime dependencies.
- Tests: `pytest`
- Before submitting: `agentsmd verify .` must pass on this repository, and
  `agentsmd generate . --stdout` must produce a file that the verifier accepts.

That last check is the important one. This tool consumes its own output; a
mismatch between what it writes and what it accepts is a bug by definition.

## Claims

Any statement about what an agent does, or about how a tool behaves, must be
either documented in a file in this repository or removed. A rule that exists
because "it feels right" will be argued about forever; a rule with a failure
story behind it can be evaluated.