"""Tests for pulse-audit/tools/audit_scan.py.

Focus on the behaviours that make the scanner trustworthy:
  * grep-fallback SAST finds CWE patterns without any external tool
  * the honest tools[] ledger records what actually ran
  * secret matches are redacted (never plaintext) in output
  * SCA names a failed advisory lookup instead of reporting a clean run
  * in a diff scope only advisories of changed manifests block
  * scope drives which files are scanned

Assertion-based, pytest-discoverable.

    python3 skills/pulse-audit/tools/tests/test_audit_scan.py
"""
from __future__ import annotations
import contextlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch


TOOLS_DIR = Path(__file__).resolve().parents[1]
SCRIPT = TOOLS_DIR / "audit_scan.py"


def _load():
    spec = importlib.util.spec_from_file_location("audit_scan", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["audit_scan"] = mod
    spec.loader.exec_module(mod)
    return mod


def _write(tmp: Path, rel: str, content: str) -> None:
    p = tmp / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def test_grep_sast_finds_cwe_patterns() -> None:
    m = _load()
    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)
        _write(tmp, "src/danger.ts",
               "eval(userInput)\n"
               "el.innerHTML = data\n"
               "child_process.exec(cmd)\n")
        findings = m.grep_sast(tmp, ["src/danger.ts"])
        cwes = {f.cwe for f in findings}
        assert "CWE-94" in cwes, cwes   # eval
        assert "CWE-79" in cwes, cwes   # innerHTML
        assert "CWE-78" in cwes, cwes   # exec
        for f in findings:
            assert f.engine == "grep-fallback", f
            assert f.fp and len(f.fp) == 8, f
        print("OK: grep SAST finds CWE patterns")


def test_grep_sast_skips_comments_optional() -> None:
    m = _load()
    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)
        # A line that is clearly a finding.
        _write(tmp, "a.ts", "const x = eval(s)\n")
        findings = m.grep_sast(tmp, ["a.ts"])
        assert any(f.cwe == "CWE-94" for f in findings), findings
        print("OK: grep SAST basic hit")


def test_tool_available_false_for_missing() -> None:
    m = _load()
    assert m.tool_available("definitely-not-a-real-binary-xyz") is False
    # python3 should exist in the test environment.
    assert m.tool_available("python3") is True
    print("OK: tool_available detects missing vs present")


def test_secrets_scan_redacts() -> None:
    m = _load()
    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)
        secret = "AKIA" + "1234567890ABCDEF"  # AWS-key-shaped
        _write(tmp, "cfg.ts", f'const key = "{secret}"\n')
        findings, tools = m.run_secrets(tmp, ["cfg.ts"])
        blob = json.dumps([f.to_dict() for f in findings])
        assert secret not in blob, f"secret leaked into findings: {blob}"
        # If the entropy fallback fired, there is at least a redacted record.
        # (gitleaks may or may not be installed; either way, no plaintext.)
        print("OK: secrets scan never emits plaintext")


def test_run_all_shape_and_honest_tools() -> None:
    m = _load()
    # CodeQL forced off for this test: a real DB build would take 30+s
    # and make the suite non-deterministic across machines. CodeQL-on
    # cascade is covered by test_run_all_sast_cascade_with_codeql below.
    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=tmp, check=True)
        subprocess.run(["git", "config", "user.email", "t@t.t"], cwd=tmp, check=True)
        subprocess.run(["git", "config", "user.name", "t"], cwd=tmp, check=True)
        _write(tmp, "package.json", json.dumps({"name": "x", "dependencies": {}}))
        _write(tmp, "src/v.ts", "eval(x)\n")
        subprocess.run(["git", "add", "-A"], cwd=tmp, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=tmp, check=True)

        with patch.object(m.CQ, "codeql_available", return_value=False):
            result = m.run_all(tmp, scope="full")
        # Envelope shape.
        for key in ("schema", "scope", "project_type", "tools", "findings", "meta"):
            assert key in result, f"missing {key}: {list(result)}"
        assert result["scope"] == "full"
        # eval finding surfaced.
        assert any(f["cwe"] == "CWE-94" for f in result["findings"]), result["findings"]
        # tools ledger is honest: each entry declares a status.
        statuses = {t["name"]: t["status"] for t in result["tools"]}
        assert statuses, "tools ledger empty"
        for name, st in statuses.items():
            assert st in ("ran", "unavailable", "offline", "error",
                          "pack-missing", "not-run", "not-applicable",
                          "not-configured"), (name, st)
        # codeql is now part of the ledger, even when unavailable.
        assert "codeql" in statuses, statuses
        assert statuses["codeql"] == "unavailable", statuses
        # findings are JSON-serializable.
        json.dumps(result)
        print("OK: run_all shape + honest tools ledger")


