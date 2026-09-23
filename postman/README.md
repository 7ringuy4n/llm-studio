# Postman

1. Connect with `tn.ovpn`.
2. Import `LLM-Studio.postman_collection.json` and
   `LLM-Studio-VPN.postman_environment.json` into Postman.
3. Select **LLM Studio - VPN** and set `apiKey` as a secret value. The key is
   stored on the VPS in `/home/tn/llm-studio/.env`.
4. Run the collection. Coverage includes health, auth, model discovery, chat /
   streaming, **all living models short + ~10k-token long** prompts, real-world
   continuous turns, concurrency, vision (simple + complicated), GGUF coding,
   and validation negatives.
5. Every request automatically sends a persistent session/correlation/trace
   identity. Chat tests validate first/last-token time, cache hit percentage,
   input/output token counts, and `Server-Timing`.

The API is intentionally reachable only through the VPN at
`http://10.8.0.1:18080`. Never commit an environment export containing a real
API key.

## New folders (2026-09-23)

| Folder | Purpose |
|--------|---------|
| **All living models (short + ~10k long)** | Short real-world ops prompt + prerequest-built ~10k tool-trace long prompt for each living model |
| **Real-world continuous + concurrency** | Multi-turn follow-ups using `lastAssistantReply` (also use **Concurrent Batch** under Advanced) |
| **Vision - simple and complicated** | Mug / color panels + nature wallpaper / desk scene data URLs for Qwen3.5-0.8B and 2B |

Fixtures live under `postman/fixtures/` (`simple-*`, `complicated-*`,
`three-color-panels.png`). Environment keys:
`simpleImageDataUrl`, `panelsImageDataUrl`, `natureWallpaperDataUrl`,
`deskSceneDataUrl`, `shortRealworldPrompt`, `longRealworldQuestion`,
`longPromptTargetTokens` (default `10000`), `qwen35_2b_model`,
`livingModelsCsv`.

Long prompts are built in a **prerequest** script (not stored as a 40 KB
literal) so the collection stays editable.

## Advanced examples

- **Complex Structured Prompt** asks the model to analyze a production incident under multiple constraints. It saves the response and `X-Request-ID` into `lastAssistantReply` and `lastRequestId`.
- **Reasoning Mode - Qwen3.5 Thinking** enables Qwen3.5 thinking with `enable_thinking=true`. Thinking and the final answer share the completion token budget.
- **Natural Reply 1 / 2** — editable `communicationSkillPrompt` and follow-up.
- **Describe / Extract / Reason About Image** — original multimodal samples.
- **KV Cache** — generation cache + GGUF prefix warm/reuse.
- **Concurrent Batch** — `concurrentRequests` parallel chats behind the single generation slot.
- **Large GGUF Coding Models** — Qwen3 8B / DeepSeek R1 7B / Llama 3.1 8B coding prompts.
- **Memory 1–3** — client-managed conversation history.

The API is stateless: conversation memory works only because the client resends
previous messages.

After enabling OpenObserve, copy any response `X-Trace-ID` into the
`llm_studio_requests` log stream. See `docs/13-observability.md`.

## Using your own image

Replace `sampleImageDataUrl` / `simpleImageDataUrl` / `natureWallpaperDataUrl` /
`deskSceneDataUrl` with a complete `data:image/png;base64,...` (or jpeg/webp)
value. The API rejects remote `http(s)://` image URLs.

Reimport both the collection and environment after updating repository files.

## Related automation

| Make target | Script |
|-------------|--------|
| `make test-models` | All living models short + ~10k long (API) |
| `make test-realworld` | Real-world + continuous + concurrency |
| `make test-vision` | Vision fixtures under `test/fixtures/vision/` |
| `make test-dsh` | DSH headless minimal + standard |

Report: `docs/perf-results/model-statistic-report.md`.
