# Clean Ubuntu setup with isolated Traefik

This procedure installs LLM Studio from scratch on a clean Ubuntu VPS, including
Docker CE, Docker Compose v2, the model API, and a dedicated Traefik proxy. It
does not join, restart, reconfigure, or reuse any Hermes Assistant resource.

## Isolation contract

LLM Studio owns only these resources:

- Compose project `llm-studio`
- containers `llm-studio-api` and exactly one of
  `llm-studio-traefik-local` / `llm-studio-traefik-internet`
- network `llm-studio-net`
- image `llm-studio-api:local`
- data root `/opt/data/llm-studio`
- listener `127.0.0.1:18080` by default, or one explicit private/VPN IP

Its Traefik reads only `configs/traefik`; it does not mount the Docker socket.
The API publishes no host port. Only LLM Studio Traefik publishes the selected
listener. Hermes container names, networks, volumes, files, and ports are not
referenced. Never rename these resources to match a Hermes resource.
Optional observability uses `llm-studio-openobserve` and
`llm-studio-otel-collector` on the same isolated network without a Docker
socket.

## 1. Prepare the host

Log in as a normal sudo-capable user:

```bash
sudo apt-get update
sudo apt-get install --yes ca-certificates curl git make
git clone git@github.com:7ringuy4n/llm-studio.git
cd llm-studio
```

Use the HTTPS clone URL if SSH keys are not configured.

## 2. Install Docker only when absent

```bash
sudo ./scripts/install_docker.sh "$USER"
```

The installer uses Docker's official APT repository. If Engine and Compose v2
already work, it leaves them unchanged. It does not edit `daemon.json`, firewall
rules, Docker networks, volumes, or containers. Reconnect the SSH session after
installation, then verify:

```bash
docker --version
docker compose version
docker ps
```

Existing Hermes containers should remain unchanged.

## 3. Choose a private listener

Keep `127.0.0.1:18080` for local or SSH-tunnel access. For OpenVPN, locate the
server VPN address:

```bash
ip -brief address
sudo ss -ltnp | grep ':18080' || true
```

Use the exact VPN address, such as `10.8.0.1`. Pick another high port if it is
already occupied. Setup rejects wildcard/public addresses, missing local
addresses, foreign `llm-studio` resources, and port conflicts.

## 4. Validate and deploy

```bash
make test
sudo LLM_STUDIO_BIND_ADDRESS=10.8.0.1 \
  LLM_STUDIO_PORT=18080 \
  ./scripts/setup.sh
```

For local-only access, omit the two environment assignments. Setup generates a
strong API key in `.env` with mode `0600`, creates the isolated data tree,
builds the API, downloads configured preload models, starts API plus Traefik,
and runs authenticated smoke tests. Re-running setup preserves key and data.

For public HTTPS instead of local/VPN access, first point a DNS A/AAAA record at
the VPS and confirm ports 80 and 443 are free. Then run:

```bash
sudo LLM_STUDIO_TRAEFIK_MODE=internet \
  LLM_STUDIO_PUBLIC_DOMAIN=llm.example.com \
  LLM_STUDIO_ACME_EMAIL=admin@example.com \
  ./scripts/setup.sh
```

Internet mode binds public ports 80/443 and obtains a Let's Encrypt certificate.
It refuses occupied ports, so it cannot silently take Hermes Traefik's listener.
If Hermes already owns 80/443, keep LLM Studio in local/VPN mode or deliberately
configure routing in the existing proxy as a separate, reviewed change.

## 5. Verify health and isolation

```bash
docker compose ps
docker network inspect llm-studio-net
curl --fail http://10.8.0.1:18080/health
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
docker network ls
```

Use `127.0.0.1` in the health URL for a local-only deployment. Traefik allows
long coding-agent responses, while API-key authentication remains enforced on
every `/v1/*` endpoint.

Enable the private monitoring UI only after the API works:

```bash
make observability-up
```

See [Request tracing and the OpenObserve UI](13-observability.md). This listener
defaults to `127.0.0.1:15080` even when the API is in public mode.

## 6. Add or remove models

```bash
make models
make model-install MODEL=qwen3-8b
make model-activate MODEL=qwen3-8b
make model-remove MODEL=llama31-8b
```

The large choices `qwen3-8b`, `deepseek-r1-7b`, and `llama31-8b` are Q4 GGUF
files. They remain on disk, but only one model is resident in RAM. The resident
model unloads after one idle hour. Compose intentionally has no RAM ceiling.

## Recovery rules on a shared host

```bash
docker compose ps
docker compose logs --tail 100 api traefik
docker compose up --detach --force-recreate
```

These commands are scoped by the repository's Compose project. Do not use
global cleanup commands such as `docker system prune` on a host shared with
Hermes.
