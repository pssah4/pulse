---
title: Security Audit
description: "Comprehensive security audit covering OWASP Top 10, OWASP LLM Top 10, SAST, SCA, and Zero Trust. Two modes: per-item audit and periodic full-codebase audit."
---

# Security Audit

`/pulse-audit` (in Codex `$pulse:pulse-audit`) runs a security audit on the codebase and
produces a prioritised remediation plan with traceable findings.

**Input:** Codebase, dependencies, configuration, the feature or
release scope being audited
**Output:** Audit report at
`_devprocess/analysis/AUDIT-{PROJECT}-{YYYY-MM-DD}.md`, plus one fix
item per deferred `H-N`, `M-N`, or `L-N` finding

## Two modes

### Per-item audit

The third gate of every feature branch in [`pulse go`](./pulse-go)
and [`/pulse-build`](./pulse-build), after the tests, in one fresh
session with the review, also when the spec or the PLAN has
`risk: [security]`. It asks nobody and runs in two steps:

1. **Pulse runs the scan itself.** `pulse go` runs
   `audit_scan.py all --scope branch --base <base> --no-baseline` before
   the session starts, outside every agent sandbox and with the network,
   and saves its JSON at `_devprocess/temp/audit-scan.json`. A subagent
   of `/pulse-build` runs the same scan itself.
2. **A fresh session triages it.** The auditor did not build the item.
   Its brief names the scan's JSON, the SCA status
   (`SCA (OSV) ran over <count> packages`, or `offline`, `error`,
   `partial`, `not-applicable` with the reason), the as-of date of the bundled
   references with a warning for any reference undated or at least 90
   days old, and the files and manifests changed since the previous audit
   that counted in this clone (`~/.cache/pulse/<clone>/audit-context.json`). It does no live lookup of its own.
   It triages the findings from source to sink, reads the changed code,
   and writes `AUDIT.md` where the brief says (the worktree root, or in
   `pulse go` the path it names beside the checkout):

```
Verdict: block
Coverage: SAST grep and semgrep on the branch diff, SCA over 212 packages, secrets; no CodeQL
- [H-1] src/api.py:40 CWE-89: user input reaches the SQL string unescaped
- [M-1] package-lock.json:1 CWE-1395: js-yaml 4.1.0 has an advisory with a fixed version
```

