# LLM Studio handbook

Project narrative and release notes:

- [CHANGELOG](CHANGELOG.md) — dated bullet changes
- [HISTORY](HISTORY.md) — decisions and real-world usage notes
- [HARDWARE](HARDWARE.md) — VPS sizing and API CPU quota
- [SECURITY](SECURITY.md) — isolation and credential rules
- Verification: [../test/README.md](../test/README.md) · [../test/REPORT.md](../test/REPORT.md)
- Agent rules: [../rule/AGENT_RULES.md](../rule/AGENT_RULES.md)
- Root-cause log: [../history/README.md](../history/README.md)

# AI Model Training Handbook

This handbook is the learning path for training and evaluating models in the
LLM Studio. It targets Ubuntu, 4 vCPU, 16 GB RAM, no GPU, and the official
`Qwen/Qwen3.5-0.8B` model.

Read the guides in this order:

1. [Fundamentals](01-fundamentals.md) — what training changes and how it differs
   from fine-tuning, LoRA, quantization, and RAG.
2. [Environment and safety](02-environment-and-safety.md) — protect Hermes and
   keep CPU, RAM, disk, and networking isolated.
3. [Dataset preparation](03-dataset-preparation.md) — design, validate, split,
   and version conversational JSONL data.
4. [Tokenization laboratory](04-tokenization.md) — inspect Qwen tokens, masks,
   truncation, and chat templates before training.
5. [Tiny model from scratch](05-tiny-model-from-scratch.md) — learn the complete
   forward/loss/backward/update loop without pretending to pretrain Qwen.
6. [Qwen3.5 LoRA training](06-qwen35-lora-training.md) — the first practical
   adapter training run on CPU.
7. [Evaluation and experiments](07-evaluation-and-experiments.md) — compare the
   base model and adapter with held-out data and reproducible metrics.
8. [Checkpoints and recovery](08-checkpoints-and-recovery.md) — resume, inspect,
   retain, and back up experiments.
9. [Troubleshooting](09-troubleshooting.md) — diagnose memory, speed, package,
   data, and quality failures.
10. [Multimodal inference](10-multimodal-inference.md) — send safe embedded
    images, design vision prompts, and understand the text-only training boundary.
11. [Clean Ubuntu and Traefik setup](11-clean-ubuntu-traefik-setup.md) — install
    Docker when absent and deploy an isolated proxy without touching Hermes.
12. [Backup, restore, and migration](12-backup-restore-migration.md) — preserve
    model caches, datasets, checkpoints, adapters, experiments, and secrets.
13. [Request tracing and the OpenObserve UI](13-observability.md) — inspect
    requests, responses, token/cache timing, IDs, IPs, and host resources.
14. [Web-search tool contract](14-web-search-test.md) — prove llm-studio emits
    `web_search` tool calls (model side only).
15. [DSH + Tavily web search/fetch](15-dsh-tavily-web.md) — wire
    `dsh-web-search-free` so DSH executes search/fetch via Tavily.
16. [CPU performance tuning](16-cpu-performance.md) — threads, batch, cache,
    3 vs 4 vCPU matrix vs the model-statistic baseline.
17. [Model statistic report](perf-results/model-statistic-report.md) — Markdown
    report shaped like `model-statistic 2.docx` (reasoning matrix, short/long
    all-models lab, accuracy/cost/cache notes).
18. [HTML performance tables](perf-results/model-statistic-tables.html) — sortable
    browser view of Model / Prompt / Tokens / Cache% / First / Last / Total.

The generated VPS inventory remains in [environment.md](environment.md).

## Recommended first milestone

Teach Qwen3.5-0.8B a narrow classification task:

```text
Input:  "Remind me tomorrow at 8 AM to back up the server."
Output: {"task_type":"create_schedule"}
```

Success means the held-out classification accuracy improves over the base
model, the output is valid JSON more often, and the result can be reproduced
from a recorded dataset version and configuration. Lower training loss alone is
not success.

## Current implementation boundary

The repository currently contains the secure inference API and setup layer. The
commands in these guides create a separate Python training environment under
`/opt/data/llm-studio/training`; they do not modify the API container or Hermes.
Stop the API before a training run so both workloads do not compete for memory.

## Official references

- [Qwen3.5-0.8B model repository](https://huggingface.co/Qwen/Qwen3.5-0.8B)
- [TRL SFTTrainer](https://huggingface.co/docs/trl/sft_trainer)
- [TRL dataset formats](https://huggingface.co/docs/trl/dataset_formats)
- [PEFT LoRA configuration](https://huggingface.co/docs/peft/en/package_reference/lora)
- [PEFT quantization guide](https://huggingface.co/docs/peft/developer_guides/quantization)

The training package versions in this handbook were selected on 2026-09-20.
Record installed versions for every experiment because these APIs evolve.
