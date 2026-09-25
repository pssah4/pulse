---
edition: "2025"
as-of: 2026-09-24
source: https://top10.owasp.org/2025/
authority: >
  This bundled list is the OFFLINE BASELINE. Phase 0 live-currency
  (SKILL.md) fetches the current published OWASP Top 10 from owasp.org,
  reconciles it against this file, and snapshots the edition actually
  used into the report. If the live step ran, its snapshot wins; if it
  did not (offline), this baseline applies and the report says so.
---

# OWASP Top 10 Checklist (edition 2025)

Cite the codes with the edition (`A03:2025`); the 2021 numbers differ.
The 2025 list folds SSRF into A01, widens the 2021 entry on components
with known vulnerabilities into A03 Software Supply Chain Failures, and
adds A10 for exceptional conditions.

## A01:2025 Broken Access Control (incl. SSRF)

- Missing authorization on endpoints
- Insecure Direct Object References (IDOR)
- Path traversal
- CORS misconfiguration
- Access to admin functions without a role check
- Server-Side Request Forgery (SSRF): variable outbound URL without
  allowlist (see cwe-patterns CWE-918)
- Identity/privilege claim taken from the request payload (Zero Trust breach)

## A02:2025 Security Misconfiguration

- Default credentials active
- Unnecessary features/ports open
- Missing security headers / weak CSP (see desktop-runtime.md)
- Verbose error messages to the user
- Directory listing enabled

## A03:2025 Software Supply Chain Failures

- Known CVEs in dependencies, outdated or unmaintained components
- No dependency inventory (SBOM) or monitoring (e.g. Dependabot)
- Components from untrusted registries or look-alike package names
- Unpinned lockfiles, lifecycle-script execution, unpinned GitHub Action tags
- Vendored / WASM / native deps that package audit does not see
- One person can change code and promote it to production unreviewed
  (see supply-chain.md)

## A04:2025 Cryptographic Failures

- Weak or outdated encryption algorithms
- Cleartext credentials in code or config
- Missing encryption at rest or in transit
- Weak password hashing (MD5, SHA1 without salt)
- Secrets not held in the OS keychain where available

## A05:2025 Injection

- SQL/NoSQL injection
- OS command injection
- LDAP injection
- XSS
- Template injection
- Second-order injection via un-anchored markers (see CWE-74/116)

## A06:2025 Insecure Design

- Missing threat models
- Architectural weaknesses (e.g. trust without validation)
- Missing rate limiting
- No defense in depth
- Ungated second path around an approval gate (see agent-approval-gate.md)

## A07:2025 Authentication Failures

- Weak session management
- Missing brute-force protection
- Credential stuffing possible
- Session tokens in the URL
- Non-timing-safe token comparison

## A08:2025 Software or Data Integrity Failures

- Insecure deserialization
- Missing signature check on updates
- CI/CD pipeline without integrity checks
- Insecure auto-update mechanisms
- Plugins, modules, or CDN scripts loaded without an integrity check

## A09:2025 Security Logging and Alerting Failures

- Missing security event logs
- Sensitive data in logs (tokens, passwords, tool results)
- No alerting on suspicious activity
- Logs not tamper-evident

## A10:2025 Mishandling of Exceptional Conditions

- Fail-open on error where it should fail-closed
- Swallowed exceptions hiding a security-relevant failure
- Partial state left committed after a cancel/abort (Esc != revert)
- Error objects dumped wholesale (leak) instead of a field allowlist
