# Evaluation and Experiments

Evaluation answers a specific question: did the adapter improve the target task
on examples that were not used for parameter updates?

## Compare the right systems

At minimum compare:

1. base `Qwen/Qwen3-0.6B`;
2. base model plus the LoRA adapter;
3. an explicit trivial baseline, such as always predicting the most frequent
   training label.

Use the same test records, system prompt, chat template, maximum output length,
and deterministic decoding for every model. For classification use
`do_sample=False`. Changing prompts between models invalidates the comparison.

## Metrics for the first task

Record these separately:

- **valid JSON rate:** percentage of outputs that parse as JSON;
- **schema-valid rate:** percentage with exactly the required fields/types;
- **accuracy:** percentage with the correct task type;
- **per-class recall:** how often each true class is found;
- **macro F1:** treats small and large classes equally;
- **no-answer/unknown accuracy:** resistance to inventing a confident class;
- **latency:** median and p95 seconds per example;
- **peak RSS:** highest resident memory during evaluation.

Do not turn malformed JSON into a correct label with generous string matching.
Malformed output is a real failure for a structured-output task.

## Prediction record

Write one JSON object per test example:

```json
{"id":"test-001","expected":"create_schedule","raw_output":"{\"task_type\":\"create_schedule\"}","parsed":"create_schedule","valid_json":true,"latency_seconds":4.82}
```

Keep raw output. It helps distinguish classification errors from formatting
errors and makes scoring auditable.

## Minimal strict scorer

```python
import json
from collections import Counter, defaultdict
from pathlib import Path

path = Path("predictions-adapter.jsonl")
total = 0
valid_json = 0
correct = 0
by_class = defaultdict(Counter)

with path.open(encoding="utf-8") as handle:
    for line in handle:
        row = json.loads(line)
        total += 1
        expected = row["expected"]
        try:
            payload = json.loads(row["raw_output"])
            if set(payload) != {"task_type"} or not isinstance(payload["task_type"], str):
                raise ValueError("invalid schema")
            predicted = payload["task_type"]
            valid_json += 1
        except (json.JSONDecodeError, ValueError, TypeError, KeyError):
            predicted = "__invalid__"

        by_class[expected]["total"] += 1
        if predicted == expected:
            correct += 1
            by_class[expected]["true_positive"] += 1
        by_class[predicted]["predicted"] += 1

print("examples", total)
print("valid_json_rate", valid_json / total if total else 0)
print("accuracy", correct / total if total else 0)

f1_values = []
for label in sorted(label for label in by_class if label != "__invalid__"):
    tp = by_class[label]["true_positive"]
    actual = by_class[label]["total"]
    predicted = by_class[label]["predicted"]
    precision = tp / predicted if predicted else 0
    recall = tp / actual if actual else 0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0
    f1_values.append(f1)
    print(label, {"precision": precision, "recall": recall, "f1": f1, "support": actual})
print("macro_f1", sum(f1_values) / len(f1_values) if f1_values else 0)
```

## Interpret loss correctly

Loss is useful for diagnosing optimization, but it is not the product metric.

| Observation | Likely interpretation |
|---|---|
| Training and validation loss both fall | Learning may be generalizing |
| Training loss falls, validation loss rises | Overfitting or split mismatch |
| Both losses remain flat | Learning rate, labels, masking, or adapter targets may be wrong |
| Loss becomes NaN | Numerical instability, corrupt data, or excessive learning rate |
| Loss improves but accuracy does not | Objective differs from the behavior metric |

Small validation sets are noisy. Report counts and confidence limitations, not
only a percentage with two decimal places.

## Experiment record

Create one directory per immutable run:

```text
/opt/data/llm-studio/experiments/qwen3-lora-001/
├── hypothesis.md
├── config.json
├── dataset-SHA256SUMS
├── requirements.txt
├── environment.txt
├── train.log
├── predictions-base.jsonl
├── predictions-adapter.jsonl
├── metrics-base.json
├── metrics-adapter.json
└── conclusion.md
```

The hypothesis should predict a measurable result before the run, for example:

> Training a rank-8 adapter for one epoch on 80 balanced intent examples will
> improve schema-valid test accuracy over the base model without reducing
> unknown-class recall below 70%.

Record:

- model ID and immutable revision/commit when available;
- tokenizer revision;
- dataset hashes and split method;
- random seed;
- package versions;
- LoRA rank, alpha, dropout, and target modules;
- sequence length, batch, accumulation, epochs, and learning rate;
- trainable and total parameter counts;
- wall-clock time, peak memory, and CPU utilization;
- all metrics and known invalid comparisons.

## Safe experiment sequence

After run 001 succeeds, change one variable per run:

| Run | Change | Question |
|---|---|---|
| 001 | rank 8, LR `1e-4`, 1 epoch | Does the pipeline work? |
| 002 | LR `5e-5` | Is the first learning rate too aggressive? |
| 003 | 2 epochs | Does more exposure improve validation behavior? |
| 004 | rank 4 | Can a smaller adapter retain quality? |
| 005 | rank 16 | Does additional capacity justify time and size? |
| 006 | sequence 512 | Do longer examples improve enough to justify cost? |

Do not compare two runs if their test set, prompt, tokenizer, or scoring logic
changed without explicitly treating that as a new evaluation version.

