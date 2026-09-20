# Environment and Safety

Training is the most resource-intensive workload in this project. Treat host
inspection and isolation as part of the experiment, not as optional operations.

## Before every first run on a VPS

From the repository root:

```bash
make inspect
make resources
```

Review `docs/environment.md`. Confirm:

- the OS, CPU count, RAM, and free disk match expectations;
- existing Hermes containers are healthy;
- the OpenVPN interface and private address are understood;
- no LLM Studio path overlaps a Hermes mount;
- at least 10 GB remains free after expected model and checkpoint storage;
- no production-like service is already under memory pressure.

## Do not train beside the API process

The API container can reserve several gigabytes while Qwen is loaded. Stop only
the LLM Studio API before training:

```bash
make stop
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Image}}'
```

Do not stop, restart, inspect secrets from, or change Hermes containers. After
training, restart the API with:

```bash
make start
make smoke
```

## Training directories

Use only the dedicated data root:

```text
/opt/data/llm-studio/
├── datasets/
├── training/
├── checkpoints/
├── models/
├── experiments/
├── logs/
└── backups/
```

Never mount `/opt`, `/opt/assistant`, a Hermes volume, or the Docker socket into
a training process.

## CPU and memory guardrails

Start with three threads so one vCPU remains available for the OS and existing
services:

```bash
export OMP_NUM_THREADS=3
export MKL_NUM_THREADS=3
export TOKENIZERS_PARALLELISM=false
```

Initial limits:

| Setting | First run |
|---|---:|
| Sequence length | 256 tokens |
| Per-device batch | 1 |
| Gradient accumulation | 8 |
| Epochs | 1 |
| Data loader workers | 0 |
| LoRA rank | 8 |
| Checkpoints retained | 2 |

In another terminal, monitor:

```bash
watch -n 2 free -h
```

```bash
watch -n 2 'ps -eo pid,ppid,%cpu,%mem,rss,etime,cmd --sort=-rss | head -n 15'
```

Stop the run if swap grows continuously, available RAM approaches zero, Hermes
latency changes materially, or the machine becomes difficult to administer.

## Create the isolated training environment

Run this as the normal LLM Studio operator, not as root:

```bash
export LLM_STUDIO_ROOT=/opt/data/llm-studio
python3 -m venv "${LLM_STUDIO_ROOT}/training/.venv"
source "${LLM_STUDIO_ROOT}/training/.venv/bin/activate"
python -m pip install --upgrade pip setuptools wheel
```

Install a known package set:

```bash
python -m pip install \
  --extra-index-url https://download.pytorch.org/whl/cpu \
  'torch==2.7.1+cpu' \
  'torchvision==0.22.1+cpu'
```

```bash
python -m pip install \
  'transformers==5.17.0' \
  'datasets==5.0.1' \
  'peft==0.21.0' \
  'trl==1.13.0' \
  'accelerate==1.15.0' \
  'pillow==11.3.0' \
  sentencepiece
```

Keep caches inside the LLM Studio:

```bash
export HF_HOME="${LLM_STUDIO_ROOT}/models/huggingface"
export HF_DATASETS_CACHE="${LLM_STUDIO_ROOT}/datasets/cache"
mkdir -p "${HF_HOME}" "${HF_DATASETS_CACHE}"
```

Verify and record the environment:

```bash
python - <<'PY'
import accelerate
import datasets
import peft
import torch
import transformers
import trl

print("torch", torch.__version__)
print("transformers", transformers.__version__)
print("datasets", datasets.__version__)
print("peft", peft.__version__)
print("trl", trl.__version__)
print("accelerate", accelerate.__version__)
print("CUDA available", torch.cuda.is_available())
PY
```

```bash
python -m pip freeze > "${LLM_STUDIO_ROOT}/experiments/requirements-$(date -u +%Y%m%dT%H%M%SZ).txt"
```

Expected: `CUDA available False`. If package resolution changes later, use the
saved requirements file to reproduce the experiment instead of silently
upgrading mid-series.

