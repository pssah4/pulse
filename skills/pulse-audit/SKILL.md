---
name: pulse-audit
description: >
  Security audit with prioritized findings: SAST, OWASP (incl. LLM Top
  10), SCA, supply chain, Zero Trust. The third gate of every feature
  branch in pulse go and /pulse-build (scope branch, no questions); by
  hand with a chosen scope on explicit requests like "security audit",
  "OWASP audit", "Sicherheitsaudit", "dependency audit", or /pulse-audit.
  NOT for one-off questions or generic "security" mentions.
---

# Security Auditor

You perform a comprehensive security audit covering dependency analysis
through code review. Output is a prioritized security report with a
concrete remediation plan.

**Input:** Codebase (`src/`), dependencies, configuration.
**Output:** `_devprocess/analysis/AUDIT-{PROJECT}-{YYYY-MM-DD}.md`.

## Two modes

- **Per-item audit** (before a feature's PR is ready): runs on the
  feature branch against its base; in the chain without a question
  (below), its verdict and fixes go into the same PR.
- **Periodic full-codebase audit**: runs on `audit/<YYYY-MM-DD>`,
  produces a standalone report, and opens a fix or improvement issue per
  deferred finding. Follow-ups get their own branches via `/pulse-build`.

## Scope

In scope: SAST (CWE-based), OWASP Top 10, OWASP LLM Top 10 (when AI/LLM
is present), SCA (dependencies, licenses), Zero Trust (trust boundaries,
input validation), code quality security patterns. Desktop/Electron
runtime when detected. Safe local PoC verification (isolated).

Out of scope: penetration testing against systems you do not own,
compliance certification, architecture design (done by the pulse-plan skill).

## In the chain (pulse go, /pulse-build, `pulse audit <n>`)

After the tests and the review, a fresh session audits the feature
branch. It asks nobody and does no live lookup (Phase 0 is skipped;
the brief names the as-of date of the bundled references instead):

1. `pulse audit <n>` runs `audit_scan.py all --scope branch --base
   <base> --no-baseline` itself before the session starts (in
   `pulse go` outside any agent sandbox, with the network) and saves
   the JSON at `_devprocess/temp/audit-scan.json`. Its brief names
   that path, the SCA status, the as-of date, and the files and
   manifests changed since the previous audit that counted
   (`.git/pulse/audit-context.json`: date, commit, manifests).
2. Triage the JSON (source to sink through the full tree, false
   positives out) and read the changed code yourself.
3. Write `AUDIT.md` at the worktree root: first line `Verdict: pass` or
   `Verdict: block` (block while a Critical or High finding is open),
   then `Coverage: <what the scan and you checked, and what not>`, then
   one line per finding, `- [H-1|M-1|L-1] <file>:<line> <CWE>:
   <what>`. When SCA did not run (`offline`, `error`) or left
   dependencies unchecked (`partial`: a lockfile it could not read, or
   dependencies declared without a lockfile), the Coverage line says
   `SCA unavailable`. Do not change code, do not commit, do not touch
   GitHub.

`pulse audit <n> --record` keeps the verdict, stamped with the commit,
and notes the audit for the next brief. It gives no verdict without the
scan of this commit or without a Coverage line, and none for a pass
whose SCA was `offline`, `error` or `partial` unless the Coverage line
says `SCA unavailable`.

The builder fixes blocking findings, and the chain starts again at the
tests. Medium and Low findings go into the PR body as notes.

## Ask the scope first (by hand, before any scan)

Called by hand, ask the user WHAT to audit (a structured question where
the tool has one, AskUserQuestion in Claude Code). The scan scripts take
a matching `--scope`:

| Scope | What | Use when |
|-------|------|----------|
| `full` | whole codebase | first audit, release gate, periodic (recommended default when no prior baseline) |
| `branch` | branch vs merge-base with `--base` | before a PR / merge (common gate) |
| `commit` | last commit | quick post-commit check |
| `working` | uncommitted + untracked | mid-development |
| `staged` | staged only | pre-commit |
| `range` | free `A..B` | targeted investigation |

A diff scope narrows WHERE findings are reported, never the reachability
context: trace source->sink through the full tree even for a diff scan.
Only `full` advances the delta baseline.

For a release-gate or `full` audit, additionally offer the opt-in
supply-chain stages (a structured question where the tool has one): the
clean-room rebuild executes
the project's build command in a scratch clone (needs
`[audit.supply_chain]` config or `--build-cmd`/`--artifact`), and the
release verify needs the `gh` CLI plus network. Both degrade to honest
not-run ledger entries when declined or unavailable.

