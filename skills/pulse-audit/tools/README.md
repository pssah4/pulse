# skills/pulse-audit/tools/

Deterministic scan layer for the `security-audit` skill. Turns the
manual "grep for eval(), exec(), ..." checklist into reproducible,
scriptable scans with a stable finding identity and an honest tool
ledger, so a re-audit delta is computed, not eyeballed.

The skill calls these scripts; the LLM triages the JSON they emit
(source -> sink, false-positive review) and writes the report prose on
top. The scripts never decide severity narrative and never fetch threat
lists (that is the skill's live-currency step). The scanner's own network
call is the dependency advisory lookup at the OSV API. Semgrep fetches
its rules from its registry, and the opt-in cleanroom stages install
dependencies and verify attestations over the network.

## Design contract (binds every script)

- **stdlib-only Python** (3.9+), one Node ESM probe. No pip installs.
- **Offline-graceful.** Every external tool (codeql, semgrep,
  gitleaks) is optional. Missing tool -> honest entry in the `tools[]`
  ledger (`status: unavailable | error`) and the scan continues.
  Without network the SCA entry says `offline` with the reason and the
  exit code is 2. Nothing hard-aborts on a missing tool.
- **Never log secrets.** Secret matches are redacted to a 4-char
  preview + length + short sha1, in output and on stderr. No plaintext,
  ever.
- **Deterministic.** A finding's fingerprint is
  `sha1(cwe | path | normalized-snippet)[:8]`, with NO line number or
  timestamp, so it survives renumbering and two runs over the same code
  produce identical ids.
- **Scope-aware, not scope-blind.** A diff scope narrows WHERE findings
  are reported, never the reachability context the LLM reasons over.
- **Baseline under `.git/`.** `.git/security-audit/{last,prev}-run.json`,
  never committed. A diff-scope run never clobbers a `full` baseline.

## Files

| File | Role |
|------|------|
| `audit_scan.py` | Orchestrator. Subcommands `detect`, `surface`, `sast`, `secrets`, `sca`, `supply-chain`, `all`. |
| `report_assembler.py` | `fill` (pre-fill AUDIT-TEMPLATE from findings JSON) + `delta` (re-audit set diff by fingerprint). |
| `lib/findings.py` | `Finding` dataclass, `fingerprint`, `redact`, baseline read/write/rotate, `delta`. |
| `lib/scope.py` | Resolve a scope category (`full`/`working`/`commit`/`staged`/`branch`/`range`) to a file list via git. |
| `lib/detectors.py` | Project-type detection (electron/obsidian-plugin/web-app/cli/library, node/python/...) + attack-surface enumeration. |
| `lib/osv.py` | SCA: reads lockfiles and pinned requirements, looks up advisories at the OSV API. |
| `lib/supply_chain.py` | Static supply-chain checks: lockfile provenance, action pinning, install-script inventory, manifest hygiene, python pins. Offline, no subprocesses. |
| `lib/cleanroom.py` | Opt-in stages: clean-room rebuild (scratch clone, scrubbed env, hash compare) + `gh attestation verify` of release assets. |
| `poc/redos_probe.mjs` | Opt-in isolated ReDoS measurement of ONE suspect regex (worker_thread + hard deadline). |
| `tests/` | Assertion-based tests, runnable without pytest, also pytest-discoverable. |

## CodeQL setup (optional, recommended)

Without CodeQL the SAST layer runs semgrep (if installed) plus the
bundled grep-fallback. That covers pattern-level bugs but misses ones
that require real source-to-sink taint analysis. Installing CodeQL
adds a third layer that catches the taint-only class.

The skill never breaks when CodeQL is absent: the tool ledger records
`codeql: unavailable` and the cascade falls through to semgrep and
grep. If CodeQL is on PATH but the language pack is not cached, the
ledger records `pack-missing` with the exact download command as its
reason.

```bash
# One-time install (macOS)
brew install --cask codeql

# Download the language packs the project needs: JS and TS, Python, Go, Rust
codeql pack download codeql/javascript-queries
codeql pack download codeql/python-queries
codeql pack download codeql/go-queries
codeql pack download codeql/rust-queries

# Refresh periodically; the report flags packs older than 90 days
codeql pack upgrade codeql/javascript-queries
```

The per-language CodeQL DB is built for each run under the git dir all
worktrees of a clone share, at `security-audit/codeql-db-<lang>-<worktree>/`
(one per worktree, so parallel audits do not overwrite each other), and is
removed with its SARIF once the findings are read. The scan orchestrator
idempotently adds the pattern to `.git/info/exclude` on first run.

### Grep-fallback limits

The pattern-based grep-fallback in [audit_scan.py](audit_scan.py) is
intentionally broad: it flags any occurrence of `\.\./`, `path.join(...,
req...)`, `eval(...)`, `.innerHTML =`, etc., without checking whether the
input is actually attacker-controlled. That is fine when CodeQL runs
alongside (the taint layer rejects unreachable hits), but on
CodeQL-less runs the grep layer will produce known false positives for
path-manipulation code (`path.join(homeDir, 'foo')`) and for
documentation strings that contain a literal `../`. Two mechanisms
reduce the noise:

* [`lib/skip_rules.py`](lib/skip_rules.py) skips test fixtures,
  minified/bundled assets, and `dist/`/`build/` outputs by path glob.
* A per-file header `# security-audit-scan: skip` opts a specific file
  out (used by the detector modules that store the CWE patterns as data
  literals and would otherwise self-match).

Beyond these, path-manipulation false positives on grep-only runs are
the known trade-off for pattern breadth. Install CodeQL to remove the
false-positive class entirely for supported languages.

## Dependency advisories (SCA)

`lib/osv.py` is the only SCA source. It reads every `package-lock.json`
(v1 to v3), `npm-shrinkwrap.json`, `pnpm-lock.yaml` (v6, v9),
`yarn.lock` (v1, berry), `requirements*.txt` (only `==` pins),
`poetry.lock`, `uv.lock`, `pylock.toml` and `pylock.<name>.toml`
(PEP 751), `Pipfile.lock`, `go.sum` and `Cargo.lock` in the tree (dot
directories and `node_modules` skipped; from `uv.lock` and `Cargo.lock`
it leaves out the project itself, its workspace members and path
dependencies), sends the package versions to
`https://api.osv.dev/v1/querybatch`,
then fetches each advisory once from `/v1/vulns/{id}`. Each finding
carries the manifest, `package`, `version`, `advisory` (GHSA, PYSEC,
GO, RUSTSEC), `aliases` (CVE), `published` and `fixed` (lowest fixed
release above the installed one). The severity is the GHSA rating;
advisories without one count as medium, malicious packages (`MAL-`) as
critical. A non-GHSA twin of a GHSA advisory is dropped.

The ledger entry `osv` says what happened: `ran` (with package count and
manifests), `partial` (a lockfile that does not parse, one in a format
its reader does not know, such as `pnpm-lock.yaml` before v6 or package
entries of a TOML lockfile in another layout, or one without a reader
here, such as `Gemfile.lock` or `bun.lock`; or dependencies declared, not
locked: a `requirements*.txt` line without `==`, a `package.json` with
`dependencies` or `devDependencies` without an npm, pnpm, yarn or bun
lockfile, a `pyproject.toml` with `[project]` dependencies without
`uv.lock`, `poetry.lock`, `pdm.lock` or `pylock.toml`, where a lockfile in
a directory above counts as for workspace members; the reason names each
file, the rest was checked), `not-applicable` (no dependency declared or
locked; a lockfile without dependencies is read with none), `offline` (no route,
DNS, refused proxy, timeout) or `error` (HTTP error, unreadable answer),
each with its reason.
`meta.offline` follows the real failure, and the report names the blind
spot. The chain in `pulse audit` counts a pass after `partial`, `offline`
or `error` only when the Coverage line says `SCA unavailable`.

In a diff scope (`branch`, `commit`, ...) an advisory blocks only when
its manifest changed in that scope. Advisories of unchanged manifests
stay in the result as `info` notes, their rating kept in the message, so
a docs commit does not inherit every CVE of the repository.

## Supply-chain checks

Stage 1 is static and part of every `all` run: lockfile provenance
(registry host allowlist, sha512 integrity, git/http dependencies),
GitHub Action pinning (mutable tag vs commit SHA, permissions blocks,
persist-credentials, `npm install` vs `npm ci`, unpinned pip installs),
install-script inventory (delta-able info findings), manifest hygiene
(`.npmrc` ignore-scripts policy, stale overrides), and Python
requirement pins.

Stages 2 and 3 execute external commands and are opt-in only:

```bash
# Static checks (also included in `all`)
python3 audit_scan.py supply-chain

# Stage 2: clean-room rebuild (runs the project's build in a scratch clone)
python3 audit_scan.py supply-chain --rebuild \
    --build-cmd "node esbuild.config.mjs production" \
    --artifact main.js --artifact styles.css

# Stage 3: verify provenance attestations of the latest release assets
python3 audit_scan.py supply-chain --release-verify
```

Config precedence: CLI flags > `[audit.supply_chain]` in the target
repo's `.pulse/config.toml` (or `.dia/config.toml` before migration) >
defaults. See
`references/supply-chain.md` for what each stage proves, the triage
guidance, and the safety notes for the rebuild (allowlist env,
`--ignore-scripts`, scratch clone). Workflow/lockfile YAML checks are
regex-based; exotic syntax can slip through and the report's
limitations block says so honestly.

## Path resolution

Skill text uses `python3 skills/pulse-audit/tools/audit_scan.py ...`;
the agent expands the leading `skills/...` against the Pulse plugin root,
the directory above the Pulse CLI named at session start. The scripts
resolve the target
repo root themselves via `git rev-parse --show-toplevel`, so the first
positional argument (a project root) is optional.

## Quick reference

```bash
# Optional; defaults to the git root
ROOT=/path/to/target/project

# What kind of project is this? (gates which references/tools apply)
python3 audit_scan.py detect "$ROOT"

# Enumerate trust-boundary entry points in scope
python3 audit_scan.py surface "$ROOT" --scope full

# Dependency advisories only (needs network; offline exits 2)
python3 audit_scan.py sca "$ROOT"

# Full scan, snapshot the live taxonomy set, write the baseline
python3 audit_scan.py all "$ROOT" --scope full \
    --taxonomy '{"owasp":"2025","owasp-llm":"2025","cwe-top-25":"2024"}' \
    > /tmp/audit-findings.json

# Scope a scan to the branch under review (vs merge-base with main)
python3 audit_scan.py all "$ROOT" --scope branch --base main

# Pre-fill the human report from the findings JSON
python3 report_assembler.py fill --findings /tmp/audit-findings.json \
    --project vault-operator --date 2026-07-23 > AUDIT-vault-operator-2026-07-23.md

# Re-audit delta: what got resolved / introduced since the last full run
python3 report_assembler.py delta \
    --before .git/security-audit/prev-run.json \
    --after  .git/security-audit/last-run.json

# Opt-in: measure whether a flagged regex actually backtracks catastrophically
node poc/redos_probe.mjs --pattern '(a+)+$' --pump-len 40 --pump-suffix '!' --deadline-ms 500
```

## Scope categories

| Scope | Files | git derivation | Use when |
|-------|-------|----------------|----------|
| `full` | all tracked | `git ls-files` | first audit, release gate, periodic |
| `working` | uncommitted + untracked | `git diff HEAD` + `ls-files -o` | mid-development |
| `commit` | last commit | `git diff HEAD~1..HEAD` | quick post-commit check |
| `branch` | branch vs merge-base | `git diff $(merge-base <base> HEAD)..HEAD` | before PR / merge |
| `range` | free range | `git diff A..B` | targeted investigation |
| `staged` | staged only | `git diff --cached` | pre-commit hook |

Only `full` advances the delta baseline. A diff scope reports against
the persisted full baseline without overwriting it.

## Exit codes

`0` no findings, `1` findings present, `2` usage/setup error or an SCA
lookup that failed or left dependencies unchecked (`offline`, `error`,
`partial`); the JSON is printed in every case.

## Running the tests

```bash
for t in skills/pulse-audit/tools/tests/test_*.py; do python3 "$t" || break; done
```

`test_redos_probe.py` skips (passes) if `node` is not installed; every
other test is pure stdlib Python.

## Why a scan layer at all

The pre-existing skill asked the model to grep by hand. That is not
reproducible (two runs differ), it is token-expensive, it silently
misses hits, and the re-audit "what changed" step was done by eye. A
scriptable orchestrator with fingerprinted findings makes the scan
deterministic and the delta reliable, while the honest `tools[]` ledger
kills the tool-overclaim where a report lists `semgrep` although only a
grep fallback ran.
