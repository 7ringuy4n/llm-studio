# Postman

1. Connect with `tn.ovpn`.
2. Import `LLM-Studio.postman_collection.json` and `LLM-Studio-VPN.postman_environment.json` into Postman.
3. Select **LLM Studio - VPN** and set `apiKey` as a secret value. The key is stored on the VPS in `/home/tn/llm-studio/.env`.
4. Run the collection. It covers health, authentication, model discovery, normal and streaming chat completions, unknown models, and token-limit validation.

The API is intentionally reachable only through the VPN at `http://10.8.0.1:18080`. Never commit an environment export containing a real API key.