## The scan layer (deterministic)

Phases 1-6 are driven by `tools/` (see `tools/README.md`), not manual
grep. Resolve `skills/pulse-audit/tools/...` against the Pulse plugin
root (the directory above the Pulse CLI's `bin/`). The scripts are
offline-graceful and never log secret plaintext; you TRIAGE their JSON
(source->sink, false-positive review) into findings.

```
python3 skills/pulse-audit/tools/audit_scan.py all --scope <S> [--base main] \
    --taxonomy '{"owasp":"...","owasp-llm":"...","cwe-top-25":"..."}'
```

## Phase 0: Live threat currency (always)

The bundled `references/*.md` are the OFFLINE BASELINE. Before scanning,
fetch the CURRENT editions and reconcile:

1. Fetch the current OWASP Top 10, OWASP Top 10 for LLM Apps, and
   MITRE CWE Top 25 with web search where the tool has it (WebSearch and
   WebFetch in Claude Code; official domains: owasp.org,
   genai.owasp.org, cwe.mitre.org). Note new categories vs the baseline.
2. SCA advisories come live from the OSV API in Phase 5.
3. SNAPSHOT the taxonomy set you used (editions + date) and pass it to
   `--taxonomy`; it lands in the report and the delta baseline. The
   Fix-Loop and re-audit run against this snapshot so a fix is verifiable
   against the SAME list; the next fresh audit re-fetches.
4. If offline: fall back to the bundled baseline and record
   `currency: offline` in the report. Never silently claim currency.
5. If CodeQL is installed, refresh the query packs before scanning:
   `codeql pack upgrade codeql/javascript-queries` (plus `python-queries`,
   `go-queries`, `rust-queries` as the project's runtimes demand). A
   stale pack means missing detection rules; the report's Coverage
   section flags packs older than 90 days as a blindspot.

## Audit Phases

Feed each from `audit_scan.py` output; triage into findings.

| Phase | Activity | Reference |
|---|---|---|
| 1. Reconnaissance | `audit_scan.py detect` + `surface`. Map entry points, data flows, trust boundaries. Read the project's own threat doc if present (`REVIEWER_NOTES.md`, `SECURITY.md`); its declared boundaries become mandatory audit targets + regression checks. Internal analysis only. | `references/attack-surface.md`, `references/threat-modeling.md` |
| 2. SAST | `audit_scan.py sast`. Three-layer cascade: CodeQL (taint analysis, when installed and pack cached) + semgrep (AST rules, when installed) + grep (bundled fallback, always). Layers are additive and deduped by fingerprint; a missing tool is documented, never a failure. Triage source->sink. | `references/cwe-patterns.md`, `tools/README.md#codeql-setup-optional-recommended` |
| 3. OWASP Top 10 | Check the Phase-0 current edition (baseline A01-A10). | `references/owasp-checklist.md` |
| 4. OWASP LLM Top 10, agentic and MCP risks | Only if `detect` reports LLM APIs or the repo carries MCP server configuration. Deepen with the agent/injection refs; once the model acts (tools, memory, other agents) or the project uses MCP servers, check the agentic and MCP risks. | `references/owasp-llm-checklist.md`, `references/agentic-mcp.md`, `references/agent-approval-gate.md`, `references/prompt-injection-boundaries.md` |
| 4b. Desktop runtime | Only if `detect` reports `electron`. | `references/desktop-runtime.md` |
| 5. SCA | `audit_scan.py sca` (the OSV API for npm, PyPI, Go, and crates.io; a failed lookup says `offline` or `error`). Classify Runtime / Dev / Transitive. Bundle-reachability check; note that a minified grep can false-negative. | -- |
| 5b. Supply chain | `audit_scan.py supply-chain` (static: lockfile provenance, action pinning, install-script inventory; always part of `all`). Opt-in stages: `--rebuild` (clean-room rebuild, executes the project build) and `--release-verify` (gh attestation of release assets). Stages that did not run appear as not-run in the ledger. | `references/supply-chain.md`, `tools/README.md#supply-chain-checks` |
| 6. Zero Trust + Quality | Input validation, least privilege, defense in depth, fail-closed defaults, audit trail, error handling, resource management, race conditions (CWE-362/367), hardcoded credentials, debug code. Optional isolated PoC. | `references/local-dast.md` |

## Finding format (binding)

Code diff only when the fix is not obvious from the remediation sentence.

```
H-N: <title>
- Severity: Critical | High | Medium | Low | Info
- CWE-ID:   CWE-XXX
- CVSS:     <v3.1 vector>=<score>   (mandatory for High+; omit for Low/Info)
- Location: <file:line>
- FP:       <fingerprint from audit_scan.py>
- Evidence: <snippet / source->sink trace / PoC result>
- Risk:     <one sentence>
- Remediation: <one sentence with concrete action>
```

Status values: `Confirmed`, `Unverified`, `Mitigated`, `False Positive`,
`Resolved`. State the status, never leave a false positive silent.
Consider context (DevDependency vs. Runtime).

**Verification before `Confirmed` (binding).** A grep/semgrep hit is
`Unverified` until you trace it: is the input attacker/user-controlled,
and does it reach the sink? Record the source->sink path in Evidence,
then set `Confirmed`. A hit you cannot trace stays `Unverified` and drops
to P3; never promote an untraced hit to Confirmed. This is what keeps the
report honest (the recurring failure is a plausible-but-unreachable hit
reported as real).

**Positive findings:** up to 3 entries, skip entirely when overall risk
is High or Critical. The team needs the negative list, not encouragement.

Severity schema: **Critical** (immediately exploitable, data loss / RCE),
**High** (exploitable with low effort, significant impact), **Medium**
(exploitable under specific conditions), **Low** (best-practice
improvement), **Info** (note, no direct threat).

## Audit summary block (canonical, define once)

Defined here. Do not restate the block in re-audit output or in the
Handoff Ritual entry; reference the report instead.

```
=== Security Audit Result ===

Overall risk: {Critical / High / Medium / Low}

P1 (Must Fix, Critical + High): {N} findings
- {H-1}: {title}, {file:line}, effort {S/M/L}

P2 (Should Fix, Medium): {N} findings
- {M-1}: {title}, {file:line}, effort {S/M/L}

P3 (Consider, Low + Info): {N} findings
- {L-1}: {title}, effort {S/M/L}

Positive findings: {up to 3, omitted when overall risk High or Critical}
```

## When to run

Before every release, after significant security-relevant changes,
periodically (monthly for active projects), after dependency updates
(SCA phase).

## Create the report

Pre-fill the template deterministically from the scan JSON, then write
the narrative (Risk/Remediation prose, executive summary) on top:

```
python3 skills/pulse-audit/tools/report_assembler.py fill \
    --findings <scan.json> --project {PROJECT} --date {YYYY-MM-DD} \
    > _devprocess/analysis/AUDIT-{PROJECT}-{YYYY-MM-DD}.md
```

`fill` produces the count matrix, P1/P2/P3 buckets, an HONEST tools
ledger (only tools that ran; kills the semgrep-overclaim), and the
mandatory "Coverage and limitations" section. Keep the report within the
`audit` artefact cap; move detail into fix issues if it grows.

---

## Fix-Loop

After the audit, the user picks scope.

### Step 1: Show the summary

Render the audit summary block defined above. Once.

### Step 2: Ask the user

```
How should I handle the findings?

A) Fix all findings (P1 + P2 + P3), then re-audit.
B) Fix only P1, defer P2/P3 to backlog.
C) Approve fixes one by one.
D) Nothing to fix, report only. All findings go to backlog.
```

### Step 3: Fix implementation

For each finding to be fixed: implement the concrete remediation, run
affected tests (no regressions). Then **proof-of-closure**: re-run the
SAME detection that surfaced it (the grep/semgrep rule, or the PoC probe
for a CWE-400) and confirm zero hits; record "Closure evidence:
{command} -> 0" before flipping `Confirmed -> Resolved`. A fix without a
re-detection that comes back clean stays `Confirmed`. On Option C: show
each fix before continuing.

### Step 4: Re-audit (automatic, script-driven delta)

Re-run affected phases against the SAME taxonomy snapshot, then compute
the delta by fingerprint (not by eye):

```
python3 skills/pulse-audit/tools/report_assembler.py delta \
    --before .git/security-audit/prev-run.json \
    --after  .git/security-audit/last-run.json
```

```
=== Re-Audit Delta ===

Before: {N} P1, {N} P2, {N} P3
After:  {N} P1, {N} P2, {N} P3
Resolved: {fingerprints}
New: {if a fix introduced new findings}
```

Adversarial check on any NEW finding a fix introduced: try to refute it
(is it reachable?) before reporting it, so a fix-bypass is caught. Loop
until all in-scope findings resolve or the user aborts. Do not re-render
the full summary block.

### Step 5: Deferred findings -> fix items

Each open finding gets its own fix spec, so `pulse go` plans and builds
it like any other fix:

1. Copy `skills/pulse-build/templates/FIX-TEMPLATE.md` to
   `_devprocess/requirements/fixes/<slug>.md` and fill it from the
   report: title `<H/M/L-ID>: <short risk>`; priority from severity,
   H -> P1, M -> P2, L -> P2 (R6 knows P0 to P2 only); effort from the
   finding; Symptom with the risk, the evidence as `path:line`, and a
   relative link to the report; Root cause from the source-to-sink
   trace; the remediation as FR-01 (EARS) and under Fix; what must keep
   working as FR-02 (unchanged).
2. Commit the fix spec and push the branch: `pulse new` takes a spec
   only once its commit is on origin. Then register it:
   `pulse new fix "<title>" --parent <affected feature or epic> --spec <the fix spec>`.
   It writes `issue:` and `parent:` into the spec; the handoff commit
   takes them along.
3. The report keeps the finding `Confirmed` with the note "Deferred to
   #<n>".

### Step 6: Update artifacts

Audit report (final version), feature specs (security-relevant changes),
decision records (when fixes affect decisions), fix items (open findings).

### Step 7: Pre-release check

The audit is the release gate, so the mechanical document check runs
here: `pulse check` (dead links, missing paths, code paths in decision
records, stubs without an open item). It must report nothing.

---

## Handoff

1. Report: the audit file, findings resolved, findings deferred with
   their item numbers.
2. Commit `docs(audit): <scope> <date>` with `Refs:` for the item and
   the fix items. The body names unresolved P0/P1 findings and why,
   architectural concerns that need redesign rather than patching (for
   a future PLAN), and the release verdict: green, yellow, or
   red.
3. Say the verdict. Green means the release can go.

## Keywords
Security Audit, Security Review, OWASP, SAST, SCA, Vulnerability, CVE,
Threat Model, Dependency Audit, Code Review Security, Fix-Loop, Handoff
