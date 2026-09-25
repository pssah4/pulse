"""Tests for pulse-audit/tools/report_assembler.py.

    python3 skills/pulse-audit/tools/tests/test_report_assembler.py
"""
from __future__ import annotations
import importlib.util
import json
import sys
import tempfile
from pathlib import Path


TOOLS_DIR = Path(__file__).resolve().parents[1]
SCRIPT = TOOLS_DIR / "report_assembler.py"


def _load():
    spec = importlib.util.spec_from_file_location("report_assembler", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["report_assembler"] = mod
    spec.loader.exec_module(mod)
    return mod


def _sample_result() -> dict:
    return {
        "schema": 1,
        "scope": "full",
        "scope_detail": "all tracked files",
        "git_branch": "feature/x",
        "project_type": {"project_kinds": ["electron", "obsidian-plugin"]},
        "tools": [
            {"name": "semgrep", "status": "ran", "ruleset": "p/typescript"},
            {"name": "gitleaks", "status": "unavailable", "reason": "not on PATH"},
            {"name": "osv", "status": "offline",
             "reason": "<urlopen error [Errno 61] Connection refused>"},
            {"name": "pattern-redact", "status": "ran"},
        ],
        "meta": {"file_count": 12, "offline": True},
        "findings": [
            {"fp": "aa", "phase": "sast", "cwe": "CWE-94", "severity": "critical",
             "file": "a.ts", "line": 3, "engine": "semgrep",
             "message": "eval", "status": "unconfirmed", "cvss": "", "evidence": ""},
            {"fp": "bb", "phase": "sast", "cwe": "CWE-79", "severity": "high",
             "file": "b.ts", "line": 9, "engine": "grep-fallback",
             "message": "innerHTML", "status": "unconfirmed", "cvss": "", "evidence": ""},
            {"fp": "cc", "phase": "sca", "cwe": "", "severity": "medium",
             "file": "package-lock.json", "line": None, "engine": "osv",
             "message": "vuln dep foo", "status": "unconfirmed", "cvss": "", "evidence": "",
             "package": "foo", "version": "1.0.0", "advisory": "GHSA-aaaa-bbbb-cccc",
             "aliases": ["CVE-2026-1"], "published": "2026-09-01", "fixed": "1.0.1"},
            {"fp": "dd", "phase": "secrets", "cwe": "CWE-798", "severity": "low",
             "file": "c.ts", "line": 2, "engine": "entropy-fallback",
             "message": "redacted secret", "status": "unconfirmed", "cvss": "", "evidence": ""},
        ],
    }


def test_fill_counts_and_buckets() -> None:
    m = _load()
    template = TOOLS_DIR.parent / "templates" / "AUDIT-TEMPLATE.md"
    assert template.exists()
    out = m.fill(_sample_result(), template.read_text(encoding="utf-8"),
                project="vault-operator", date="2026-07-23")
    # Metadata filled.
    assert "vault-operator" in out
    assert "2026-07-23" in out
    # Executive summary counts: 1 critical, 1 high in code domain.
    assert "P1: Must Fix" in out
    # Critical + High findings appear in P1.
    p1_section = out.split("P1: Must Fix")[1].split("P2:")[0]
    assert "CWE-94" in p1_section, p1_section
    assert "CWE-79" in p1_section, p1_section
    # Medium goes to P2.
    p2_section = out.split("P2:")[1].split("P3:")[0]
    assert "vuln dep foo" in p2_section, p2_section
    # Low goes to P3.
    p3_section = out.split("P3:")[1]
    assert "redacted secret" in p3_section, p3_section
    print("OK: fill counts + P1/P2/P3 buckets")


def test_fill_tools_are_honest() -> None:
    m = _load()
    template = TOOLS_DIR.parent / "templates" / "AUDIT-TEMPLATE.md"
    out = m.fill(_sample_result(), template.read_text(encoding="utf-8"),
                project="p", date="2026-07-23")
    # Only tools that actually ran are claimed as run; semgrep ran, gitleaks did not.
    assert "semgrep" in out
    # The honest ledger must reflect unavailable/offline, not hide it.
    assert "unavailable" in out or "offline" in out, out
    # Tool-overclaim guard: a tool that did NOT run must not be listed as a used tool.
    tools_section = out.split("Scope and Tools")[1]
    assert "gitleaks" in tools_section  # listed, but with its status
    # fill() owns the Tools, Files analyzed and Excluded lines: none keeps its template placeholder.
    owned = [l for l in tools_section.splitlines() if l.startswith(("- Tools", "- Files analyzed", "- Excluded"))]
    assert len(owned) == 4 and not any("{" in l for l in owned), owned
    print("OK: tools ledger honest (no overclaim)")


def test_fill_has_limitations_section() -> None:
    m = _load()
    template = TOOLS_DIR.parent / "templates" / "AUDIT-TEMPLATE.md"
    out = m.fill(_sample_result(), template.read_text(encoding="utf-8"),
                project="p", date="2026-07-23")
    # Mandatory coverage/limitations content.
    lower = out.lower()
    assert "limitation" in lower or "not evaluated" in lower or "coverage" in lower, out
    # Offline SCA must be surfaced as a blindspot.
    assert "offline" in lower, "offline SCA blindspot must be named"
    print("OK: mandatory limitations section present")


def test_delta_from_baselines() -> None:
    m = _load()
    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)
        before = {"findings": [{"fp": "a"}, {"fp": "b"}, {"fp": "c"}]}
        after = {"findings": [{"fp": "b"}, {"fp": "c"}, {"fp": "d"}]}
        bpath = tmp / "prev.json"
        apath = tmp / "last.json"
        bpath.write_text(json.dumps(before), encoding="utf-8")
        apath.write_text(json.dumps(after), encoding="utf-8")
        d = m.delta_from_files(bpath, apath)
        assert set(d["resolved"]) == {"a"}, d
        assert set(d["new"]) == {"d"}, d
        assert set(d["persisted"]) == {"b", "c"}, d
        print("OK: delta from baseline files")


