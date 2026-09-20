# Postman

1. Connect with `tn.ovpn`.
2. Import `LLM-Studio.postman_collection.json` and `LLM-Studio-VPN.postman_environment.json` into Postman.
3. Select **LLM Studio - VPN** and set `apiKey` as a secret value. The key is stored on the VPS in `/home/tn/llm-studio/.env`.
4. Run the collection. It covers health, authentication, model discovery, normal and streaming chat completions, unknown models, token-limit validation, complex prompts, reasoning, natural communication, multimodal image analysis, concurrent requests, and client-managed conversation history.

The API is intentionally reachable only through the VPN at `http://10.8.0.1:18080`. Never commit an environment export containing a real API key.

## Advanced examples

- **Complex Structured Prompt** asks the model to analyze a production incident under multiple constraints. It saves the response and `X-Request-ID` into `lastAssistantReply` and `lastRequestId`.
- **Reasoning Mode - Qwen3.5 Thinking** enables Qwen3.5 thinking with `enable_thinking=true`. Thinking and the final answer share the completion token budget.
- **Natural Reply 1 - Helpful Support Response** applies the editable `communicationSkillPrompt` system prompt to produce a clear, warm, factual customer reply. It stores the exchange in `communicationHistory`.
- **Natural Reply 2 - Contextual Follow-up** replays that exchange and asks for a shorter, warmer revision without losing required facts.
- **Describe Image** identifies the panels in the embedded sample PNG.
- **Extract Image as JSON** demonstrates structured visual extraction.
- **Reason About Image** combines an image with Qwen3.5 thinking mode.
- **Concurrent Batch** launches `concurrentRequests` chat calls together with `pm.sendRequest`. With the default server limit of one generation, one request should succeed while the others receive `429` busy responses. Keep the batch between 2 and 4 requests.
- **Memory 1 - Start Conversation** saves the user and assistant messages into `conversationHistory`.
- **Memory 2 - Recall with History** sends that complete history back with a follow-up question and appends the new turn.
- **Memory 3 - Clear Client Memory** resets `conversationHistory` to `[]`.

The API is stateless: it does not remember earlier calls on the server. Conversation memory works only because the client resends previous messages. Postman also keeps a local request log in its **History** sidebar; that UI history is separate from model context.

To generate real parallel traffic using the Postman UI, open the collection Runner, choose **Performance**, and configure multiple virtual users. Start with two users because this VPS is intentionally configured for one simultaneous model generation.

## Using your own image

Replace `sampleImageDataUrl` in the selected Postman environment with a complete
`data:image/png;base64,...`, `data:image/jpeg;base64,...`, or
`data:image/webp;base64,...` value. Keep the prefix. The API intentionally
rejects `http://`, `https://`, `file://`, and local paths.

The included `postman/fixtures/three-color-panels.png` is the source of the
default embedded image. Reimport both the collection and environment after
updating the repository files.
