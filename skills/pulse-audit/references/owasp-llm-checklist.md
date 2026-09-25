---
edition: "2026"
as-of: 2026-09-24
source: https://genai.owasp.org/resource/owasp-genai-llm-top-10-2026/
authority: >
  Offline baseline. Phase 0 live-currency fetches the current OWASP Top
  10 for LLM Applications from genai.owasp.org, reconciles, and snapshots
  the edition used. Live snapshot wins when it ran; else this applies and
  the report says so.
---

# OWASP Top 10 for LLM Applications (edition 2026)

Relevant only when the project uses LLM/agent APIs (`detect` reports
`reference_gates.owasp-llm = true`). Cite the codes with the edition
(`LLM03:2026`); the 2026 list renumbered most entries, the 2025 code
stands next to each heading. This list covers the model as a component.
Once the model acts (tools, memory, other agents), also work through
`agentic-mcp.md`.

## LLM01:2026 Prompt Injection

- Is the system prompt protected?
- Is user input filtered before it reaches the LLM?
- Indirect injection via documents/web/tool metadata considered, including
  instructions hidden in images or audio?
- Defang iterates to a fixpoint (not single-pass); markers line-anchored?
  (see prompt-injection-boundaries.md)
- Emitter direction: if this app is an MCP/agent server, are its exposed
  tool descriptions/responses free of coercive text, PII, internal IDs?

## LLM02:2026 Sensitive Information Disclosure

- PII kept out of prompts?
- API keys never in logs?
- Reasoning or trace output kept from users who must not see it?
- Conversation history retention policy?

## LLM03:2026 Excessive Agency (2025: LLM06)

- Tools scoped to least privilege (functionality, permissions, autonomy)?
- Destructive operations require confirmation?
- Rate limits on tool execution + task-wide cost budget?
- Every mutating sink gated on all reachable paths?
  (see agent-approval-gate.md)

## LLM04:2026 Supply Chain (2025: LLM03)

- API keys stored securely (not in code)?
- Model versions pinned, and the model artifact verified (hash or
  signature) before it is promoted?
- Fallback on provider outage?
- Third-party model, plugin, and MCP server provenance checked?
  (see agentic-mcp.md)

## LLM05:2026 Data and Model Poisoning (2025: LLM04)

- Pre-trained models: usually not directly relevant
- If fine-tuning: training-data integrity checked, and who can submit
  fine-tuning data or jobs?

## LLM06:2026 Unbounded Consumption (2025: LLM10)

- Rate limiting on LLM API calls?
- Token/output limits set?
- Timeout handling for LLM requests?
- Cost controls (max spend) across the subtask tree?
- Model-extraction / theft via bulk querying mitigated?

## LLM07:2026 Misinformation (2025: LLM09)

- LLM output validated (not blindly trusted)?
- Critical decisions and tool calls driven by model output gated on
  human review?
- Hallucination detection where possible (e.g. package names checked
  against the registry before install)?

## LLM08:2026 Hidden Context Exposure (2025: LLM07 System Prompt Leakage)

- No secrets, tokens, or connection strings in the system prompt, tool
  schemas, or retrieved policy text?
- Hidden context never the only control for authorization or content
  policy?
- Hidden context that leaks is treated as disclosed?

## LLM09:2026 Vector and Embedding Weaknesses (2025: LLM08)

- RAG sources access-controlled (no cross-tenant leakage)?
- Embedded/retrieved content treated as untrusted (indirect injection)?
- Poisoned-document detection where feasible?

## LLM10:2026 Improper Output Handling (2025: LLM05)

- LLM output validated before use in code/UI?
- No direct execution of LLM-generated code?
- Generated code reviewed like third-party code before it is merged?
- HTML/DOM output sanitized?
