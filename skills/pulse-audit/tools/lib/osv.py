"""Dependency advisories from the OSV API (https://osv.dev), stdlib only.

The one SCA source for npm, PyPI, Go and crates.io. Reads the lockfiles
and pinned requirements, asks /v1/querybatch which of those versions carry
advisories, then fetches each advisory once from /v1/vulns/{id} for its
aliases, rating, dates and fix. A lookup that fails is a result (`offline`
or `error` with the reason), never a clean run with zero findings; a
lockfile it cannot read makes the run `partial` and is named.

In a diff scope an advisory blocks only when its manifest changed in the
scope; the others stay visible as `info` notes, so a docs commit does not
inherit every CVE of the repository.
"""
from __future__ import annotations
import json
import os
import re
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

try:
    from . import findings as F
except ImportError:  # pragma: no cover
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import findings as F  # type: ignore

API = "https://api.osv.dev/v1"
BATCH = 1000  # queries per /v1/querybatch call, the API's limit
_RATING = {"CRITICAL": "critical", "HIGH": "high", "MODERATE": "medium",
           "MEDIUM": "medium", "LOW": "low"}
_REQ_RE = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*(?:\[[^\]]*\])?\s*==\s*([^\s;#\\]+)")
_TOML_PKG_RE = re.compile(r"""^\[\[packages?\]\]\s*\nname\s*=\s*["']([^"']+)["']\s*\nversion\s*=\s*["']([^"']+)["']"""
                          r"(?:\s*\nsource\s*=\s*(.*))?", re.M)
# the project itself, its workspace members and path dependencies: in uv.lock an editable, virtual,
# directory or path source, in Cargo.lock no source
_OWN = re.compile(r"$|\{\s*(?:editable|virtual|directory|path)\s*=")
_NPM_NAME = r"""(?:@[^/\s'"]+/)?[^@/\s'"(]+"""  # `name` or `@scope/name`
# pnpm v6 `/name@1.0.0(peer@2):`, v9 `name@1.0.0:`; a version not starting with a digit is a URL or path
_PNPM_RE = re.compile(r"""^  ['"]?/?(%s)@(\d[^(\s'":]*)""" % _NPM_NAME, re.M)
_YARN_V1_RE = re.compile(r'^"?(%s)@[^\n]*:\n  version "([^"]+)"' % _NPM_NAME, re.M)
_YARN_BERRY_RE = re.compile(r'^  resolution: "(%s)@npm:([^"\s]+)"' % _NPM_NAME, re.M)
# lockfiles OSV knows and this reader does not: named as unread, never skipped
_NO_READER = {"bun.lock", "bun.lockb", "deno.lock", "composer.lock", "Gemfile.lock", "pdm.lock",
              "packages.lock.json", "gradle.lockfile", "pubspec.lock", "mix.lock"}


@dataclass
class Advisory(F.Finding):
    """An SCA finding: one advisory against one package version in one manifest."""
    package: str = ""
    version: str = ""
    advisory: str = ""
    aliases: list = field(default_factory=list)
    published: str = ""
    fixed: str = ""


# ---------- manifests ------------------------------------------------------

def _npm(text: str) -> list:
    lock = json.loads(text)
    if "packages" not in lock:  # lockfileVersion 1: a tree under `dependencies`
        return list(_npm_v1(lock.get("dependencies") or {}))
    return [("npm", v.get("name") or path.rsplit("node_modules/", 1)[1], v["version"])
            for path, v in lock["packages"].items()
            if "node_modules/" in path and "version" in v and not v.get("link")]


def _npm_v1(deps: dict):
    for name, v in deps.items():
        if v.get("version", "")[:1].isdigit():  # not `github:...` or `file:...`
            yield "npm", name, v["version"]
        yield from _npm_v1(v.get("dependencies") or {})


def _pnpm(text: str) -> list:
    version = re.search(r"^lockfileVersion: '?(\d+)", text, re.M)
    if not version or int(version[1]) < 6:  # v5 names packages `/name/1.0.0`
        raise ValueError("lockfile format before v6")
    packages = re.search(r"^packages:\n(.*?)(?=^\S|\Z)", text, re.M | re.S)
    return [("npm", n, v) for n, v in _PNPM_RE.findall(packages[1] if packages else "")]


def _yarn(text: str) -> list:
    # v1 names the package in each block header; berry in `resolution:`, where `@npm:` marks the
    # registry (workspaces, patches and git are not in OSV). ponytail: a v1 alias `a@npm:b@1`
    # is asked as `a`; read `resolved` if aliases hide advisories
    return [("npm", n, v) for n, v in _YARN_V1_RE.findall(text) + _YARN_BERRY_RE.findall(text)]


def _pep503(name: str) -> str:
    """PyPI name normalization, so `Typing_Extensions` asks for `typing-extensions`."""
    return re.sub(r"[-_.]+", "-", name).lower()


def _requirements(text: str) -> list:
    return [("PyPI", _pep503(m[1]), m[2]) for m in map(_REQ_RE.match, text.splitlines()) if m]


def _pipfile(text: str) -> list:
    lock = json.loads(text)
    return [("PyPI", _pep503(name), v["version"][2:])
            for group in ("default", "develop") for name, v in (lock.get(group) or {}).items()
            if v.get("version", "").startswith("==")]  # editable and git entries have no version


def _go_sum(text: str) -> list:
    rows = (ln.split() for ln in text.splitlines())
    # a `/go.mod` line only pins the module graph; the build uses the others
    return [("Go", r[0], r[1]) for r in rows if len(r) > 1 and not r[1].endswith("/go.mod")]


def _toml(ecosystem: str, own: bool = False):
    """own: the lockfile lists the own project too (uv, Cargo), which is no package of the registry."""
    def parse(text: str) -> list:
        found = _TOML_PKG_RE.findall(text)
        if not found and re.search(r"^\[\[packages?\]\]", text, re.M):
            raise ValueError("package entries in a layout this reader does not know")
        return [(ecosystem, n, v) for n, v, source in found if not (own and _OWN.match(source))]
    return parse


_PARSERS = {"package-lock.json": _npm, "npm-shrinkwrap.json": _npm, "pnpm-lock.yaml": _pnpm,
            "yarn.lock": _yarn, "poetry.lock": _toml("PyPI"), "uv.lock": _toml("PyPI", own=True),
            "Pipfile.lock": _pipfile, "go.sum": _go_sum, "Cargo.lock": _toml("crates.io", own=True)}


def _parser(name: str):
    if name.startswith("requirements") and name.endswith(".txt"):
        return _requirements
    if re.fullmatch(r"pylock(\.[^.]+)?\.toml", name):  # PEP 751: `pylock.toml`, `pylock.<name>.toml`
        return _toml("PyPI")
    return _PARSERS.get(name)


def read_manifests(root: Path) -> tuple:
    """({manifest path: sorted (ecosystem, name, version)}, {path: why unchecked}) for
    every lockfile and pinned requirements*.txt under root, without dot directories and
    node_modules. A lockfile without dependencies is read with none; one in a format its
    reader does not know is unchecked. So are dependencies declared, not locked: a
    requirements*.txt line without `==`, and a package.json with dependencies or
    devDependencies or a pyproject.toml with [project] dependencies when no lockfile of
    theirs lies in their directory or one above (a workspace lock covers its members).
    ponytail: a lock above also covers a nested project outside the workspace, and Cargo.toml,
    go.mod, Pipfile, setup.py and [tool.poetry] tables are no declarations here; read the
    lock's workspace list or those files when such a project turns up."""
    out, unread, locked = {}, {}, {}
    for top, dirs, names in os.walk(root):
        dirs[:] = sorted(d for d in dirs if not d.startswith(".") and d != "node_modules")
        npm, py = locked.get(os.path.dirname(top), (False, False))  # a lock covers the directories below
        npm = npm or any(n in ("package-lock.json", "npm-shrinkwrap.json", "pnpm-lock.yaml", "yarn.lock",
                               "bun.lock", "bun.lockb") for n in names)
        py = py or any(n in ("uv.lock", "poetry.lock", "pdm.lock") or re.fullmatch(r"pylock(\.[^.]+)?\.toml", n)
                       for n in names)
        locked[top] = npm, py
        for name in names:
            if name in _NO_READER:
                unread[Path(top, name).relative_to(root).as_posix()] = "no reader for this lockfile"
            parse = _parser(name)
            if not parse and name not in ("package.json", "pyproject.toml"):
                continue
            rel = Path(top, name).relative_to(root).as_posix()
            try:
                text = Path(top, name).read_text(encoding="utf-8")
                pkgs = sorted(set(parse(text))) if parse else []
                if name == "package.json":
                    declared = not npm and any(json.loads(text).get(k) for k in ("dependencies", "devDependencies"))
                elif name == "pyproject.toml":  # the [project] table has `dependencies = [` with an entry
                    declared = not py and re.search(
                        r"^\[project\](?:(?!^\[).)*?^dependencies\s*=\s*\[(?:\s|#[^\n]*\n)*[\"']", text, re.M | re.S)
                else:  # a requirement line, not an option, a path or a comment, without `==`
                    declared = parse is _requirements and any(
                        re.match(r"\s*[A-Za-z0-9]", ln) and not _REQ_RE.match(ln) for ln in text.splitlines())
            except Exception as exc:  # noqa: BLE001  any manifest that fails is a blind spot, not a crash
                unread[rel] = f"{type(exc).__name__}: {exc}"
                continue
            if declared:
                unread[rel] = "declared, not locked"
            if pkgs:
                out[rel] = pkgs
    return out, unread


# ---------- API ------------------------------------------------------------

def _fetch(path: str, body: dict | None = None) -> dict:
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(f"{API}/{path}", data=data,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read())


def _query(pkgs: list) -> dict:
    """{(ecosystem, name, version): [advisory ids]} from /v1/querybatch."""
    ids = {}
    for i in range(0, len(pkgs), BATCH):
        chunk = pkgs[i:i + BATCH]
        answer = _fetch("querybatch", {"queries": [
            {"package": {"ecosystem": eco, "name": name}, "version": ver}
            for eco, name, ver in chunk]})
        # ponytail: next_page_token (over 1000 advisories for one version) is not followed
        for pkg, result in zip(chunk, answer["results"]):
            ids[pkg] = [v["id"] for v in result.get("vulns", [])]
    return ids


def _advisories(ids: list) -> dict:
    with ThreadPoolExecutor(max_workers=8) as pool:
        return dict(zip(ids, pool.map(lambda vid: _fetch(f"vulns/{vid}"), ids)))


# ---------- findings -------------------------------------------------------

def _severity(vuln: dict) -> str:
    if vuln["id"].startswith("MAL-"):
        return "critical"  # a malicious package, not a bug
    # ponytail: advisories without a GHSA-style rating (Go, some RUSTSEC) count as
    # medium; score their CVSS vector if that hides criticals
    rating = str((vuln.get("database_specific") or {}).get("severity", "")).upper()
    return _RATING.get(rating, "medium")


def _vkey(version: str) -> tuple:
    return tuple(int(n) for n in re.findall(r"\d+", version))


def _fix(vuln: dict, name: str, version: str) -> str:
    """The lowest fixed version above the installed one, "" when none is released."""
    fixed = []
    for affected in vuln.get("affected", []):
        if affected.get("package", {}).get("name", "").lower() != name.lower():
            continue
        for rng in affected.get("ranges", []):
            if rng.get("type") != "GIT":
                fixed += [e["fixed"] for e in rng.get("events", []) if "fixed" in e]
    return min((f for f in fixed if _vkey(f) > _vkey(version)), key=_vkey, default="")


def _finding(rel: str, name: str, version: str, vuln: dict, blocking: bool) -> Advisory:
    vid, aliases = vuln["id"], vuln.get("aliases", [])
    rating, published, fixed = _severity(vuln), vuln.get("published", "")[:10], _fix(vuln, name, version)
    message = (f"{name} {version}: {vid}" + (f" ({', '.join(aliases)})" if aliases else "")
               + f", {rating}, published {published}, fixed in {fixed or 'no release yet'}."
               + (f" {vuln['summary']}" if vuln.get("summary") else ""))
    if not blocking:
        message = f"Note, {rel} is unchanged in this scope: {message}"
    return Advisory(
        fp=F.fingerprint("SCA", rel, f"{name} {version} {vid}"), phase="sca",
        cwe=((vuln.get("database_specific") or {}).get("cwe_ids") or [""])[0],
        severity=rating if blocking else "info", file=rel, line=None, engine="osv",
        message=message, package=name, version=version, advisory=vid,
        aliases=aliases, published=published, fixed=fixed)


def scan(root: Path, changed=None) -> tuple:
    """(findings, tool entry). `changed`: the files of a diff scope; advisories
    of other manifests become notes. None (full scope) makes every one block."""
    manifests, unread = read_manifests(root)
    pkgs = sorted({p for ps in manifests.values() for p in ps})
    if not pkgs and not unread:
        return [], {"name": "osv", "status": "not-applicable",
                    "reason": "no dependency in a lockfile, requirements file, package.json or pyproject.toml"}
    try:
        ids = _query(pkgs)
        vulns = _advisories(sorted({vid for found in ids.values() for vid in found}))
    except urllib.error.HTTPError as exc:
        return [], {"name": "osv", "status": "error", "reason": f"HTTP {exc.code} from api.osv.dev"}
    except ValueError as exc:
        return [], {"name": "osv", "status": "error", "reason": f"unreadable answer from api.osv.dev: {exc}"}
    except OSError as exc:  # URLError (no route, DNS, refused proxy) and timeouts
        return [], {"name": "osv", "status": "offline", "reason": str(getattr(exc, "reason", exc))}
    out = []
    for rel, rel_pkgs in manifests.items():
        for eco, name, version in rel_pkgs:
            found = ids[(eco, name, version)]
            for vid in found:
                vuln = vulns[vid]
                if not vid.startswith("GHSA-") and set(vuln.get("aliases", [])) & set(found):
                    continue  # the GHSA twin of this advisory carries the rating
                out.append(_finding(rel, name, version, vuln, changed is None or rel in changed))
    tool = {"name": "osv", "status": "ran", "packages": len(pkgs), "manifests": sorted(manifests)}
    if unread:
        tool.update(status="partial", reason="not checked: " + "; ".join(
            f"{rel} ({why})" for rel, why in sorted(unread.items())))
    return out, tool