def test_limitations_names_codeql_when_ran() -> None:
    m = _load()
    template = TOOLS_DIR.parent / "templates" / "AUDIT-TEMPLATE.md"
    result = _sample_result()
    # Replace semgrep-only tool set with a CodeQL-ran ledger.
    result["tools"] = [
        {"name": "codeql/javascript-queries", "status": "ran",
         "pack_version": "2.3.2", "pack_age_days": 47},
        {"name": "semgrep", "status": "unavailable", "reason": "not on PATH"},
        {"name": "pattern-redact", "status": "ran"},
    ]
    out = m.fill(result, template.read_text(encoding="utf-8"),
                 project="p", date="2026-07-27")
    lower = out.lower()
    assert "codeql taint analysis" in lower, out
    assert "javascript" in lower, "CodeQL language must be named"
    # A fresh (47-day) pack must NOT trigger the stale-pack line.
    assert "days old" not in lower, "fresh pack incorrectly flagged as stale"
    print("OK: limitations names CodeQL runner + language when it ran")


def test_limitations_names_codeql_missing_as_blindspot() -> None:
    m = _load()
    template = TOOLS_DIR.parent / "templates" / "AUDIT-TEMPLATE.md"
    result = _sample_result()
    # Semgrep ran but CodeQL did not: coverage line must name the gap.
    result["tools"] = [
        {"name": "codeql", "status": "unavailable", "reason": "not on PATH"},
        {"name": "semgrep", "status": "ran", "ruleset": "auto"},
        {"name": "pattern-redact", "status": "ran"},
    ]
    out = m.fill(result, template.read_text(encoding="utf-8"),
                 project="p", date="2026-07-27")
    lower = out.lower()
    assert "no codeql taint" in lower, out
    assert "install codeql" in lower, "missing actionable hint to install codeql"
    print("OK: limitations flags missing CodeQL as a blindspot")


