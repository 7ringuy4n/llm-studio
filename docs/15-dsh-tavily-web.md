# DSH + Tavily web search / fetch

LLM Studio only runs the model. **Web search and fetch are DSH plugins**: the
model emits `web_search` / `web_fetch` tool calls; DSH executes them against
Tavily and returns results to the model.

## What is installed (this machine)

| Piece | Role |
| --- | --- |
| `dsh-web-search-free` on **web** and **headless** profiles | Search + fetch providers; Tavily engine |
| `~/.dsh/settings.yaml` → `web-search-free` | `tavilyApiKey`, `providerOrder: [tavily]`, `enableSearch` / `enableFetch` |
| `~/.dsh/.credentials.yaml` → `refs.TAVILY_API_KEY` | Same key as a credential ref |
| Preset `minimal-web` under `~/.dsh/.agent-presets/` | Minimal persona **plus** `tool-web` |

Settings → Plugins → **Web Search Free** should show **Tavily** under call order
with Search + Fetch, and **Enable web_fetch** on.

## Modes (web UI)

| Mode | Web tools? | Notes |
| --- | --- | --- |
| **Standard** | Yes (`web_search`, `web_fetch`) | Prefer for research |
| **Minimal** | No | Shell only — cannot use Tavily tools |
| **Minimal + Web** | Yes | Custom preset: shell + Tavily-backed web tools |

`dsh --profile headless` always mounts host `tool-web` (presets do not strip it),
so headless is not a faithful test of Minimal vs Standard. Use the **web UI**
mode picker for that.

## One-time setup / after DSH upgrade

```bash
export PATH="$HOME/.local/node/bin:$PATH"
corepack enable && corepack prepare pnpm@latest --activate

dsh plugin --profile web add dsh-web-search-free
dsh plugin --profile headless add dsh-web-search-free   # optional CLI tests

# Key: Settings → Plugins → Web Search Free → Tavily
# or web-search-free.tavilyApiKey in ~/.dsh/settings.yaml
# and/or refs.TAVILY_API_KEY in ~/.dsh/.credentials.yaml

# Restart web
# (stop the existing dsh web process, then:)
dsh web --port 8080 --no-open
```

The plugin's `cordis.patch.yml` sets:

```yaml
- id: web
  config:
    searchProvider: web-search-free
    fetchProvider: web-search-free
```

Do **not** point `web-search-deepseek.baseURL` at `https://api.tavily.com` —
that provider speaks DeepSeek's API, not Tavily REST.

## Using it

1. Open DSH Web → workspace → mode **Standard** or **Minimal + Web**.
2. Model: **homelab** → prefer **Qwen3.5-2B** (best tool use on this VPS).
   **Qwen3.5-0.8B** can call tools but is flaky. **Qwen3-8B**, **R1-7B**, and
   **Llama-3.1-8B** often ignore `tool_choice` / fail to emit tools on CPU.
3. Prompts:

```text
Use web_search exactly once for: official OpenObserve GitHub repository.
Then reply with the top result URL only.
```

```text
Use web_fetch exactly once on https://example.com and quote the page title.
```

4. Trajectory should show: tool call → tool result (Sources / page text) → answer.

## Verify without the model

```bash
# Plugin provider path (same code DSH uses)
node --input-type=module -e '
import { tavilyProvider } from "file://$HOME/.dsh/profiles/web/node_modules/dsh-web-search-free/dist/providers/tavily.js";
const key = process.env.TAVILY_API_KEY;
console.log(await tavilyProvider.search("OpenObserve", key));
console.log(await tavilyProvider.fetch("https://example.com", key));
'
```

Or REST:

```bash
curl -sS https://api.tavily.com/search \
  -H 'Content-Type: application/json' \
  -d "{\"api_key\":\"$TAVILY_API_KEY\",\"query\":\"OpenObserve\",\"max_results\":2}"
```

## Model-side tool contract (llm-studio only)

```bash
cd ~/Documents/llm-studio && set -a && source .env && set +a
LLM_STUDIO_TEST_BASE_URL=http://10.8.0.1:18080/v1 \
LLM_STUDIO_TEST_MODEL=Qwen/Qwen3.5-2B \
  python3 test/scripts/web_search_contract.py
```

A pass means the model emitted `web_search`. Tavily execution is still DSH.

## Verified results (2026-09-23)

- DSH → Tavily **search** succeeded (tool result with Sources / OpenObserve GitHub)
  for **Qwen3.5-0.8B** and **Qwen3.5-2B** in headless sessions.
- Follow-up assistant turns after the tool often hit **503 / timeouts** on the
  CPU VPS when the API was busy — restart `make restart` on the VPS if needed.
- `web_search_contract`: **0.8B** and **2B** pass; **8B**, **R1-7B**, **Llama**
  return `finish_reason=stop` (no tool call) with `tool_choice=required`.
- Tavily **fetch** verified via the plugin provider (`/extract` → Example Domain).

## Later integration checklist

1. Keep the key out of git; use credentials refs or the Plugins card.
2. After `dsh` upgrades, re-add `dsh-web-search-free` if the bundle disappeared.
3. Prefer **Standard** or **Minimal + Web** for research; stock **Minimal** for
   shell-only tasks.
4. Pin `providerOrder: [tavily]`.
5. Outside DSH, call Tavily REST yourself — llm-studio will not call Tavily alone.
