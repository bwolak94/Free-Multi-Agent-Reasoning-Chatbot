# Security Policy

## Supported Versions

| Version | Supported |
|---|---|
| `main` (latest) | Yes |
| Older branches | No |

We maintain only the latest version on `main`. Please ensure you are running the latest commit before reporting a vulnerability.

---

## Reporting a Vulnerability

**Do not open a public GitHub issue for security vulnerabilities.**

Report vulnerabilities privately via one of the following:

- **GitHub Private Vulnerability Reporting:** Use the [Security tab](https://github.com/your-org/free-multi-agent-reasoning-chatbot/security/advisories/new) → "Report a vulnerability".
- **Email:** security@your-domain.com (PGP key available on request).

### What to include

- Description of the vulnerability and potential impact.
- Steps to reproduce (proof of concept if available).
- Affected component (agent, API endpoint, policy engine, MCP loader, etc.).
- Suggested fix (optional).

### Response timeline

| Stage | Target |
|---|---|
| Initial acknowledgement | 48 hours |
| Triage and severity assessment | 5 business days |
| Fix or workaround | Depends on severity (see below) |
| Public disclosure | After fix is deployed |

### Severity and fix timeline

| Severity | Example | Target fix |
|---|---|---|
| Critical | RCE, auth bypass, secret exfiltration | 24–48 hours |
| High | Prompt injection leading to data leak, policy bypass | 7 days |
| Medium | HITL bypass, SSRF via web.fetch | 30 days |
| Low | Information disclosure, non-exploitable misconfiguration | Next release |

---

## Security Design Principles

This project is designed with the following security properties in mind:

### Prompt injection defence
- Tool outputs (web fetch, MCP results) are treated as **data**, not instructions.
- Policy Guard evaluates tool arguments deterministically — the LLM cannot override rules.
- High-risk tool calls always require human approval (HITL #2).

### MCP server sandboxing
- Stdio MCP servers run inside Docker containers with no host filesystem access.
- Each MCP server operates with the minimum required permissions.
- Tool names are namespaced (`mcp.<server>.<tool>`) to prevent collisions.

### Secret handling
- No secrets in source code or Docker images.
- Production credentials loaded from environment variables only.
- AWS access via EC2 instance role — no `AWS_ACCESS_KEY_ID` in any config.
- `.env` files are in `.gitignore` and must never be committed.

### Audit trail
- Every tool call is logged with `thread_id`, `run_id`, `tool_name`, `args`, and `result`.
- All LLM calls are traced in Langfuse with full argument visibility.
- Policy rule evaluations are logged deterministically.

### Network
- API is behind nginx with TLS (Let's Encrypt).
- EC2 security group: inbound SSH restricted to operator IP only.
- S3 bucket: private, no public access, accessed via presigned URLs only.

---

## Known Limitations

- Video and image generation backends (HF Spaces, Pollinations) are external services outside our control. Do not send sensitive data as generation prompts.
- Free LLM tier providers (Groq, Gemini, OpenRouter) process requests on their infrastructure. Treat all LLM input/output as potentially logged by the provider.
- This project is intended for single-user self-hosted deployment. It does not implement multi-tenant isolation or RBAC.
