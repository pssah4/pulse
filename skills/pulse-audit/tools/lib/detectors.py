"""Project-type detection and attack-surface enumeration.

Pure file inspection: no network, no external tools, deterministic.

detect_project(root) -> dict
    Classifies runtimes (node/python/...) and project kinds
    (electron/obsidian-plugin/web-app/cli/library). Multiple kinds may
    apply at once (an Obsidian plugin is also electron). This is what
    makes the audit projekttyp-adaptiv: the detected kinds gate which
    reference checklists and which SAST rulesets apply.

enumerate_surfaces(root, files) -> list[dict]
    Deterministic grep of trust-boundary entry points across the given
    files, plus the agent-specific ones: model calls in code, HTML
    comments in Markdown that speak to agents, unpinned MCP servers.
    Feeds the attack-surface reference section. Not findings --
    context. Output is sorted so two runs match byte-for-byte.

reference_currency(refs, today) -> dict
    The as-of date of each bundled reference and a warning once one is
    undated or 90 days old: the scanner states how current its knowledge is.
"""
# security-audit-scan: skip -- this module stores surface-detection
# regexes as data literals; scanning it against those same regexes only
# produces self-referential false positives.
from __future__ import annotations
import json
import re
from datetime import date
from pathlib import Path
from typing import Iterable

# ---------- project-type detection -----------------------------------------

# Frameworks whose presence in dependencies marks a web application.
_WEBAPP_DEPS = (
    "express", "koa", "fastify", "next", "nuxt", "react", "vue",
    "svelte", "@angular/core", "vite", "hapi", "@nestjs/core",
    "flask", "django", "fastapi", "starlette",
)
# Dependency names that indicate an LLM/agent API is used (gates phase 4).
_LLM_DEPS = (
    "@anthropic-ai/sdk", "anthropic", "openai", "@google/generative-ai",
    "@mistralai/mistralai", "cohere-ai", "langchain", "@langchain/core",
    "ollama", "llamaindex", "cohere", "mistralai", "google-genai",
    "google-generativeai", "llama-index", "litellm",
)
# A requirement's distribution name: at line start (requirements*.txt, Poetry
# tables) or opening a quoted PEP 508 string (pyproject dependencies).
_PY_DEP = re.compile(r"""(?:^[ \t]*|["'])([A-Za-z0-9][\w.-]*)[ \t]*(?:\[[^\]]*\])?[ \t]*(?:[<>=!~;@"']|$)""", re.M)


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _python_deps(root: Path) -> set:
    """Normalized names from requirements*.txt and pyproject.toml; a regex,
    because Python 3.9 has no TOML parser."""
    names = set()
    for path in [*root.glob("requirements*.txt"), root / "pyproject.toml"]:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        names.update(re.sub(r"[-_.]+", "-", n).lower() for n in _PY_DEP.findall(text))
    return names


def detect_project(root: Path) -> dict:
    pkg_path = root / "package.json"
    pkg = _read_json(pkg_path)
    deps = {}
    deps.update(pkg.get("dependencies", {}) or {})
    dev = pkg.get("devDependencies", {}) or {}
    all_deps = dict(deps)
    all_deps.update(dev)

    has_pkg = pkg_path.is_file()
    manifest = _read_json(root / "manifest.json")
    is_obsidian_manifest = bool(
        manifest.get("id") and manifest.get("minAppVersion")
    ) or ("obsidian" in dev)

    runtimes: list = []
    if has_pkg:
        runtimes.append("node")
    if (root / "pyproject.toml").is_file() or (root / "requirements.txt").is_file() \
            or (root / "setup.py").is_file():
        runtimes.append("python")
    if (root / "go.mod").is_file():
        runtimes.append("go")
    if (root / "Cargo.toml").is_file():
        runtimes.append("rust")

    kinds: list = []
    electron = "electron" in all_deps
    if is_obsidian_manifest:
        kinds.append("obsidian-plugin")
        # Obsidian plugins run inside Electron's renderer even without an
        # explicit electron dependency.
        electron = True
    if electron:
        kinds.append("electron")
    if any(d in all_deps for d in _WEBAPP_DEPS):
        kinds.append("web-app")
    # CLI: a bin field. Library: exports/module and not private, no bin.
    if has_pkg and pkg.get("bin"):
        kinds.append("cli")
    if has_pkg and not pkg.get("bin") and (pkg.get("exports") or pkg.get("module")) \
            and pkg.get("private") is not True:
        kinds.append("library")

    # De-dupe while preserving first-seen order.
    seen = set()
    kinds = [k for k in kinds if not (k in seen or seen.add(k))]

    llm_api = any(d in all_deps for d in _LLM_DEPS) or bool(_python_deps(root) & set(_LLM_DEPS))

    applicable_tools = _applicable_tools(runtimes, kinds)
    codeql_languages = _codeql_languages(runtimes)

    return {
        "runtimes": runtimes,
        "project_kinds": kinds,
        "codeql_languages": codeql_languages,
        "signals": {
            "package_json": has_pkg,
            "obsidian_manifest": is_obsidian_manifest,
            "electron_dep": "electron" in all_deps,
            "bin_field": bool(pkg.get("bin")),
            "exports_field": bool(pkg.get("exports") or pkg.get("module")),
            "llm_api": llm_api,
            "lockfiles": sorted(
                n for n in ("package-lock.json", "yarn.lock", "pnpm-lock.yaml",
                            "poetry.lock", "Cargo.lock", "go.sum")
                if (root / n).is_file()
            ),
        },
        "applicable_tools": applicable_tools,
        "reference_gates": _reference_gates(kinds, llm_api),
    }


