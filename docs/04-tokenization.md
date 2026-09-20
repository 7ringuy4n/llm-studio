# Tokenization Laboratory

Do this exercise before training. It reveals what the model actually receives,
where truncation happens, and how much padding or unnecessary system text costs.

Activate the training environment and cache paths from the environment guide:

```bash
export LLM_STUDIO_ROOT=/opt/data/llm-studio
source "${LLM_STUDIO_ROOT}/training/.venv/bin/activate"
export HF_HOME="${LLM_STUDIO_ROOT}/models/huggingface"
export HF_DATASETS_CACHE="${LLM_STUDIO_ROOT}/datasets/cache"
```

## Inspect one conversation

```python
from transformers import AutoProcessor

model_id = "Qwen/Qwen3.5-0.8B"
processor = AutoProcessor.from_pretrained(model_id)
tokenizer = processor.tokenizer

messages = [
    {"role": "system", "content": "Classify the request. Return JSON only."},
    {"role": "user", "content": "Remind me tomorrow at 8 AM to back up the server."},
    {"role": "assistant", "content": '{"task_type":"create_schedule"}'},
]

rendered = processor.apply_chat_template(
    messages,
    tokenize=False,
    add_generation_prompt=False,
    enable_thinking=False,
)
encoded = tokenizer(rendered, return_attention_mask=True)
tokens = tokenizer.convert_ids_to_tokens(encoded["input_ids"])

print("Rendered conversation:\n", rendered)
print("Token count:", len(encoded["input_ids"]))
print("Token IDs:", encoded["input_ids"])
print("Tokens:", tokens)
print("Attention mask:", encoded["attention_mask"])
```

Observe:

- words may split into several tokens;
- punctuation and JSON syntax consume tokens;
- Vietnamese and English text can have different token counts;
- the chat template adds control tokens not visible in the raw data;
- `enable_thinking=False` keeps this narrow classification task focused on the
  answer rather than Qwen reasoning output.

Do not manually add Qwen control tokens. Let the model tokenizer render the
conversation so training and inference use the same format.


Qwen3.5 is multimodal, so its chat template lives on the processor. For a
vision request, the processor also returns `pixel_values` and image-grid
metadata. Measure visual-token cost separately from the text-only dataset; do
not mix images into this first classification baseline.

## Measure the whole dataset

```python
from datasets import load_dataset
from transformers import AutoProcessor

model_id = "Qwen/Qwen3.5-0.8B"
data_file = "/opt/data/llm-studio/datasets/hermes-intent-v1/train.jsonl"
processor = AutoProcessor.from_pretrained(model_id)
tokenizer = processor.tokenizer
dataset = load_dataset("json", data_files=data_file, split="train")

lengths = []
for row in dataset:
    token_ids = processor.apply_chat_template(
        row["messages"],
        tokenize=True,
        add_generation_prompt=False,
        enable_thinking=False,
    )
    lengths.append(len(token_ids))

lengths.sort()
for percentile in (50, 90, 95, 100):
    index = min(len(lengths) - 1, round((percentile / 100) * (len(lengths) - 1)))
    print(f"p{percentile}: {lengths[index]} tokens")
```

Choose a maximum length that covers nearly all examples without being far above
the 95th percentile. For the first run, cap it at 256 even if a few examples
must be shortened. Investigate long examples instead of silently truncating
their expected answers.

## Understand labels

For causal language modeling, labels are the token IDs shifted conceptually by
one position: each position predicts the next token. Positions with label
`-100` are ignored by cross-entropy loss.

In a simple conversational SFT run, loss may be calculated across the complete
conversation. Completion-only or assistant-only loss can focus updates on the
answer, but assistant-only masking requires a chat template that emits an
assistant mask. Start with the documented default, verify it, and change one
behavior at a time.

## Completion checklist

- You can explain every field produced by the tokenizer.
- You know p50, p95, and maximum token length for every split.
- Training and inference use the same chat template and thinking setting.
- No target answer is truncated.
- You have recorded the tokenizer/model identifier and revision.