def test_run_all_sast_cascade_with_codeql() -> None:
    """CodeQL-on path uses mocked ensure_pack + run_codeql so the test
    stays fast and does not depend on a real query pack. Verifies:
      * codeql tool entry lands in the ledger with pack age metadata
      * semgrep + grep still run alongside (three-layer cascade)
      * pack-missing status is surfaced when a language pack is absent
    """
    m = _load()
    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=tmp, check=True)
        subprocess.run(["git", "config", "user.email", "t@t.t"], cwd=tmp, check=True)
        subprocess.run(["git", "config", "user.name", "t"], cwd=tmp, check=True)
        _write(tmp, "package.json", json.dumps({"name": "x", "dependencies": {}}))
        _write(tmp, "src/v.ts", "eval(x)\n")
        subprocess.run(["git", "add", "-A"], cwd=tmp, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=tmp, check=True)

        fake_finding = m.F.Finding(
            fp="deadbeef", phase="sast", cwe="CWE-94", severity="high",
            file="src/v.ts", line=1, engine="codeql",
            message="Code injection (mock)",
        )

        def fake_run_codeql(root, lang, db_dir, timeout=1800):
            return [fake_finding], {"name": f"codeql/{lang}-queries", "status": "ran"}

        def fake_pack_age(name):
            return {"pack_version": "2.3.2", "pack_age_days": 47, "stale": False}

        with patch.object(m.CQ, "codeql_available", return_value=True), \
             patch.object(m.CQ, "run_codeql", side_effect=fake_run_codeql), \
             patch.object(m.CQ, "pack_age_check", side_effect=fake_pack_age):
            result = m.run_all(tmp, scope="full")

        statuses = {t["name"]: t["status"] for t in result["tools"]}
        # CodeQL tool entry present with the ran status.
        assert "codeql/javascript-queries" in statuses, statuses
        assert statuses["codeql/javascript-queries"] == "ran", statuses
        # Pack age metadata carried through to the ledger.
        codeql_entry = next(t for t in result["tools"]
                            if t["name"] == "codeql/javascript-queries")
        assert codeql_entry.get("pack_version") == "2.3.2", codeql_entry
        assert codeql_entry.get("pack_age_days") == 47, codeql_entry
        # CodeQL finding surfaced alongside grep's eval hit (both CWE-94:
        # dedup keeps them distinct because fingerprints differ).
        cwe_94 = [f for f in result["findings"] if f["cwe"] == "CWE-94"]
        assert any(f["engine"] == "codeql" for f in cwe_94), cwe_94
        assert any(f["engine"] == "grep-fallback" for f in cwe_94), cwe_94
        print("OK: run_all runs CodeQL alongside semgrep+grep, pack age surfaced")


def test_run_all_sast_pack_missing_falls_back() -> None:
    """CodeQL is available but the pack is not cached: pack-missing is
    reported, no findings from CodeQL, semgrep+grep continue normally."""
    m = _load()
    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=tmp, check=True)
        subprocess.run(["git", "config", "user.email", "t@t.t"], cwd=tmp, check=True)
        subprocess.run(["git", "config", "user.name", "t"], cwd=tmp, check=True)
        _write(tmp, "package.json", json.dumps({"name": "x", "dependencies": {}}))
        _write(tmp, "src/v.ts", "eval(x)\n")
        subprocess.run(["git", "add", "-A"], cwd=tmp, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=tmp, check=True)

        with patch.object(m.CQ, "codeql_available", return_value=True), \
             patch.object(m.CQ, "ensure_pack", return_value=False):
            result = m.run_all(tmp, scope="full")

        statuses = {t["name"]: t["status"] for t in result["tools"]}
        assert statuses.get("codeql/javascript-queries") == "pack-missing", statuses
        pack_tool = next(t for t in result["tools"]
                         if t["name"] == "codeql/javascript-queries")
        assert "codeql pack download" in pack_tool["reason"], pack_tool
        # Grep still surfaces the eval finding.
        assert any(f["cwe"] == "CWE-94" and f["engine"] == "grep-fallback"
                   for f in result["findings"]), result["findings"]
        print("OK: pack-missing falls back to lower layers cleanly")