def _codeql_languages(runtimes: list) -> list:
    """Map detected runtimes to CodeQL extractor names.
    The `javascript` extractor covers both JS and TS.
    """
    mapping = {
        "node": "javascript",
        "python": "python",
        "go": "go",
        "rust": "rust",
    }
    langs = []
    for rt in runtimes:
        lang = mapping.get(rt)
        if lang and lang not in langs:
            langs.append(lang)
    return langs


def _applicable_tools(runtimes: list, kinds: list) -> dict:
    sast = []
    # Action-pinning applies to every project with workflows; the runner
    # itself degrades to not-applicable when .github/workflows is absent.
    supply = ["action-pinning"]
    if "node" in runtimes:
        sast.append("semgrep:p/typescript")
        sast.append("semgrep:p/javascript")
        supply.extend(["lockfile-provenance", "install-scripts",
                       "manifest-hygiene"])
    if "python" in runtimes:
        sast.append("semgrep:p/python")
        supply.append("python-pins")
    # the OSV API covers npm, PyPI, Go and Cargo alike
    sca = ["osv"] if runtimes else []
    return {"sast": sast, "sca": sca,
            "secrets": ["gitleaks", "trufflehog"],
            "supply_chain": supply}


def _reference_gates(kinds: list, llm_api: bool) -> dict:
    """Which reference checklists apply for this project."""
    return {
        "desktop-runtime": "electron" in kinds,
        "owasp-llm": llm_api,
        "web": "web-app" in kinds,
    }


# ---------- attack-surface enumeration -------------------------------------

# (surface_type, compiled regex). Order does not matter; output is sorted.
_SURFACE_PATTERNS = [
    ("code_execution", re.compile(r"\b(eval|new\s+Function|vm\.runIn\w+)\s*\(")),
    ("child_process", re.compile(r"\b(child_process|execSync|spawnSync|\.spawn|\.exec|execFile|subprocess\.(run|call|check_call|check_output|Popen)|os\.(system|popen))\b")),
    ("network_egress", re.compile(r"\b(fetch|requestUrl|axios|http\.get|https\.get|http\.request|urlopen|(requests|httpx)\.(get|post|put|patch|delete|request))\s*\(")),
    ("llm_call", re.compile(r"\b(messages|completions|responses)\.(create|stream)\s*\(|\bgenerate_?[cC]ontent\s*\(")),
    ("http_server", re.compile(r"\b(createServer|app\.(get|post|put|delete|patch)|listen)\s*\(")),
    ("message_listener", re.compile(r"addEventListener\s*\(\s*['\"]message['\"]|ipcMain\.(on|handle)|ipcRenderer\.(on|invoke)")),
    ("deserialization", re.compile(r"\b(JSON\.parse|yaml\.load|pickle\.loads|unserialize)\s*\(")),
    ("dom_sink", re.compile(r"\.(innerHTML|outerHTML)\b|dangerouslySetInnerHTML|document\.write\s*\(")),
    ("filesystem", re.compile(r"\bfs\.(read|write|append|unlink|rm|mkdir)\w*\s*\(|readFileSync|writeFileSync|(?<![.\w])open\s*\(")),
    ("shell_open", re.compile(r"\bshell\.(openExternal|openPath)\s*\(")),
    ("protocol_handler", re.compile(r"registerProtocol|setAsDefaultProtocolClient|registerObsidianProtocol")),
]

