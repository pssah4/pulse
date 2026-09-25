"""Tests for pulse-audit/tools/lib/osv.py (SCA over the OSV API).

Assertion-based, runnable without pytest but pytest-discoverable. The API
answers come from recordings (trimmed, taken from api.osv.dev on
2026-09-24); the offline test points urllib at a dead proxy.

    python3 skills/pulse-audit/tools/tests/test_osv.py
"""
from __future__ import annotations
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import urllib.error
from pathlib import Path
from unittest.mock import patch

LIB_DIR = Path(__file__).resolve().parents[1] / "lib"

# /v1/querybatch for anyio 4.14.1, requests 2.19.0 (PyPI, cut to one CVE) and js-yaml 4.3.1 (npm)
QUERYBATCH = {"results": [
    {"vulns": [{"id": "GHSA-82r6-8w77-94w6", "modified": "2026-09-18T17:30:07Z"}]},
    {"vulns": [{"id": "GHSA-x84v-xcm2-53pg", "modified": "2026-03-25T17:16:52Z"},
               {"id": "PYSEC-2018-28", "modified": "2026-03-25T17:16:52Z"}]},
    {"vulns": [{"id": "GHSA-2883-xcg3-v3hh", "modified": "2026-09-08T21:30:05Z"}]},
]}
# /v1/vulns/{id}, trimmed to the fields the scanner reads
VULNS = {
    "GHSA-2883-xcg3-v3hh": {
        "id": "GHSA-2883-xcg3-v3hh", "aliases": ["CVE-2026-84375"],
        "published": "2026-09-08T21:24:51Z",
        "summary": "js-yaml: maxTotalMergeKeys does not limit CPU use for empty merge sources",
        "database_specific": {"severity": "HIGH", "cwe_ids": ["CWE-400", "CWE-407"]},
        "affected": [
            {"package": {"name": "js-yaml", "ecosystem": "npm"},
             "ranges": [{"type": "SEMVER", "events": [{"introduced": "4.0.0"}, {"fixed": "4.3.2"}]}]},
            {"package": {"name": "js-yaml", "ecosystem": "npm"},
             "ranges": [{"type": "SEMVER", "events": [{"introduced": "3.0.0"}, {"fixed": "3.15.2"}]}]},
        ]},
    "GHSA-82r6-8w77-94w6": {
        "id": "GHSA-82r6-8w77-94w6", "aliases": ["CVE-2026-63374"],
        "published": "2026-09-18T17:17:18Z",
        "summary": "AnyIO: TLSStream IDNA 2003 host name encoding enables potential TLS certificate spoofing",
        "database_specific": {"severity": "CRITICAL", "cwe_ids": ["CWE-295", "CWE-297"]},
        "affected": [
            {"package": {"name": "anyio", "ecosystem": "PyPI"},
             "ranges": [{"type": "ECOSYSTEM", "events": [{"introduced": "0"}, {"fixed": "4.14.2"}]}]},
        ]},
    "GHSA-x84v-xcm2-53pg": {
        "id": "GHSA-x84v-xcm2-53pg", "aliases": ["CVE-2018-18074", "PYSEC-2018-28"],
        "published": "2018-10-29T19:06:46Z",
        "summary": "Insufficiently Protected Credentials in Requests",
        "database_specific": {"severity": "HIGH", "cwe_ids": ["CWE-522"]},
        "affected": [
            {"package": {"name": "requests", "ecosystem": "PyPI"},
             "ranges": [{"type": "ECOSYSTEM", "events": [{"introduced": "0"}, {"fixed": "2.20.0"}]}]},
        ]},
    "PYSEC-2018-28": {
        "id": "PYSEC-2018-28", "aliases": ["CVE-2018-18074", "GHSA-x84v-xcm2-53pg"],
        "published": "2018-10-09T17:29:00Z",
        "affected": [
            {"package": {"name": "requests", "ecosystem": "PyPI"},
             "ranges": [{"type": "GIT", "events": [{"introduced": "0"},
                                                   {"fixed": "c45d7c49ea75133e52ab22a8e9e13173938e36ff"}]},
                        {"type": "ECOSYSTEM", "events": [{"introduced": "0"}, {"fixed": "2.20.0"}]}]},
        ]},
}


