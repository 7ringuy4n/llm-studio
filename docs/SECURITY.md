# Security (llm-studio)

Isolation and credential rules for the inference API. Broader environment notes
live in [02-environment-and-safety.md](./02-environment-and-safety.md).

## Hard requirements

| Control | Requirement |
|---------|-------------|
| Auth | Bearer `LLM_STUDIO_API_KEY` (≥32 chars); never commit or log |
| Network | Prefer VPN / local Traefik; internet profile only when authorized |
| Isolation | No Hermes volumes/networks; no Docker socket mount |
| Container | read-only rootfs, `cap_drop`, `no-new-privileges` |
| Images | Embedded data-URL only (PNG/JPEG/WebP) — no remote URL fetch in API |
| Tools | Model may emit `web_search`; **DSH** executes search (Tavily), not llm-studio |
| Reports | Sanitize headers; no Bearer / passwords in `test/REPORT.md` or history |

## Operator checklist

1. Rotate API key if leaked; update `.env` only on the host.
2. After deploy, confirm compose still has isolation greps in `test/run.sh`.
3. OpenObserve UI access is operator-only; do not paste credentials into agent chat.