# Text-file extensions worth scanning; anything else is skipped as binary.
_TEXT_EXT = {
    ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".py", ".go", ".rs",
    ".java", ".rb", ".php", ".vue", ".svelte",
}


# An HTML comment is invisible on the rendered page, but agents read it verbatim.
# An unclosed one runs to the end, as in HTML.
_HTML_COMMENT = re.compile(r"<!--(.*?)(?:-->|\Z)", re.S)
_AGENT_WORD = re.compile(r"\b(agents?|AI|assistants?|LLMs?|Claude|Codex|Copilot|Cursor|Gemini)\b", re.I)
# An MCP server that npx fetches fresh at every start: -y/--yes or an @latest tag.
_MCP_PATTERNS = [
    ("mcp_unpinned", re.compile(r"""["'](-y|--yes)["']|\bnpx\s+(-y|--yes)\b|@latest\b""")),
]
_CONFIG_EXT = {".json", ".toml", ".yaml", ".yml"}


def _agent_comments(rel: str, text: str) -> list:
    """One surface per HTML comment that names an agent. The symbol holds only
    the matched word: the comment's text would reach the auditing model."""
    out = []
    for m in _HTML_COMMENT.finditer(text):
        word = _AGENT_WORD.search(m.group(1))
        if word:
            out.append({"surface_type": "agent_instruction", "file": rel,
                        "line": text.count("\n", 0, m.start()) + 1,
                        "symbol": f"<!-- {word.group(0)} -->"})
    return out


def enumerate_surfaces(root: Path, files: Iterable[str]) -> list:
    """Grep the given files for trust-boundary entry points. Returns a
    sorted list of {surface_type, file, line, symbol}. Missing/binary
    files are skipped, never fatal.
    """
    out: list = []
    for rel in files:
        path = root / rel
        if path.suffix not in _TEXT_EXT | _CONFIG_EXT | {".md"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue
        if path.suffix == ".md":
            out.extend(_agent_comments(rel, text))
            continue
        if path.suffix in _TEXT_EXT:
            patterns = _SURFACE_PATTERNS
        elif "mcp" in rel.lower() or "mcpServers" in text or "mcp_servers" in text:
            patterns = _MCP_PATTERNS
        else:
            continue
        for ln, line in enumerate(text.splitlines(), start=1):
            for surface_type, rx in patterns:
                m = rx.search(line)
                if m:
                    out.append({
                        "surface_type": surface_type,
                        "file": rel,
                        "line": ln,
                        "symbol": m.group(0).strip(),
                    })
    # Deterministic ordering, independent of input file order.
    out.sort(key=lambda s: (s["file"], s["line"], s["surface_type"]))
    return out


# ---------- knowledge currency ----------------------------------------------

_REFS = Path(__file__).resolve().parents[2] / "references"
_AS_OF = re.compile(r"^as-of:[ \t]*(\d{4}-\d{2}-\d{2})[ \t]*$", re.M)


def reference_currency(refs: Path = _REFS, today: date | None = None) -> dict:
    """meta fields: `taxonomy`, the as-of date per bundled reference (None when
    the front matter has none), and `taxonomy_warning`, which names every
    reference undated or at least 90 days old (None when all are current)."""
    today = today or date.today()
    as_of, old = {}, []
    for path in sorted(refs.glob("*.md")):
        m = _AS_OF.search(path.read_text(encoding="utf-8").split("\n---", 1)[0])
        try:
            age = (today - date.fromisoformat(m.group(1))).days if m else None
        except ValueError:
            age = None
        as_of[path.stem] = m.group(1) if age is not None else None
        if age is None or age >= 90:
            old.append(f"{path.stem} ({'no as-of' if age is None else f'{age} days'})")
    warning = ("bundled references undated or at least 90 days old: " + ", ".join(old)
               + "; update Pulse or run the Phase 0 live check") if old else None
    return {"taxonomy": as_of, "taxonomy_warning": warning}