def _load():
    if str(LIB_DIR) not in sys.path:
        sys.path.insert(0, str(LIB_DIR))
    spec = importlib.util.spec_from_file_location("sa_osv", LIB_DIR / "osv.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["sa_osv"] = mod
    spec.loader.exec_module(mod)
    return mod


def _write(root: Path, rel: str, content: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def _recorded(calls: list):
    def fetch(path, body=None):
        calls.append((path, body))
        if path == "querybatch":
            return QUERYBATCH
        return VULNS[path.split("/", 1)[1]]
    return fetch


def _answer(path, body=None):
    """The recordings for any list of queries: js-yaml 4.3.1 and anyio 4.14.1 carry one advisory."""
    if path != "querybatch":
        return VULNS[path.split("/", 1)[1]]
    hits = {("npm", "js-yaml", "4.3.1"): "GHSA-2883-xcg3-v3hh", ("PyPI", "anyio", "4.14.1"): "GHSA-82r6-8w77-94w6"}
    keys = [(q["package"]["ecosystem"], q["package"]["name"], q["version"]) for q in body["queries"]]
    return {"results": [{"vulns": [{"id": hits[k]}]} if k in hits else {} for k in keys]}


def _probe_repo(root: Path) -> None:
    _write(root, "package-lock.json", json.dumps({"lockfileVersion": 3, "packages": {
        "": {"name": "bot"}, "node_modules/js-yaml": {"version": "4.3.1"}}}))
    _write(root, "requirements.txt", "anyio==4.14.1\nrequests==2.19.0\n")


PNPM_V9 = """lockfileVersion: '9.0'

settings:
  autoInstallPeers: true

overrides:
  foo@1: 1.0.1

importers:

  .:
    dependencies:
      '@babel/core':
        specifier: 7.22.0
        version: 7.22.0
      js-yaml:
        specifier: 4.3.1
        version: 4.3.1

packages:

  '@babel/core@7.22.0':
    resolution: {integrity: sha512-a}

  js-yaml@4.3.1:
    resolution: {integrity: sha512-b}
    hasBin: true

  'tool@https://codeload.github.com/o/tool/tar.gz/abc':
    resolution: {tarball: https://codeload.github.com/o/tool/tar.gz/abc}
    version: 1.0.0

snapshots:

  '@babel/core@7.22.0': {}

  js-yaml@4.3.1: {}

  react-dom@18.2.0(react@18.2.0): {}
"""
PNPM_V6 = """lockfileVersion: '6.0'

dependencies:
  js-yaml:
    specifier: ^4.1.0
    version: 4.1.0

packages:

  /@types/node@20.0.0:
    resolution: {integrity: sha512-c}
    dev: false

  /js-yaml@4.1.0:
    resolution: {integrity: sha512-d}
    dependencies:
      argparse: 2.0.1
    dev: false

  /use-sync@1.2.0(react@18.2.0):
    resolution: {integrity: sha512-e}
    peerDependencies:
      react: ^18.0.0
    dev: false
"""
PNPM_V5 = """lockfileVersion: 5.4

packages:

  /js-yaml/4.1.0:
    resolution: {integrity: sha512-d}
    dev: false

  /use-sync/1.2.0_react@18.2.0:
    resolution: {integrity: sha512-e}
    dev: false
"""
YARN_V1 = """# THIS IS AN AUTOGENERATED FILE. DO NOT EDIT THIS FILE DIRECTLY.
# yarn lockfile v1


"@babel/code-frame@^7.0.0", "@babel/code-frame@^7.10.4":
  version "7.12.13"
  resolved "https://registry.yarnpkg.com/@babel/code-frame/-/code-frame-7.12.13.tgz#abc"
  integrity sha512-f
  dependencies:
    "@babel/highlight" "^7.12.13"

js-yaml@^4.1.0:
  version "4.1.0"
  resolved "https://registry.yarnpkg.com/js-yaml/-/js-yaml-4.1.0.tgz#def"
"""
YARN_BERRY = """# This file is generated by running "yarn install" inside your project.
# Manual changes might be lost - proceed with caution!

__metadata:
  version: 8
  cacheKey: 10c0

"@babel/code-frame@npm:^7.0.0":
  version: 7.22.5
  resolution: "@babel/code-frame@npm:7.22.5"
  languageName: node
  linkType: hard

"app@workspace:.":
  version: 0.0.0-use.local
  resolution: "app@workspace:."
  languageName: unknown
  linkType: soft

"js-yaml@npm:^4.1.0, js-yaml@npm:^4.3.0":
  version: 4.3.1
  resolution: "js-yaml@npm:4.3.1"
  languageName: node
  linkType: hard

"resolve@patch:resolve@npm%3A^1.22.1#optional!builtin<compat/resolve>":
  version: 1.22.8
  resolution: "resolve@patch:resolve@npm%3A1.22.8#optional!builtin<compat/resolve>::version=1.22.8"
  languageName: node
  linkType: hard

"yml@npm:yaml@2.0.0":
  version: 2.0.0
  resolution: "yaml@npm:2.0.0"
  languageName: node
  linkType: hard
"""
UV_LOCK = """version = 1
requires-python = ">=3.9"

[[package]]
name = "anyio"
version = "4.14.1"
source = { registry = "https://pypi.org/simple" }
dependencies = [
    { name = "idna" },
]
sdist = { url = "https://files.pythonhosted.org/a.tar.gz", hash = "sha256:a", size = 1 }

[[package]]
name = "idna"
version = "3.7"
source = { registry = "https://pypi.org/simple" }
"""
PIPFILE_LOCK = json.dumps({
    "_meta": {"hash": {"sha256": "x"}, "pipfile-spec": 6},
    "default": {"anyio": {"hashes": ["sha256:a"], "version": "==4.14.1"},
                "app": {"editable": True, "path": "."},
                "tool": {"git": "https://github.com/o/tool.git", "ref": "abc"}},
    "develop": {"Typing_Extensions": {"version": "==4.0.0"}}})
NPM_V1 = json.dumps({"name": "old", "lockfileVersion": 1, "requires": True, "dependencies": {
    "js-yaml": {"version": "3.14.0", "dependencies": {"argparse": {"version": "1.0.10"}}},
    "tool": {"version": "github:o/tool#abc", "from": "github:o/tool"}}})
# PEP 751, as `uv export --format pylock.toml` writes it
PYLOCK = """lock-version = "1.0"
created-by = "uv"
requires-python = ">=3.9"

[[packages]]
name = "anyio"
version = "4.14.1"
index = "https://pypi.org/simple"
sdist = { url = "https://files.pythonhosted.org/a.tar.gz", size = 1, hashes = { sha256 = "a" } }

[[packages]]
name = "app"
directory = { path = ".", editable = true }

[[packages]]
name = "idna"
version = "3.7"
index = "https://pypi.org/simple"

[[packages.wheels]]
name = "idna-3.7-py3-none-any.whl"
url = "https://files.pythonhosted.org/idna.whl"
hashes = { sha256 = "c" }
"""
# what each tool writes for a project without dependencies
EMPTY_LOCKFILES = {
    "npm3/package-lock.json": json.dumps({"name": "app", "version": "1.0.0", "lockfileVersion": 3,
                                          "requires": True, "packages": {"": {"name": "app"}}}),
    "npm1/package-lock.json": json.dumps({"name": "app", "version": "1.0.0", "lockfileVersion": 1}),
    "npm-shrinkwrap.json": json.dumps({"name": "app", "lockfileVersion": 3, "packages": {"": {"name": "app"}}}),
    "pnpm-lock.yaml": "lockfileVersion: '9.0'\n\nsettings:\n  autoInstallPeers: true\n\nimporters:\n\n  .: {}\n",
    "yarn.lock": "# THIS IS AN AUTOGENERATED FILE. DO NOT EDIT THIS FILE DIRECTLY.\n# yarn lockfile v1\n\n\n",
    "poetry.lock": 'package = []\n\n[metadata]\nlock-version = "2.0"\npython-versions = "^3.9"\n',
    "Pipfile.lock": json.dumps({"_meta": {"pipfile-spec": 6}, "default": {}, "develop": {}}),
    "pylock.toml": 'lock-version = "1.0"\ncreated-by = "pip"\n',
    "go.sum": "",
}


def test_reads_the_five_manifest_kinds() -> None:
    m = _load()
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        _write(root, "package-lock.json", json.dumps({"lockfileVersion": 3, "packages": {
            "": {"name": "bot"},
            "node_modules/js-yaml": {"version": "4.3.1"},
            "node_modules/@anthropic-ai/sdk": {"version": "0.128.0"},
            "node_modules/a/node_modules/js-yaml": {"version": "3.14.0"},
            "node_modules/yml": {"name": "yaml", "version": "2.0.0"},
            "node_modules/local": {"resolved": "../local", "link": True},
        }}))
        _write(root, "requirements.txt",
               "# pinned\nanyio==4.14.1\n"
               'Requests[socks]==2.19.0 ; python_version >= "3.8"\n'
               "flask>=2.0\n-r requirements-dev.txt\n"
               "Typing_Extensions==4.0.0 \\\n    --hash=sha256:abc\n")
        _write(root, "sub/requirements-dev.txt", "pytest==7.0.0\n")
        _write(root, "poetry.lock", '[[package]]\nname = "idna"\nversion = "3.7"\n'
                                    'description = "x"\n\n[[package]]\nname = "anyio"\nversion = "4.14.1"\n')
        _write(root, "go.sum", "golang.org/x/net v0.7.0 h1:a=\ngolang.org/x/net v0.7.0/go.mod h1:b=\n"
                               "golang.org/x/text v0.3.0/go.mod h1:c=\n")
        _write(root, "Cargo.lock", 'version = 3\n\n[[package]]\nname = "time"\nversion = "0.1.43"\n'
                                   'source = "registry+https://github.com/rust-lang/crates.io-index"\n')
        _write(root, "node_modules/x/package-lock.json", json.dumps({"packages": {
            "node_modules/y": {"version": "1.0.0"}}}))
        _write(root, ".venv/requirements.txt", "evil==1.0\n")
        _write(root, "docs/requirements.txt", "mkdocs>=1.5\n")
        found, unread = m.read_manifests(root)
    assert unread == {"requirements.txt": "declared, not locked",          # flask>=2.0
                      "docs/requirements.txt": "declared, not locked"}, unread
    assert found == {
        "Cargo.lock": [("crates.io", "time", "0.1.43")],
        "go.sum": [("Go", "golang.org/x/net", "v0.7.0")],
        "package-lock.json": [("npm", "@anthropic-ai/sdk", "0.128.0"), ("npm", "js-yaml", "3.14.0"),
                              ("npm", "js-yaml", "4.3.1"), ("npm", "yaml", "2.0.0")],
        "poetry.lock": [("PyPI", "anyio", "4.14.1"), ("PyPI", "idna", "3.7")],
        "requirements.txt": [("PyPI", "anyio", "4.14.1"), ("PyPI", "requests", "2.19.0"),
                             ("PyPI", "typing-extensions", "4.0.0")],
        "sub/requirements-dev.txt": [("PyPI", "pytest", "7.0.0")],
    }, found
    print("OK: reads package-lock, requirements, poetry.lock, go.sum, Cargo.lock")


def test_reads_pnpm_yarn_uv_pipfile_and_package_lock_v1() -> None:
    m = _load()
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        for rel, text in (("pnpm9/pnpm-lock.yaml", PNPM_V9), ("pnpm6/pnpm-lock.yaml", PNPM_V6),
                          ("yarn1/yarn.lock", YARN_V1), ("berry/yarn.lock", YARN_BERRY),
                          ("uv.lock", UV_LOCK), ("Pipfile.lock", PIPFILE_LOCK),
                          ("old/package-lock.json", NPM_V1)):
            _write(root, rel, text)
        found, unread = m.read_manifests(root)
    assert unread == {}, unread
    assert found == {
        "Pipfile.lock": [("PyPI", "anyio", "4.14.1"), ("PyPI", "typing-extensions", "4.0.0")],
        "berry/yarn.lock": [("npm", "@babel/code-frame", "7.22.5"), ("npm", "js-yaml", "4.3.1"),
                            ("npm", "yaml", "2.0.0")],
        "old/package-lock.json": [("npm", "argparse", "1.0.10"), ("npm", "js-yaml", "3.14.0")],
        "pnpm6/pnpm-lock.yaml": [("npm", "@types/node", "20.0.0"), ("npm", "js-yaml", "4.1.0"),
                                 ("npm", "use-sync", "1.2.0")],
        "pnpm9/pnpm-lock.yaml": [("npm", "@babel/core", "7.22.0"), ("npm", "js-yaml", "4.3.1")],
        "uv.lock": [("PyPI", "anyio", "4.14.1"), ("PyPI", "idna", "3.7")],
        "yarn1/yarn.lock": [("npm", "@babel/code-frame", "7.12.13"), ("npm", "js-yaml", "4.1.0")],
    }, found
    print("OK: reads pnpm-lock v6/v9, yarn.lock v1/berry, uv.lock, Pipfile.lock, package-lock v1")


def test_queries_osv_for_pnpm_and_uv_packages() -> None:
    """The probe of the pre-re-audit: js-yaml in pnpm-lock.yaml, anyio in uv.lock."""
    m = _load()
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        _write(root, "pnpm-lock.yaml", PNPM_V9)
        _write(root, "uv.lock", UV_LOCK)
        with patch.object(m, "_fetch", side_effect=_answer):
            findings, tool = m.scan(root)
    assert tool["status"] == "ran" and tool["manifests"] == ["pnpm-lock.yaml", "uv.lock"], tool
    assert sorted((f.file, f.package, f.advisory) for f in findings) == [
        ("pnpm-lock.yaml", "js-yaml", "GHSA-2883-xcg3-v3hh"),
        ("uv.lock", "anyio", "GHSA-82r6-8w77-94w6")], findings
    print("OK: pnpm-lock.yaml and uv.lock packages reach OSV")


def test_a_lockfile_it_cannot_read_makes_the_sca_partial_and_names_it() -> None:
    m = _load()
    calls: list = []
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        _write(root, "requirements.txt", "anyio==4.14.1\n")
        _write(root, "package-lock.json", "{not json")
        _write(root, "legacy/pnpm-lock.yaml", PNPM_V5)
        _write(root, "ruby/Gemfile.lock", "GEM\n  specs:\n    rack (2.2.3)\n")
        with patch.object(m, "_fetch", side_effect=_answer):
            findings, tool = m.scan(root)
        assert tool["status"] == "partial", tool
        for rel in ("package-lock.json", "legacy/pnpm-lock.yaml", "ruby/Gemfile.lock"):
            assert rel in tool["reason"], (rel, tool)
        assert tool["packages"] == 1 and tool["manifests"] == ["requirements.txt"], tool
        assert [f.advisory for f in findings] == ["GHSA-82r6-8w77-94w6"], findings

        with patch.object(m, "_fetch", side_effect=_recorded(calls)):
            findings, tool = m.scan(root / "legacy")
        assert findings == [] and calls == [], calls
        assert tool["status"] == "partial" and "pnpm-lock.yaml" in tool["reason"], tool
        assert "no lockfile" not in tool["reason"], tool
    print("OK: an unreadable or unknown lockfile makes the SCA partial and is named")


def test_a_lockfile_without_dependencies_is_read_with_zero_packages() -> None:
    m = _load()
    calls: list = []
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        for rel, text in EMPTY_LOCKFILES.items():
            _write(root, rel, text)
        assert m.read_manifests(root) == ({}, {})
        with patch.object(m, "_fetch", side_effect=_recorded(calls)):
            findings, tool = m.scan(root)
        assert findings == [] and calls == [] and tool["status"] == "not-applicable", tool
        assert "not read" not in tool["reason"] and "no lockfile" not in tool["reason"], tool

        _write(root, "legacy/pnpm-lock.yaml", PNPM_V5)
        _, unread = m.read_manifests(root)
        assert list(unread) == ["legacy/pnpm-lock.yaml"], unread
    print("OK: an empty lockfile is read with zero packages; pnpm v5 stays unread")


def _sca_rc(root: Path) -> int:
    """The exit code of `audit_scan.py sca` for root."""
    return subprocess.run([sys.executable, str(LIB_DIR.parent / "audit_scan.py"), "sca", str(root)],
                          capture_output=True).returncode


def test_dependencies_declared_but_not_locked_make_the_sca_partial() -> None:
    """f11-sca: a package.json, a version range in requirements.txt or a pyproject.toml without a
    lockfile was not-applicable, and the chain took that for full coverage."""
    m = _load()
    calls: list = []
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        _write(root, "package.json", json.dumps({"name": "bot", "dependencies": {"js-yaml": "^4.1.0"}}))
        _write(root, "web/package.json", json.dumps({"name": "web", "devDependencies": {"vite": "^7.0.0"}}))
        _write(root, "requirements.txt", "# runtime\n-r base.txt\nanyio>=4.14\n")
        _write(root, "py/pyproject.toml", '[project]\nname = "py"\ndependencies = [\n    # net\n    "anyio>=4.14",\n]\n')
        # locked, a workspace member under its root lock, nothing declared: not named
        _write(root, "ws/package-lock.json", json.dumps({"lockfileVersion": 3, "packages": {"": {"name": "ws"}}}))
        _write(root, "ws/packages/a/package.json", json.dumps({"name": "a", "dependencies": {"js-yaml": "^4.1.0"}}))
        _write(root, "uvapp/pyproject.toml", '[project]\nname = "uvapp"\ndependencies = ["anyio>=4.14"]\n')
        _write(root, "uvapp/uv.lock", "version = 1\n")
        _write(root, "tool/package.json", json.dumps({"name": "tool", "dependencies": {}, "scripts": {"t": "x"}}))
        _write(root, "lib/pyproject.toml", '[build-system]\nrequires = ["setuptools"]\n\n'
                                          '[project]\nname = "lib"\ndependencies = []\n')
        with patch.object(m, "_fetch", side_effect=_recorded(calls)):
            findings, tool = m.scan(root)
        rc = _sca_rc(root)
    named = ["package.json", "py/pyproject.toml", "requirements.txt", "web/package.json"]
    assert findings == [] and calls == [] and tool["status"] == "partial", tool
    assert tool["reason"] == "not checked: " + "; ".join(f"{rel} (declared, not locked)" for rel in named), tool
    assert rc == 2, rc
    print("OK: dependencies declared without a lockfile make the SCA partial and are named, exit 2")


def test_a_repository_that_declares_no_dependency_stays_not_applicable() -> None:
    m = _load()
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        _write(root, "package.json", json.dumps({"name": "app", "scripts": {"test": "node t.js"}}))
        _write(root, "pyproject.toml", '[build-system]\nrequires = ["setuptools"]\n\n[project]\nname = "app"\n')
        _write(root, "requirements.txt", "# nothing yet\n")
        _, tool = m.scan(root)
        rc = _sca_rc(root)
    assert tool["status"] == "not-applicable" and rc == 0, (tool, rc)
    print("OK: no dependency declared stays not-applicable, exit 0")


def test_reads_npm_shrinkwrap_and_pylock() -> None:
    m = _load()
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        _write(root, "cli/npm-shrinkwrap.json", json.dumps({"lockfileVersion": 3, "packages": {
            "": {"name": "cli"}, "node_modules/js-yaml": {"version": "4.3.1"}}}))
        _write(root, "py/pylock.toml", PYLOCK)
        _write(root, "py/pylock.dev.toml", PYLOCK.replace("idna", "pytest").replace("3.7", "7.0.0"))
        found, unread = m.read_manifests(root)
        with patch.object(m, "_fetch", side_effect=_answer):
            findings, tool = m.scan(root)
    assert unread == {} and found == {
        "cli/npm-shrinkwrap.json": [("npm", "js-yaml", "4.3.1")],
        "py/pylock.dev.toml": [("PyPI", "anyio", "4.14.1"), ("PyPI", "pytest", "7.0.0")],
        "py/pylock.toml": [("PyPI", "anyio", "4.14.1"), ("PyPI", "idna", "3.7")],
    }, (found, unread)
    assert tool["status"] == "ran" and tool["manifests"] == sorted(found), tool
    assert sorted((f.file, f.advisory) for f in findings) == [
        ("cli/npm-shrinkwrap.json", "GHSA-2883-xcg3-v3hh"), ("py/pylock.dev.toml", "GHSA-82r6-8w77-94w6"),
        ("py/pylock.toml", "GHSA-82r6-8w77-94w6")], findings
    print("OK: npm-shrinkwrap.json and pylock.toml (also pylock.<name>.toml) reach OSV")


def test_reads_single_quoted_toml_and_names_packages_it_cannot_parse() -> None:
    m = _load()
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        _write(root, "a/pylock.toml", "lock-version = '1.0'\n\n[[packages]]\nname = 'anyio'\nversion = '4.14.1'\n")
        _write(root, "b/uv.lock", "version = 1\n\n[[package]]\nversion = \"1.0\"\nname = \"x\"\n")
        found, unread = m.read_manifests(root)
    assert found == {"a/pylock.toml": [("PyPI", "anyio", "4.14.1")]}, found
    assert list(unread) == ["b/uv.lock"], unread
    print("OK: single quotes read; package blocks the reader cannot parse leave the lockfile unread")


# as `uv lock` 0.x writes it for a workspace: the root and a member editable, a path dependency
UV_WORKSPACE = """version = 1
revision = 3
requires-python = ">=3.9"

[manifest]
members = [
    "app",
    "member",
]

[[package]]
name = "anyio"
version = "4.14.1"
source = { registry = "https://pypi.org/simple" }

[[package]]
name = "app"
version = "0.1.0"
source = { editable = "." }
dependencies = [
    { name = "anyio" },
    { name = "lib" },
    { name = "member" },
]

[package.metadata]
requires-dist = [
    { name = "lib", directory = "../lib" },
    { name = "member", editable = "packages/member" },
]

[[package]]
name = "lib"
version = "1.0.0"
source = { directory = "../lib" }

[[package]]
name = "member"
version = "0.2.0"
source = { editable = "packages/member" }

[[package]]
name = "wheel"
version = "1.0"
source = { path = "dist/wheel-1.0-py3-none-any.whl" }
"""
# Cargo writes no source for the root, workspace members and path dependencies
CARGO_WORKSPACE = """# This file is automatically @generated by Cargo.
# It is not intended for manual editing.
version = 4

[[package]]
name = "app"
version = "0.1.0"
dependencies = [
 "member",
 "time",
]

[[package]]
name = "member"
version = "0.2.0"

[[package]]
name = "time"
version = "0.1.43"
source = "registry+https://github.com/rust-lang/crates.io-index"
checksum = "ca8a50ef2360fbd1eeb0ecd46795a87a19024eb4b53c5dc916ca1fd95fe62438"
"""


def test_uv_and_cargo_locks_keep_the_own_project_from_osv() -> None:
    """f9-sca: uv.lock and Cargo.lock list the project itself, its workspace members and path
    dependencies; OSV was asked for them as if they came from PyPI or crates.io."""
    m = _load()
    bodies: list = []
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        _write(root, "py/uv.lock", UV_WORKSPACE)
        _write(root, "rs/Cargo.lock", CARGO_WORKSPACE)
        _write(root, "tool/uv.lock", 'version = 1\n\n[[package]]\nname = "tool"\nversion = "0.1.0"\n'
                                     'source = { virtual = "." }\n')
        _write(root, "solo/Cargo.lock", 'version = 4\n\n[[package]]\nname = "solo"\nversion = "0.1.0"\n')
        assert m.read_manifests(root) == ({"py/uv.lock": [("PyPI", "anyio", "4.14.1")],
                                           "rs/Cargo.lock": [("crates.io", "time", "0.1.43")]}, {})
        with patch.object(m, "_fetch", side_effect=lambda path, body=None: bodies.append(body) or _answer(path, body)):
            _, tool = m.scan(root)
    asked = [q["package"]["name"] for q in bodies[0]["queries"]]
    assert asked == ["anyio", "time"] and tool["status"] == "ran", (asked, tool)
    print("OK: uv.lock and Cargo.lock send no root project, member or path dependency to OSV")


def test_asks_querybatch_then_each_advisory_once() -> None:
    m = _load()
    calls: list = []
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        _probe_repo(root)
        _write(root, "poetry.lock", '[[package]]\nname = "anyio"\nversion = "4.14.1"\n')
        with patch.object(m, "_fetch", side_effect=_recorded(calls)):
            findings, tool = m.scan(root)
    assert calls[0] == ("querybatch", {"queries": [
        {"package": {"ecosystem": "PyPI", "name": "anyio"}, "version": "4.14.1"},
        {"package": {"ecosystem": "PyPI", "name": "requests"}, "version": "2.19.0"},
        {"package": {"ecosystem": "npm", "name": "js-yaml"}, "version": "4.3.1"},
    ]}), calls[0]
    fetched = sorted(p for p, _ in calls[1:])
    assert fetched == sorted(f"vulns/{i}" for i in VULNS), fetched
    assert tool == {"name": "osv", "status": "ran", "packages": 3,
                    "manifests": ["package-lock.json", "poetry.lock", "requirements.txt"]}, tool
    by_id = {}
    for f in findings:
        by_id.setdefault(f.advisory, []).append(f)
    assert "PYSEC-2018-28" not in by_id, "the PYSEC twin of a GHSA advisory is a duplicate"
    yaml_hit, = by_id["GHSA-2883-xcg3-v3hh"]
    assert (yaml_hit.package, yaml_hit.version, yaml_hit.aliases, yaml_hit.severity,
            yaml_hit.published, yaml_hit.fixed, yaml_hit.file, yaml_hit.cwe, yaml_hit.engine) == (
        "js-yaml", "4.3.1", ["CVE-2026-84375"], "high", "2026-09-08", "4.3.2",
        "package-lock.json", "CWE-400", "osv"), yaml_hit
    assert sorted(f.file for f in by_id["GHSA-82r6-8w77-94w6"]) == ["poetry.lock", "requirements.txt"]
    assert {f.severity for f in by_id["GHSA-82r6-8w77-94w6"]} == {"critical"}
    assert by_id["GHSA-x84v-xcm2-53pg"][0].fixed == "2.20.0"
    for f in findings:
        assert f.advisory in f.message and f.package in f.message, f.message
    assert len({f.fp for f in findings}) == len(findings), "one fingerprint per manifest, package version and advisory"
    print("OK: querybatch, one /vulns/{id} per advisory, ID, CVE, severity, date, fix")


def test_offline_and_api_errors_are_results_not_clean_runs() -> None:
    m = _load()
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        _probe_repo(root)
        dead = "http://127.0.0.1:9"
        env = {k: v for k, v in os.environ.items() if k.lower() not in ("no_proxy", "all_proxy")}
        env.update(https_proxy=dead, HTTPS_PROXY=dead)
        with patch.dict(os.environ, env, clear=True):
            findings, tool = m.scan(root)
        assert findings == [] and tool["status"] == "offline" and tool["reason"], tool

        def fail(path, body=None):
            raise urllib.error.HTTPError("https://api.osv.dev/v1/" + path, 503, "Unavailable", {}, None)
        with patch.object(m, "_fetch", side_effect=fail):
            findings, tool = m.scan(root)
        assert findings == [] and tool["status"] == "error" and "503" in tool["reason"], tool

        empty = root / "empty"
        empty.mkdir()
        _, tool = m.scan(empty)
        assert tool["status"] == "not-applicable", tool
    print("OK: offline and API errors are named, no manifest is not-applicable")


ALL_TESTS = [
    test_reads_the_five_manifest_kinds,
    test_reads_pnpm_yarn_uv_pipfile_and_package_lock_v1,
    test_queries_osv_for_pnpm_and_uv_packages,
    test_a_lockfile_it_cannot_read_makes_the_sca_partial_and_names_it,
    test_a_lockfile_without_dependencies_is_read_with_zero_packages,
    test_dependencies_declared_but_not_locked_make_the_sca_partial,
    test_a_repository_that_declares_no_dependency_stays_not_applicable,
    test_reads_npm_shrinkwrap_and_pylock,
    test_reads_single_quoted_toml_and_names_packages_it_cannot_parse,
    test_uv_and_cargo_locks_keep_the_own_project_from_osv,
    test_asks_querybatch_then_each_advisory_once,
    test_offline_and_api_errors_are_results_not_clean_runs,
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
    print("\nAll osv tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