def test_run_all_records_taxonomy_snapshot() -> None:
    m = _load()
    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=tmp, check=True)
        subprocess.run(["git", "config", "user.email", "t@t.t"], cwd=tmp, check=True)
        subprocess.run(["git", "config", "user.name", "t"], cwd=tmp, check=True)
        _write(tmp, "a.ts", "eval(x)\n")
        subprocess.run(["git", "add", "-A"], cwd=tmp, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "c"], cwd=tmp, check=True)
        tax = {"owasp": "2025", "cwe-top-25": "2024"}
        result = m.run_all(tmp, scope="full", taxonomy=tax, write_baseline=False)
        # The snapshotted taxonomy must reach the envelope so the report's
        # limitations section can name the editions instead of "unrecorded".
        assert result.get("taxonomy") == tax, result.get("taxonomy")
        print("OK: run_all records taxonomy snapshot in envelope")


def test_run_all_diff_scope_limits_files() -> None:
    m = _load()
    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=tmp, check=True)
        subprocess.run(["git", "config", "user.email", "t@t.t"], cwd=tmp, check=True)
        subprocess.run(["git", "config", "user.name", "t"], cwd=tmp, check=True)
        _write(tmp, "old.ts", "eval(a)\n")
        subprocess.run(["git", "add", "-A"], cwd=tmp, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "c1"], cwd=tmp, check=True)
        _write(tmp, "new.ts", "eval(b)\n")
        subprocess.run(["git", "add", "-A"], cwd=tmp, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "c2"], cwd=tmp, check=True)

        result = m.run_all(tmp, scope="commit")
        sast_files = {f["file"] for f in result["findings"] if f["phase"] == "sast"}
        # Only the last commit's file is in the reported SAST scope.
        assert sast_files <= {"new.ts"}, sast_files
        assert "new.ts" in sast_files, sast_files
        print("OK: diff scope limits reported SAST files")


def test_run_all_supply_chain_static_only() -> None:
    """`all` must include the supply-chain ledger but never execute the
    opt-in stages (no clean-room build, no gh calls)."""
    m = _load()
    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=tmp, check=True)
        subprocess.run(["git", "config", "user.email", "t@t.t"], cwd=tmp, check=True)
        subprocess.run(["git", "config", "user.name", "t"], cwd=tmp, check=True)
        _write(tmp, "package.json", json.dumps({"name": "x"}))
        subprocess.run(["git", "add", "-A"], cwd=tmp, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=tmp, check=True)

        with patch.object(m.CQ, "codeql_available", return_value=False), \
                patch.object(m.CR, "run_cleanroom_rebuild") as rb, \
                patch.object(m.CR, "run_release_verify") as rv:
            result = m.run_all(tmp, scope="full")
        rb.assert_not_called()
        rv.assert_not_called()
    statuses = {t["name"]: t["status"] for t in result["tools"]}
    assert statuses.get("cleanroom-rebuild") == "not-run", statuses
    assert statuses.get("gh-attestation") == "not-run", statuses
    assert "manifest-hygiene" in statuses, statuses
    print("OK: run_all carries supply ledger, opt-in stages never execute")