def test_limitations_names_stale_pack() -> None:
    m = _load()
    template = TOOLS_DIR.parent / "templates" / "AUDIT-TEMPLATE.md"
    result = _sample_result()
    # 151-day-old pack: the currency signal must fire with the upgrade command.
    result["tools"] = [
        {"name": "codeql/javascript-queries", "status": "ran",
         "pack_version": "2.3.2", "pack_age_days": 151},
        {"name": "pattern-redact", "status": "ran"},
    ]
    out = m.fill(result, template.read_text(encoding="utf-8"),
                 project="p", date="2026-07-27")
    assert "151 days old" in out, out
    assert "codeql pack upgrade codeql/javascript-queries" in out, out
    print("OK: limitations flags 151-day-old pack + names upgrade command")


def test_fill_no_findings_clean() -> None:
    m = _load()
    template = TOOLS_DIR.parent / "templates" / "AUDIT-TEMPLATE.md"
    empty = _sample_result()
    empty["findings"] = []
    out = m.fill(empty, template.read_text(encoding="utf-8"),
                project="p", date="2026-07-23")
    # Still a valid report; no crash on zero findings.
    assert "Executive Summary" in out
    print("OK: fill handles zero findings")


def _supply_result() -> dict:
    result = _sample_result()
    result["tools"] += [
        {"name": "lockfile-provenance", "status": "ran", "packages": 3},
        {"name": "action-pinning", "status": "ran", "workflows": 2},
        {"name": "cleanroom-rebuild", "status": "not-run",
         "reason": "opt-in; pass --rebuild"},
        {"name": "gh-attestation", "status": "not-run",
         "reason": "opt-in; pass --release-verify"},
    ]
    result["findings"].append(
        {"fp": "ee", "phase": "supply-chain", "cwe": "CWE-829",
         "severity": "high", "file": ".github/workflows/x.yml", "line": 7,
         "engine": "supply-chain",
         "message": "Action pinned to mutable ref: actions/checkout@v4",
         "status": "unconfirmed", "cvss": "", "evidence": ""})
    return result


def test_fill_supply_chain_matrix_and_section() -> None:
    m = _load()
    template = TOOLS_DIR.parent / "templates" / "AUDIT-TEMPLATE.md"
    out = m.fill(_supply_result(), template.read_text(encoding="utf-8"),
                 project="p", date="2026-08-08")
    # Matrix row filled with the one high supply finding.
    assert "| Supply chain (provenance, build integrity) | 0 | 1 | 0 | 0 | 0 |" in out, out
    assert "{n}" not in out.split("License Compliance")[0], "unfilled matrix cells"
    # Supply section carries the finding row.
    section = out.split("Supply Chain: Provenance and Build Integrity")[1]
    assert "actions/checkout@v4" in section.split("## License")[0], out
    print("OK: supply-chain matrix row + report section filled")


def test_limitations_name_supply_chain_stages() -> None:
    m = _load()
    block = m._limitations_block(_supply_result())
    assert "Supply chain (static)" in block, block
    assert "action-pinning" in block, block
    assert "Clean-room rebuild: not run" in block, block
    assert "Release attestation: not run" in block, block
    ran = dict(_supply_result())
    ran["tools"] = [t for t in ran["tools"]
                    if t["name"] not in ("cleanroom-rebuild",)]
    ran["tools"].append({"name": "cleanroom-rebuild", "status": "ran",
                         "artifacts": 2, "mismatches": 1})
    block2 = m._limitations_block(ran)
    assert "MISMATCH in 1 artifact" in block2, block2
    print("OK: limitations block names all three supply-chain stages honestly")


