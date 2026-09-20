# Checkpoints and Recovery

A LoRA checkpoint is not a complete standalone Qwen model. It normally contains
adapter weights and configuration plus trainer/optimizer state in step
checkpoints. Loading it requires the matching base model and tokenizer.

## What to retain

For a completed experiment retain:

- final adapter weights and `adapter_config.json`;
- tokenizer configuration used by the run;
- trainer state and final metrics;
- exact base model ID and revision;
- dataset hashes;
- package freeze;
- run configuration and logs.

Do not copy the cached base model into every experiment directory. Record its
identity and keep the shared cache under `/opt/data/llm-studio/models`.

## Step checkpoints

The first LoRA configuration saves every 10 optimizer steps and retains at most
two step checkpoints. With gradient accumulation of 8, an optimizer step occurs
after eight micro-batches, not after every example.

List available checkpoints:

```bash
find /opt/data/llm-studio/checkpoints/qwen35-lora-001 \
  -maxdepth 1 -type d -name 'checkpoint-*' -printf '%f\n' | sort -V
```

Resume by passing a specific directory:

```bash
export RUN_ID=qwen35-lora-001
export RESUME_FROM=/opt/data/llm-studio/checkpoints/qwen35-lora-001/checkpoint-10
python /opt/data/llm-studio/training/train_lora.py
```

Resume only with the same model, dataset, tokenizer, adapter structure, and core
training configuration. Starting from an incompatible optimizer state can fail
or invalidate the experiment.

## Verify artifacts

```bash
cd /opt/data/llm-studio/checkpoints/qwen35-lora-001
find . -type f -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS
sha256sum --check SHA256SUMS
```

Inspect the adapter configuration before loading it:

```bash
python -m json.tool \
  /opt/data/llm-studio/checkpoints/qwen35-lora-001/adapter-final/adapter_config.json
```

Confirm the base model reference, task type, rank, alpha, and targeted modules
match the run record.

## Backup

Create backups only inside the LLM Studio backup directory, then copy them to an
approved external destination using an existing administrative process:

```bash
backup_name="qwen35-lora-001-$(date -u +%Y%m%dT%H%M%SZ).tar.gz"
tar -C /opt/data/llm-studio/checkpoints \
  -czf "/opt/data/llm-studio/backups/${backup_name}" \
  qwen35-lora-001
sha256sum "/opt/data/llm-studio/backups/${backup_name}" \
  > "/opt/data/llm-studio/backups/${backup_name}.sha256"
```

Test recovery into a new experiment directory. A backup is unproven until it
has been restored and its hashes and adapter loading have been verified.

## Adapter merging

PEFT can merge an adapter into base weights for deployment, but merging is not
needed for learning or comparison. It creates a much larger artifact, makes it
easier to lose the base/adapter distinction, and requires sufficient RAM and
disk for the full model.

Keep base plus adapter separate until:

1. held-out evaluation is complete;
2. the exact adapter is approved;
3. the merged model has a clear deployment benefit;
4. disk and memory headroom have been measured;
5. the unmerged artifacts remain backed up.

