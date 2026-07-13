# Security Policy

WACE Light handles credentials (your LLM key, connector tokens) and runs a
governed engine, so security reports matter. Thank you for helping keep it safe.

## Reporting a vulnerability

**Please do not open a public issue for security problems.**

Report privately via GitHub's **[Private vulnerability reporting](https://github.com/pamiray-m/wace-light/security/advisories/new)**
(the "Report a vulnerability" button on the Security tab). Include:

- what the issue is and where (file / route / component),
- steps to reproduce or a proof of concept,
- the impact you see.

We'll acknowledge within a few days and keep you updated as we work a fix.
Please give us reasonable time to release a patch before any public disclosure.

## Scope

In scope: the backend engine (`src/aos/voundry`, `src/saib`, `src/llm`,
`src/core`), the API (`src/api/routes/wace.py`), and the frontend console.
Especially interested in: prompts reaching the LLM without SAIb scrubbing,
connector writes bypassing the approval gate, SSRF in connectors, auth/token
handling, and anything that exfiltrates a stored key.

Out of scope: issues that require a malicious local operator with your own
machine and credentials (this is a single-user, self-hosted tool).

## Supported versions

The latest release on `master` is supported. Older tags are not backported.
