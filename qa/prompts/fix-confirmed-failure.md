# Cursor / Sonnet fix prompt — confirmed failure only

You are fixing **one** confirmed failure reproduced by the TrueLine QA harness.
The harness produced the evidence below. Do not propose fixes for anything
that is not represented in that evidence.

## Rules

- **Scope is the single confirmed failure pasted below. Nothing else.**
- Do not refactor adjacent code. Do not "while you're in there" anything.
- Do not modify KMZ parsing/rendering, the topology sidecar, pilot token
  lifecycle, or auth token rotation logic.
- Do not modify routes that are not directly implicated by the failure.
- Do not invent new features, abstractions, helpers, or wrappers.
- Provide **full-file replacements** for every file you change — never partial
  diffs, never `// ...` placeholders.
- After the change, the user will run `npm run qa:all` from `qa/` and re-paste
  the new diagnosis packet. The same failure must not appear again.

## Acceptance check

Your output is wrong if:

- It edits files unrelated to the failure category and suspected owner.
- It changes more than one route handler when only one is implicated.
- It removes existing tests or weakens existing assertions.
- It claims a fix without referencing the specific failed URL, status, or
  error message from the evidence.

## Evidence

> Paste the failure card (title + evidence + category + suspected owner)
> from `diagnosis-packet.md` here.

```
<<PASTE CONFIRMED FAILURE EVIDENCE HERE>>
```

## Output format

1. One paragraph: which file(s) you will change and why.
2. Full-file replacements, one fenced block per file, with the file path on
   the line above each block.
3. The exact command(s) you would run to verify the fix locally (typically
   `npm run qa:all` from `qa/`).