It blocks while a Critical or High finding is open, and a report
without a Coverage line is no verdict at all ([the Coverage
rule](#the-coverage-rule)). The builder fixes blocking findings; then
the tests run again and the audit looks again. Medium and Low findings
go into the PR body as notes.

### Periodic full-codebase audit

A deep audit across the whole codebase, independent of any single
feature, on `audit/{YYYY-MM-DD}`. Triggered manually or on a calendar
cadence (quarterly, before a major release, after a significant
dependency upgrade).

The two modes share the same six audit phases below; only the scope
differs.

## Scope

Called by hand, `/pulse-audit` first asks what to audit: `full` (the
whole codebase), `branch` (against a base, default the base branch),
`commit`, `working` (uncommitted and untracked), `staged`, or `range`
(`A..B`). It then runs the scanner with that scope itself,
`python3 skills/pulse-audit/tools/audit_scan.py all --scope <scope>`,
and asks the OSV API over the network; without network, the lookup says
`offline`. In the chain it never asks.

## The Coverage rule

An audit counts only when it says what it checked and stands on the
scan of the commit it judges. `pulse go` gives no verdict when:

- `AUDIT.md` has no `Coverage:` line (what the scan and the auditor
  checked, and what not);
- there is no scan of this commit;
- the session changed the branch: the brief notes HEAD and the working
  tree before the session, and the verdict reads that note once;
- the verdict is `pass` while the OSV lookup did not run (`offline`,
  `error`) or left dependencies unchecked (`partial`: a lockfile it could
  not read, or a `package.json`, `pyproject.toml` or version range in
  `requirements*.txt` without a lockfile) and the Coverage line does not
  say `SCA unavailable`.

A scan that fails or times out gives no verdict either, and no audit
session starts for it. One scan gives one verdict: reading the report takes
the saved JSON away. An audit that counts is noted in
`~/.cache/pulse/<clone>/audit-context.json` (date, commit, manifests), so the next
brief can say what changed since.

## Six audit phases

1. **Reconnaissance.** Identify tech stack, dependencies, existing
   security measures, threat model assumptions.
2. **SAST (Static Application Security Testing).** CWE-based static
   analysis with grep / pattern matching from
   `references/cwe-patterns.md`.
3. **OWASP Top 10.** All 10 categories (A01 to A10) with concrete
   patterns.
4. **OWASP LLM Top 10.** LLM01 to LLM10, relevant when the project
   uses LLM APIs.
5. **SCA (Software Composition Analysis).** Dependency advisories
   from the OSV API, the only SCA source, for npm, PyPI, Go, and
   crates.io: it reads the lockfiles and pinned requirements, asks which
   versions carry advisories, and fetches each advisory with its
   aliases, rating, and fix. There is no `npm audit`, `pip-audit`, or
   `cargo audit` step. Without network the scan says `offline`, never a
   clean result. Dependencies declared without a lockfile make it
   `partial` and are named; `not-applicable` means nothing is declared.
   In a diff scope only advisories of a manifest the scope changed
   block; the others stay as notes.
6. **Zero Trust and Code Quality.** Input validation, least
   privilege, fail-closed defaults, audit trail, hardcoded
   credentials, debug code in production.

## How current the knowledge is

- **Advisories** come live from OSV on every scan, never from a bundled
  list.
- **The bundled references** (OWASP Top 10, OWASP LLM Top 10, CWE
  patterns, agentic and MCP risks) carry an `as-of` date in their front
  matter. The brief names the oldest of these dates, and the brief and
  the report warn when a reference is undated or at least 90 days old.
- **Called by hand**, the audit first fetches the current OWASP and CWE
  editions from the web and records the editions it used; offline it
  falls back to the bundled references and records `currency: offline`.
  In the chain it skips that lookup and names the as-of date instead.

## Supply-chain phase

Between SCA and Zero Trust, the audit runs a supply-chain phase
(`audit_scan.py supply-chain`) in up to three stages:

- **Static checks (always part of a full audit).** Lockfile
  provenance, CI action pinning, and an inventory of install
  scripts. No network, no build execution.
- **Clean-room rebuild (opt-in, `--rebuild`).** Rebuilds the
  project in a scratch clone and compares the artifact against the
  distributed one. It executes the project's build command, so it
  runs only after explicit confirmation and needs a configured
  build command (`[audit.supply_chain]` in the config or
  `--build-cmd`/`--artifact`).
- **Release verification (opt-in, `--release-verify`).** Verifies
  the GitHub attestation of release assets via the `gh` CLI; needs
  network access.

The report keeps an honest ledger: only tools and stages that
actually ran are claimed, and declined or unavailable stages appear
explicitly as not-run instead of silently vanishing. A skipped
rebuild is a documented gap, not a passed check.

## Severity schema

- **H (High)**: exploitable, significant impact, fix immediately
- **M (Medium)**: exploitable under specific conditions, fix in
  this cycle
- **L (Low)**: low risk, best-practice improvement, schedule
- **Info**: note, no direct threat, optional context

Each finding gets an id of the form `H-N`, `M-N`, `L-N` (severity
plus a counter local to the audit report).

## Findings as fix items

The report holds every finding with severity, priority from severity
(H to P1, M to P2, L to P3), evidence as `path:line`, and the risk in
one line. Each finding the team does not fix in this run becomes a fix
item under the affected feature or epic, with priority P1 for High and
P2 for Medium and Low (a fix spec knows P0 to P2 only), pointing at the
report, and
the report notes "Deferred to #n". A High finding the team decides not
to fix stays an open item with the reason in the report; there is no
silent "we'll get to it" state.

## Fix-loop

Called by hand, findings trigger a fix-loop with 4 user options:

- **A)** Fix all findings automatically
- **B)** Fix only High findings, defer the rest
- **C)** Approve fixes one by one
- **D)** Report only, no fixes in this run

Each iteration re-runs the audit phase for the affected category
with fresh output before claiming the finding is closed. See
[Verification Gates](../concepts/verification-gates).

## Handoff

Before the handoff, `pulse check` runs as the mechanical release gate
(dead links, missing paths, code paths in decision records, stubs
without an open item). The report is committed
(`docs(audit): <scope> <date>`, with `Refs:` for the fix items); the commit body names
unresolved P0 and P1 findings, architectural concerns that need
redesign rather than patching, and the release verdict: green, yellow,
or red.

## Read the skill file

[`skills/pulse-audit/SKILL.md`](https://github.com/pssah4/pulse/blob/main/skills/pulse-audit/SKILL.md) on GitHub.