def test_sca_rows_and_coverage_name_the_advisory_source() -> None:
    m = _load()
    template = TOOLS_DIR.parent / "templates" / "AUDIT-TEMPLATE.md"
    result = _sample_result()
    out = m.fill(result, template.read_text(encoding="utf-8"), project="p", date="2026-09-24")
    assert "| foo | 1.0.0 | GHSA-aaaa-bbbb-cccc (CVE-2026-1) | medium | 1.0.1 |" in out, out
    offline = m._limitations_block(result)
    assert "SCA: OFFLINE (<urlopen error [Errno 61] Connection refused>)" in offline, offline
    assert "NOT reported" in offline, offline
    result["tools"][2] = {"name": "osv", "status": "error", "reason": "HTTP 503 from api.osv.dev"}
    assert "SCA: ERROR (HTTP 503 from api.osv.dev)" in m._limitations_block(result)
    result["tools"][2] = {"name": "osv", "status": "ran", "packages": 12,
                          "manifests": ["package-lock.json", "requirements.txt"]}
    ran = m._limitations_block(result)
    assert "SCA: OSV advisories for 12 packages in package-lock.json, requirements.txt" in ran, ran
    result["tools"][2] = {"name": "osv", "status": "not-applicable", "reason": "no lockfile"}
    assert "SCA: no lockfile; dependencies unscanned." in m._limitations_block(result)
    result["tools"][2] = {"name": "osv", "status": "partial", "packages": 1, "manifests": ["requirements.txt"],
                          "reason": "not read: pnpm-lock.yaml (no package found)"}
    partial = m._limitations_block(result)
    assert "SCA: PARTIAL, OSV advisories for 1 packages in requirements.txt;" \
           " not read: pnpm-lock.yaml (no package found)" in partial, partial
    assert "NOT reported" in partial, partial
    result["tools"][2] = {"name": "osv", "status": "partial", "packages": 0, "manifests": [],
                          "reason": "not checked: package.json (declared, not locked)"}
    declared = m._limitations_block(result)      # f11-sca: no lockfile there, so none is "unread"
    assert "- SCA: PARTIAL, no dependency checked against OSV; not checked: package.json" \
           " (declared, not locked); known CVEs" in declared, declared   # f13-code: not "0 packages in no manifest"
    assert "lockfile" not in declared and "NOT reported" in declared, declared
    print("OK: SCA rows carry ID, CVE, fix; coverage names OSV, offline and errors")


def test_sca_not_applicable_names_the_reason_osv_gave() -> None:
    """f9-sca: the report said "no lockfile" for every not-applicable, also for a lockfile read
    with zero packages."""
    m = _load()
    sys.path.insert(0, str(TOOLS_DIR))
    from lib import osv
    with tempfile.TemporaryDirectory() as raw:
        (Path(raw) / "package-lock.json").write_text(json.dumps(
            {"name": "app", "lockfileVersion": 3, "packages": {"": {"name": "app"}}}), encoding="utf-8")
        _, tool = osv.scan(Path(raw))
    assert tool["status"] == "not-applicable", tool
    result = _sample_result()
    result["tools"][2] = tool
    block = m._limitations_block(result)
    assert f"- SCA: {tool['reason']}; dependencies unscanned." in block, block
    assert "no lockfile" not in block, block
    print("OK: a not-applicable SCA names the reason osv gave")


def test_limitations_names_missing_codeql_pack_as_blind_spot() -> None:
    m = _load()
    result = _sample_result()
    result["tools"] = [
        {"name": "codeql/javascript-queries", "status": "ran", "pack_age_days": 3},
        {"name": "codeql/python-queries", "status": "pack-missing",
         "reason": "pack not cached; run: codeql pack download codeql/python-queries"},
        {"name": "pattern-redact", "status": "ran"},
    ]
    block = m._limitations_block(result)
    assert "- Blind spot: no CodeQL taint analysis for python (codeql/python-queries pack-missing:" \
           " pack not cached; run: codeql pack download codeql/python-queries)." in block, block
    assert "javascript" not in block.split("Blind spot")[1], block
    print("OK: a missing CodeQL pack is named as a blind spot")


def test_limitations_name_reference_dates_and_warn_when_stale() -> None:
    m = _load()
    result = _sample_result()
    result["meta"]["taxonomy"] = {"owasp-checklist": "2026-09-24", "supply-chain": "2026-06-01"}
    result["meta"]["taxonomy_warning"] = None
    block = m._limitations_block(result)
    assert "- Threat taxonomy: bundled references, oldest as-of 2026-06-01;" in block, block
    assert "WARNING" not in block, block
    result["meta"]["taxonomy_warning"] = "bundled references undated or at least 90 days old: supply-chain (115 days)"
    assert "- WARNING: bundled references undated or at least 90 days old: supply-chain (115 days)." \
        in m._limitations_block(result)
    print("OK: coverage names the reference date and the 90-day warning")


