---
applies-when: detect reports LLM/agent APIs, or the repo carries MCP server configuration
read-when: Phase 4, when the model acts (tools, memory, other agents) or the project uses or ships MCP servers
as-of: 2026-09-24
source: https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/
---

# Agentic and MCP risks

The LLM checklist covers the model as a component. Once the model acts
(calls tools, keeps memory, talks to other agents), the OWASP Top 10 for
Agentic Applications 2026 applies. MCP servers add the OWASP MCP Top 10
(2025, beta: https://owasp.org/www-project-mcp-top-10/) and the MCP
Security Cheat Sheet
(https://cheatsheetseries.owasp.org/cheatsheets/MCP_Security_Cheat_Sheet.html).

## Agentic Top 10 (2026) at a glance

| Code | Risk | First check |
|---|---|---|
| ASI01 | Agent Goal Hijack | see Goal Hijack below |
| ASI02 | Tool Misuse and Exploitation | Can an allowed tool be chained or called with arguments that delete, send, or spend? |
| ASI03 | Identity and Privilege Abuse | Does the agent act under its own least-privilege identity, or with the user's full rights? |
| ASI04 | Agentic Supply Chain Vulnerabilities | see Tool Poisoning, Rug Pull, MCP configuration supply chain |
| ASI05 | Unexpected Code Execution (RCE) | Does generated or tool-supplied code run outside a sandbox? |
| ASI06 | Memory & Context Poisoning | Can untrusted text land in memory that later sessions replay as trusted? |
| ASI07 | Insecure Inter-Agent Communication | Are messages between agents authenticated and checked for origin? |
| ASI08 | Cascading Failures | Does one agent's bad output reach others without a checkpoint? |
| ASI09 | Human-Agent Trust Exploitation | Does an approval prompt show the real action, not the agent's summary of it? |
| ASI10 | Rogue Agents | Is agent behavior logged against a baseline, with a kill switch? |

MCP Top 10 (2025, beta): MCP01 Token Mismanagement & Secret Exposure,
MCP02 Privilege Escalation via Scope Creep, MCP03 Tool Poisoning, MCP04
Software Supply Chain Attacks & Dependency Tampering, MCP05 Command
Injection & Execution, MCP06 Prompt Injection via Contextual Payloads,
MCP07 Insufficient Authentication & Authorization, MCP08 Lack of Audit
and Telemetry, MCP09 Shadow MCP Servers, MCP10 Context Injection &
Over-Sharing.

## Goal Hijack (ASI01)

Text from an issue, web page, email, file, tool output, or peer agent
changes what the agent is trying to do, beyond a single answer (that is
LLM01).

- Can any untrusted input change the agent's task, plan, or tool choice?
- Is the goal fixed outside the context window (config, approved plan)
  and checked again before a high-impact or goal-changing action?
- Does a deviation from the original task pause the run for review?
- Is the active goal logged, so a drift shows up afterwards?

## Tool Poisoning (MCP03, ASI02, ASI04)

Instructions hidden in a tool's name, description, parameter schema, or
return value. The model treats that text as authoritative.

- Is the whole tool schema reviewed as injection surface, not only
  `description`?
- Does tool text address the model (hide something from the user, read
  a file first), name secret paths (`~/.ssh`, `.env`), pair a send verb
  with a URL, or carry zero-width characters or HTML comments?
- Can one server's tool text change how the agent uses another server's
  tools, and can two servers register the same tool name (shadowing)?

## Rug Pull (MCP03)

A server changes its tool definitions after the user approved them.

- Are approved tool definitions pinned by hash and compared before each
  call?
- Does a changed definition force a new approval, or does the client
  apply it silently?
- Can a new server version reach users without a reviewed change?

## Shadow MCP (MCP09)

MCP servers that run outside any review: started for a test, added by
one developer, or launched by a repo config nobody approved.

- Can you list every MCP server the project starts or recommends (repo
  configs, docs, setup scripts)?
- Does a repo config start servers without a per-user approval step
  (for example Claude Code `enableAllProjectMcpServers`)?
- Are HTTP/SSE servers bound to `127.0.0.1` and authenticated?
- Do test servers reach production data or credentials?

## MCP configuration supply chain (MCP04, ASI04)

MCP configuration runs code on every machine that opens the repo:
`.mcp.json`, `.cursor/mcp.json`, `.vscode/mcp.json`,
`claude_desktop_config.json`, `[mcp_servers]` in a Codex `config.toml`.

- Does an entry launch a server via `npx -y`, `uvx`, or `@latest`
  without an exact version? Each start then runs whatever the registry
  serves that day.
- Is each server package pinned (exact version, lockfile, or hash) and
  from the expected publisher (typosquats, look-alike names, internal
  names that resolve on a public registry)?
- Do configs carry secrets inline in `env` or `headers` instead of a
  reference to the environment or keychain (MCP01)?
- Does a server get more scope than its job needs, such as the
  filesystem root, broad tokens, or write access (MCP02)?
- Does a change to these files get the same review as a CI workflow?

## Finding shape

Name the ASI or MCP code next to the CWE (CWE-829 for an unpinned or
untrusted server, CWE-94 or CWE-78 for tool-driven execution). Severity
follows the reachable impact, as in `agent-approval-gate.md`.
