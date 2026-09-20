# Dataset Preparation

Data quality and evaluation design matter more than increasing epochs on a bad
dataset. Start narrow, explicit, and inspectable.

## Recommended format

Use conversational JSON Lines. Each line is one complete JSON object:

```json
{"messages":[{"role":"system","content":"Classify the request. Return JSON only."},{"role":"user","content":"Remind me tomorrow at 8 AM to back up the server."},{"role":"assistant","content":"{\"task_type\":\"create_schedule\"}"}]}
{"messages":[{"role":"system","content":"Classify the request. Return JSON only."},{"role":"user","content":"Find the current Ubuntu release notes."},{"role":"assistant","content":"{\"task_type\":\"search\"}"}]}
```

TRL supports conversational language-model and prompt-completion datasets. The
`messages` representation also lets the model tokenizer apply its own chat
template instead of manually inventing delimiters.

## First taxonomy

Keep the first problem small enough to evaluate exactly:

```text
normal
create_schedule
coding
tool
search
file
knowledge
unknown
```

Write a one-sentence definition and at least three positive and three confusing
negative examples for each class. If two humans cannot consistently choose a
label, the model will not learn a stable boundary.

## Split before tuning

For 50–100 initial examples:

- training: 70–80%;
- validation: 10–15%;
- test: 10–15%.

Stratify by task type. Put paraphrases, near-duplicates, and examples derived
from the same template in the same split. Otherwise the validation score will
measure memorization leakage rather than generalization.

Do not inspect and repeatedly edit the test set based on model mistakes. Use the
validation set during development and evaluate the test set only at milestones.

## Directory layout

```bash
export DATASET_DIR=/opt/data/llm-studio/datasets/hermes-intent-v1
mkdir -p "${DATASET_DIR}"
```

```text
hermes-intent-v1/
├── README.md
├── labels.json
├── train.jsonl
├── validation.jsonl
├── test.jsonl
└── SHA256SUMS
```

The dataset README should record its purpose, source, license/permission,
creation date, label definitions, exclusions, known bias, split method, and any
personal or confidential data review.

## Validate before training

Save the following as a temporary validator or adapt it into the future dataset
pipeline:

```python
import json
from collections import Counter
from pathlib import Path

root = Path("/opt/data/llm-studio/datasets/hermes-intent-v1")
seen = {}

for split in ("train", "validation", "test"):
    counts = Counter()
    path = root / f"{split}.jsonl"
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            record = json.loads(line)
            messages = record["messages"]
            assert [m["role"] for m in messages] == ["system", "user", "assistant"]
            assert all(isinstance(m["content"], str) and m["content"].strip() for m in messages)

            user_text = messages[1]["content"].strip()
            key = user_text.casefold()
            if key in seen:
                raise ValueError(f"duplicate across {seen[key]} and {split}:{line_number}")
            seen[key] = f"{split}:{line_number}"

            answer = json.loads(messages[2]["content"])
            assert set(answer) == {"task_type"}
            counts[answer["task_type"]] += 1
    print(split, sum(counts.values()), dict(sorted(counts.items())))
```

Run it before every experiment, then hash the dataset:

```bash
cd "${DATASET_DIR}"
sha256sum README.md labels.json train.jsonl validation.jsonl test.jsonl > SHA256SUMS
sha256sum --check SHA256SUMS
```

## Data security

- Do not train on API keys, tokens, passwords, production dumps, VPN profiles,
  private keys, personal records, or unreviewed logs.
- Assume memorization is possible even with a small adapter.
- Redact secrets before data enters version control or a model cache.
- Keep production data out of this educational lab unless a separate approval,
  retention policy, and deletion process exist.
- Treat downloaded datasets as untrusted input and review their license.