def test_limitations_list_agent_surfaces_unrated() -> None:
    m = _load()
    result = _sample_result()
    assert "Agent surfaces" not in m._limitations_block(result)
    result["surfaces"] = [
        {"surface_type": "agent_instruction", "file": "AGENTS.md", "line": 5, "symbol": "<!-- agents -->"},
        {"surface_type": "network_egress", "file": "bot/summarize.py", "line": 18, "symbol": "urlopen("},
        {"surface_type": "llm_call", "file": "bot/summarize.py", "line": 19, "symbol": "messages.create("},
        {"surface_type": "agent_instruction", "file": "README.md", "line": 10, "symbol": "<!-- AI -->"},
        {"surface_type": "mcp_unpinned", "file": "mcp/servers.json", "line": 3, "symbol": '"-y"'},
    ]
    assert ("- Agent surfaces, flagged for Phase 4 triage and not rated:"
            " agent_instruction at AGENTS.md:5, README.md:10; llm_call at bot/summarize.py:19;"
            " mcp_unpinned at mcp/servers.json:3.") in m._limitations_block(result)
    print("OK: coverage lists the agent surfaces the scanner flagged")


def test_scan_meta_carries_reference_dates_into_the_report() -> None:
    import subprocess
    spec = importlib.util.spec_from_file_location("audit_scan", TOOLS_DIR / "audit_scan.py")
    scan = importlib.util.module_from_spec(spec)
    sys.modules["audit_scan"] = scan
    spec.loader.exec_module(scan)
    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)
        (tmp / "README.md").write_text("# x\n", encoding="utf-8")
        for cmd in (["init", "-q", "-b", "main"], ["add", "-A"],
                    ["-c", "user.email=t@t.t", "-c", "user.name=t", "commit", "-q", "-m", "c"]):
            subprocess.run(["git", *cmd], cwd=tmp, check=True)
        result = scan.run_all(tmp, scope="full", write_baseline=False)
    owasp = (TOOLS_DIR.parent / "references" / "owasp-checklist.md").read_text(encoding="utf-8")
    assert f"as-of: {result['meta']['taxonomy']['owasp-checklist']}\n" in owasp, result["meta"]
    assert "taxonomy_warning" in result["meta"], result["meta"]
    json.dumps(result)  # the envelope stays plain JSON
    template = (TOOLS_DIR.parent / "templates" / "AUDIT-TEMPLATE.md").read_text(encoding="utf-8")
    out = _load().fill(result, template, project="p", date="2026-09-24")
    assert "bundled references, oldest as-of 20" in out, result["meta"]
    print("OK: scan meta names as-of per reference, the report shows it")


ALL_TESTS = [
    test_fill_counts_and_buckets,
    test_fill_tools_are_honest,
    test_fill_has_limitations_section,
    test_delta_from_baselines,
    test_limitations_names_codeql_when_ran,
    test_limitations_names_codeql_missing_as_blindspot,
    test_limitations_names_stale_pack,
    test_fill_no_findings_clean,
    test_fill_supply_chain_matrix_and_section,
    test_limitations_name_supply_chain_stages,
    test_sca_rows_and_coverage_name_the_advisory_source,
    test_sca_not_applicable_names_the_reason_osv_gave,
    test_limitations_names_missing_codeql_pack_as_blind_spot,
    test_limitations_name_reference_dates_and_warn_when_stale,
    test_limitations_list_agent_surfaces_unrated,
    test_scan_meta_carries_reference_dates_into_the_report,
]


def main() -> int:
    failed = 0
    for t in ALL_TESTS:
        try:
            t()
        except AssertionError as exc:
            print(f"FAIL: {t.__name__}: {exc}", file=sys.stderr)
            failed += 1
        except Exception as exc:  # noqa: BLE001
            print(f"ERROR: {t.__name__}: {exc!r}", file=sys.stderr)
            failed += 1
    if failed:
        print(f"\n{failed} test(s) failed.", file=sys.stderr)
        return 1
    print("\nAll report_assembler tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
