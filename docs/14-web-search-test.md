# Web-search tool test

LLM Studio exposes the OpenAI tool-calling contract; the calling harness owns
the actual network search. Test the two layers separately so a model-selection
problem is not mistaken for a network problem.

## 1. Test LLM Studio tool calling

On the server, load the API key without printing it and run the live contract
test:

```bash
cd ~/llm-studio
set -a
source .env
set +a
LLM_STUDIO_TEST_BASE_URL=http://10.8.0.1:18080/v1 \
  python3 tests/web_search_contract.py
```

A pass means the model returned one valid `web_search` function call with JSON
arguments and `finish_reason: tool_calls`. It does not claim that LLM Studio
performed the search.

## 2. Test DSH execution

Create a DSH session in **Standard mode** and send:

```text
You must use the web_search tool exactly once. Search for the official
OpenObserve GitHub repository, then reply with its repository URL only.
```

In **Trajectory**, confirm the sequence is assistant tool call, web-search tool
result, then final assistant answer. Minimal mode exposes only its persistent
shell, so it is not the correct mode for this test.

The 0.8B model can emit the tool-call schema, but its large Standard-mode prompt
is slow and tool selection is less reliable. Use Qwen3.5-2B or a 7B/8B
instruction model for regular coding-agent web search.