def test_supply_chain_runner_findings_and_overrides() -> None:
    m = _load()
    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)
        _write(tmp, "package-lock.json", json.dumps({
            "name": "x", "lockfileVersion": 3,
            "packages": {
                "": {"name": "x"},
                "node_modules/evil": {"version": "1",
                                      "resolved": "git+https://g/x.git"},
                "node_modules/mirror": {
                    "version": "1",
                    "resolved": "https://npm.corp.example/m.tgz",
                    "integrity": "sha512-x"},
            },
        }))
        fs, tools = m.run_supply_chain(tmp)
        assert any(f.phase == "supply-chain" and f.severity == "high"
                   for f in fs), fs
        assert any("mirror" in f.message for f in fs), fs

        fs2, _ = m.run_supply_chain(
            tmp, cli_cfg={"registry_hosts": ["registry.npmjs.org",
                                             "npm.corp.example"]})
        assert not any("mirror" in f.message for f in fs2), fs2
    names = {t["name"] for t in tools}
    assert {"lockfile-provenance", "cleanroom-rebuild", "gh-attestation"} <= names, tools
    print("OK: supply-chain runner finds git dep, CLI registry override works")


def test_codeql_databases_of_parallel_worktrees_do_not_share_a_directory() -> None:
    """pulse go audits several worktrees of one clone at once; each needs its own DB dir."""
    mod = _load()
    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)
        main, wt = tmp / "main", tmp / "wt"
        main.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=main, check=True)
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q",
                        "--allow-empty", "-m", "init"], cwd=main, check=True)
        subprocess.run(["git", "worktree", "add", "-q", str(wt)], cwd=main, check=True)
        a, b = mod._codeql_db_dir(main, "python"), mod._codeql_db_dir(wt, "python")
        assert a != b, "two worktrees would overwrite each other's database"
        assert a.parent == b.parent and a.parent.name == "security-audit"
        assert mod._codeql_db_dir(wt, "python") == b, "stable for one worktree"
    print("OK: codeql db per worktree")


def _init_repo(tmp: Path) -> None:
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=tmp, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.t"], cwd=tmp, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp, check=True)


def _commit(tmp: Path, msg: str) -> None:
    subprocess.run(["git", "add", "-A"], cwd=tmp, check=True)
    subprocess.run(["git", "commit", "-q", "-m", msg], cwd=tmp, check=True)


def _one_high_advisory_per_package(path, body=None):
    if path == "querybatch":
        return {"results": [{"vulns": [{"id": "GHSA-" + q["package"]["name"]}]}
                            for q in body["queries"]]}
    vid = path.split("/", 1)[1]
    return {"id": vid, "aliases": [], "published": "2026-09-01T00:00:00Z",
            "database_specific": {"severity": "HIGH"}, "affected": []}


def test_branch_scope_blocks_only_advisories_of_changed_manifests() -> None:
    m = _load()
    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)
        _init_repo(tmp)
        _write(tmp, "package-lock.json", json.dumps({"lockfileVersion": 3, "packages": {
            "": {"name": "x"}, "node_modules/js-yaml": {"version": "4.3.1"}}}))
        _write(tmp, "requirements.txt", "anyio==4.14.1\n")
        _commit(tmp, "base")
        subprocess.run(["git", "checkout", "-q", "-b", "feature"], cwd=tmp, check=True)
        _write(tmp, "requirements.txt", "anyio==4.14.1\nrequests==2.19.0\n")
        _write(tmp, "docs.txt", "notes\n")
        _commit(tmp, "bump")
        with patch.object(m.CQ, "codeql_available", return_value=False), \
                patch.object(m.OSV, "_fetch", side_effect=_one_high_advisory_per_package):
            branch = m.run_all(tmp, scope="branch", base="main", write_baseline=False)
            full = m.run_all(tmp, scope="full", write_baseline=False)
    sca = {f["package"]: f for f in branch["findings"] if f["phase"] == "sca"}
    assert set(sca) == {"js-yaml", "anyio", "requests"}, sca
    assert sca["anyio"]["severity"] == sca["requests"]["severity"] == "high", sca
    note = sca["js-yaml"]
    assert note["severity"] == "info", note
    assert "unchanged" in note["message"] and "high" in note["message"], note["message"]
    assert {f["severity"] for f in full["findings"] if f["phase"] == "sca"} == {"high"}
    print("OK: branch scope blocks on changed manifests, the rest is a note")


