# VPS update from `main`

Use this after labs PASS and `main` has the merged release.

## Preconditions

- SSH as the deploy user on the llm-studio VPS
- Repo checked out under the usual path (example: `~/llm-studio` or `/opt/llm-studio`)
- VPN still reaches Traefik on `:18080` and OpenObserve on `:15080` after restart

Do **not** paste API keys or OpenObserve passwords into chat logs.

## Steps

```bash
cd /path/to/llm-studio
git fetch origin
git checkout main
git pull --ff-only origin main

# Review compose / .env.example deltas, then align local .env (never commit it)
diff -u .env.example .env || true

# Redeploy (script names follow this repo)
./scripts/setup.sh   # or your usual compose up path
# Example:
# docker compose pull
# docker compose up -d

# Confirm health
curl -sS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:18080/v1/models
# From VPN client:
# curl -sS -H "Authorization: Bearer $LLM_STUDIO_API_KEY" http://10.8.0.1:18080/v1/models
```

## Post-update checks

1. `configs/models.json` living models appear in `/v1/models`
2. Short chat on `Qwen/Qwen3.5-0.8B`
3. OpenObserve UI on `:15080` still ingesting
4. Keep CPU defaults **3.0 / 3** unless a new matrix says otherwise (`docs/16-cpu-performance.md`)

## Rollback

```bash
git log --oneline -5
git checkout <previous-main-sha>
# redeploy compose as above
```
