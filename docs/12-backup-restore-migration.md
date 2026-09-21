# Backup, restore, and clean-OS migration

Use this workflow to move LLM Studio to another machine or rebuild a clean OS
without losing trained assets. A backup contains the complete data tree:

- Hugging Face base-model and GGUF caches
- datasets and prepared training data
- checkpoints, full trained weights, and LoRA adapters
- evaluations, experiment records, RAG/vector data, and notebooks
- `.env`, including the API key and runtime/model selection
- the model catalog used when the backup was created

The backup contains secrets. Keep it on an encrypted disk or encrypted transfer,
restrict access, and do not commit it to Git.

## Create a consistent backup

Mount an external disk or remote filesystem with enough free space. Do not place
the backup inside `/opt/data/llm-studio`.

```bash
sudo ./scripts/backup_data.sh /mnt/llm-studio-backups
# or
sudo make backup BACKUP_DEST=/mnt/llm-studio-backups
```

The script stops only the `llm-studio` Compose services, uses `rsync -aHAX` to
preserve links/ownership/extended attributes, calculates SHA-256 for every
file, writes `BACKUP_COMPLETE` last, and restarts the stack only if it was
running before. Hermes remains running.

Inspect the result:

```bash
sudo du -sh /mnt/llm-studio-backups/llm-studio-backup-*
sudo cat /mnt/llm-studio-backups/llm-studio-backup-*/BACKUP_INFO
```

## Transfer to the new host

`rsync` can resume a large interrupted copy:

```bash
rsync -aHAX --info=progress2 \
  /mnt/llm-studio-backups/llm-studio-backup-YYYYMMDDTHHMMSSZ/ \
  new-host:/mnt/restore/llm-studio-backup-YYYYMMDDTHHMMSSZ/
```

Use SSH host keys and an encrypted transport. Do not expose the backup through a
public web server.

## Restore onto clean Ubuntu

1. Clone the same LLM Studio revision when possible.
2. Install Docker and `rsync` with `sudo ./scripts/install_docker.sh "$USER"`.
3. Do not run setup yet; restore into an empty data target and a clone without
   `.env`.
4. Run restore, then setup:

```bash
cd llm-studio
sudo ./scripts/restore_data.sh \
  /mnt/restore/llm-studio-backup-YYYYMMDDTHHMMSSZ \
  /opt/data/llm-studio
sudo LLM_STUDIO_BIND_ADDRESS=10.8.0.1 ./scripts/setup.sh
```

Restore refuses incomplete backups, checksum failures, non-empty target data,
or an existing `.env`. It maps restored ownership to the new sudo/login user.
Setup then validates configuration, rebuilds images, starts isolated Traefik,
and performs smoke tests.

## Verify after migration

```bash
docker compose ps
make models
make smoke
sudo du -sh /opt/data/llm-studio
```

Run one inference request for every model you intend to use. For trained models,
also compare a saved evaluation set and recorded metrics from the old host.

## Moving training work to another base model

Migration between hosts and compatibility between model architectures are
different problems:

- Datasets, prompts, evaluation cases, and experiment metadata are portable.
- A full checkpoint normally requires the same architecture and tokenizer.
- A LoRA adapter is tied to its exact base model/revision and target modules.
  Do not attach a Qwen adapter to Llama or a different-size Qwen checkpoint.
- To change base models, restore the dataset/evaluation assets, install the new
  base model, create a new training run, and compare it against the old run.
- Quantized GGUF inference files are not training checkpoints. Preserve the
  original full-precision checkpoint or adapter when future training matters.

Keep the old backup until the new host passes inference, evaluation, and a
restore drill. Removing a model with `make model-remove` deletes only that local
cache; it does not delete datasets or trained experiment directories.