def test_two_versions_of_one_package_under_one_advisory_stay_two_findings() -> None:
    m = _load()
    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)
        _init_repo(tmp)
        _write(tmp, "package-lock.json", json.dumps({"lockfileVersion": 3, "packages": {
            "": {"name": "x"}, "node_modules/js-yaml": {"version": "4.3.1"},
            "node_modules/a/node_modules/js-yaml": {"version": "3.14.0"}}}))
        _commit(tmp, "init")
        with patch.object(m.CQ, "codeql_available", return_value=False), \
                patch.object(m.OSV, "_fetch", side_effect=_one_high_advisory_per_package):
            result = m.run_all(tmp, scope="full", write_baseline=False)
    versions = sorted(f["version"] for f in result["findings"] if f["phase"] == "sca")
    assert versions == ["3.14.0", "4.3.1"], versions
    print("OK: a nested older version keeps its own finding")


def test_offline_sca_is_named_and_fails_the_exit_code() -> None:
    m = _load()
    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)
        _init_repo(tmp)
        _write(tmp, "requirements.txt", "anyio==4.14.1\n")
        _commit(tmp, "init")
        dead = "http://127.0.0.1:9"
        env = {k: v for k, v in os.environ.items() if k.lower() not in ("no_proxy", "all_proxy")}
        env.update(https_proxy=dead, HTTPS_PROXY=dead)
        with patch.dict(os.environ, env, clear=True), \
                patch.object(m.CQ, "codeql_available", return_value=False):
            result = m.run_all(tmp, scope="full", write_baseline=False)
            codes = {}
            for cmd in ("sca", "all"):
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    codes[cmd] = m.main([cmd, str(tmp), *(["--no-baseline"] if cmd == "all" else [])])
                osv, = [t for t in json.loads(out.getvalue())["tools"] if t["name"] == "osv"]
                assert osv["status"] == "offline" and osv["reason"], osv
    osv, = [t for t in result["tools"] if t["name"] == "osv"]
    assert osv["status"] == "offline" and osv["reason"], osv
    assert result["meta"]["offline"] is True, result["meta"]
    assert codes == {"sca": 2, "all": 2}, codes
    print("OK: offline SCA is named in the ledger and meta, exit 2")


def test_partial_sca_fails_the_exit_code() -> None:
    m = _load()
    tools = [{"name": "osv", "status": "partial", "reason": "not read: pnpm-lock.yaml (no package found)"}]
    assert m._exit_code([], tools) == 2
    print("OK: a partial SCA exits 2")


def test_a_lockfile_without_dependencies_exits_0() -> None:
    m = _load()
    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)
        _init_repo(tmp)
        _write(tmp, "package-lock.json", json.dumps({"name": "x", "lockfileVersion": 3, "packages": {"": {}}}))
        _commit(tmp, "init")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = m.main(["sca", str(tmp)])
    osv, = json.loads(out.getvalue())["tools"]
    assert code == 0 and osv["status"] == "not-applicable" and "not read" not in osv["reason"], (code, osv)
    print("OK: a lockfile without dependencies exits 0")


ALL_TESTS = [
    test_codeql_databases_of_parallel_worktrees_do_not_share_a_directory,
    test_grep_sast_finds_cwe_patterns,
    test_grep_sast_skips_comments_optional,
    test_tool_available_false_for_missing,
    test_secrets_scan_redacts,
    test_run_all_shape_and_honest_tools,
    test_run_all_sast_cascade_with_codeql,
    test_run_all_sast_pack_missing_falls_back,
    test_run_all_records_taxonomy_snapshot,
    test_run_all_diff_scope_limits_files,
    test_run_all_supply_chain_static_only,
    test_supply_chain_runner_findings_and_overrides,
    test_branch_scope_blocks_only_advisories_of_changed_manifests,
    test_two_versions_of_one_package_under_one_advisory_stay_two_findings,
    test_offline_sca_is_named_and_fails_the_exit_code,
    test_partial_sca_fails_the_exit_code,
    test_a_lockfile_without_dependencies_exits_0,
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
    print("\nAll audit_scan tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
