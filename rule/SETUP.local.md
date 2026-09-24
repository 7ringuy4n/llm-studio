# Local / VPS setup notes (llm-studio)

Non-secret operator checklist. Secrets stay in `.env` on the host only.

## Paths

| Item | Value |
|------|-------|
| Repo | this tree |
| VPS data | `/opt/data/llm-studio` |
| API (VPN) | `http://10.8.0.1:18080` (Traefik → api:8000) |
| OpenObserve | host port **15080** (observability profile) |
| DSH (operator OS) | `http://127.0.0.1:8080` |

## Before deploy

1. Read `docs/CHANGELOG.md`, `docs/HISTORY.md`, and dated `history/` folders
2. Confirm `.env`: `LLM_STUDIO_API_CPUS=3.0`, `LLM_STUDIO_CPU_THREADS=3`
3. `make test` offline
4. Deploy from authorized branch; `make restart` / compose up with profiles

## After deploy

- `curl` health + `/v1/models` over VPN
- Short + long prompt contract (`test/scripts/prompt_length_contract.py`)
- Optional OpenObserve UI smoke (browser skill) — no secrets in chat
- Scan API/container logs for new ERROR/OOM patterns
