# Qwen3-0.6B LoRA Training on CPU

This is the first practical Qwen fine-tuning experiment. It freezes the base
weights and trains small LoRA matrices on the query and value projections.

Expected reality: a short run on 50–100 examples can still take a long time on
four CPU cores. Begin with one epoch and 256 tokens. Do not increase dataset
size, sequence length, rank, and epochs at the same time.

## 1. Preflight

```bash
cd /home/tringuyen/Documents/llm-studio
make inspect
make stop
make resources
```

Activate the environment:

```bash
export LLM_STUDIO_ROOT=/opt/data/llm-studio
source "${LLM_STUDIO_ROOT}/training/.venv/bin/activate"
export HF_HOME="${LLM_STUDIO_ROOT}/models/huggingface"
export HF_DATASETS_CACHE="${LLM_STUDIO_ROOT}/datasets/cache"
export OMP_NUM_THREADS=3
export MKL_NUM_THREADS=3
export TOKENIZERS_PARALLELISM=false
```

Validate and hash the dataset as described in the dataset guide.

## 2. Establish a base-model result

Before training, run the test prompts through the unmodified base model and save
the raw outputs. This is the baseline; without it you cannot show that the
adapter improved anything.

Use deterministic generation for classification comparisons:

```python
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

model_id = "Qwen/Qwen3-0.6B"
tokenizer = AutoTokenizer.from_pretrained(model_id)
model = AutoModelForCausalLM.from_pretrained(
    model_id,
    dtype=torch.float32,
    low_cpu_mem_usage=True,
)
model.eval()

messages = [
    {"role": "system", "content": "Classify the request. Return JSON only."},
    {"role": "user", "content": "Remind me tomorrow at 8 AM to back up the server."},
]
prompt = tokenizer.apply_chat_template(
    messages,
    tokenize=False,
    add_generation_prompt=True,
    enable_thinking=False,
)
inputs = tokenizer(prompt, return_tensors="pt")
with torch.inference_mode():
    output = model.generate(**inputs, max_new_tokens=32, do_sample=False)
answer_ids = output[0, inputs["input_ids"].shape[-1] :]
print(tokenizer.decode(answer_ids, skip_special_tokens=True))
```

## 3. Inspect target modules

Before applying LoRA, verify the module names instead of assuming them:

```python
for name, module in model.named_modules():
    if name.endswith(("q_proj", "v_proj")):
        print(name, type(module).__name__)
```

If this prints no modules, stop and inspect the installed model architecture and
PEFT documentation. Do not silently train zero or unintended parameters.

## 4. First LoRA script

Save this as `/opt/data/llm-studio/training/train_lora.py`:

```python
import json
import os
import platform
import time
from pathlib import Path

import torch
from datasets import load_dataset
from peft import LoraConfig, TaskType
from transformers import AutoModelForCausalLM, AutoTokenizer, set_seed
from trl import SFTConfig, SFTTrainer

MODEL_ID = "Qwen/Qwen3-0.6B"
DATASET_DIR = Path("/opt/data/llm-studio/datasets/hermes-intent-v1")
RUN_ID = os.environ.get("RUN_ID", time.strftime("qwen3-lora-%Y%m%dT%H%M%SZ", time.gmtime()))
OUTPUT_DIR = Path("/opt/data/llm-studio/checkpoints") / RUN_ID
THREADS = int(os.environ.get("LLM_STUDIO_CPU_THREADS", "3"))

torch.set_num_threads(THREADS)
torch.set_num_interop_threads(1)
set_seed(42)

dataset = load_dataset(
    "json",
    data_files={
        "train": str(DATASET_DIR / "train.jsonl"),
        "validation": str(DATASET_DIR / "validation.jsonl"),
    },
)

tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
model = AutoModelForCausalLM.from_pretrained(
    MODEL_ID,
    dtype=torch.float32,
    low_cpu_mem_usage=True,
)
model.config.use_cache = False

targets = [
    name for name, _ in model.named_modules()
    if name.endswith(("q_proj", "v_proj"))
]
if not targets:
    raise RuntimeError("No q_proj/v_proj modules found; do not start training")

lora = LoraConfig(
    task_type=TaskType.CAUSAL_LM,
    r=8,
    lora_alpha=16,
    lora_dropout=0.05,
    bias="none",
    target_modules=["q_proj", "v_proj"],
)

config = SFTConfig(
    output_dir=str(OUTPUT_DIR),
    use_cpu=True,
    num_train_epochs=1,
    per_device_train_batch_size=1,
    per_device_eval_batch_size=1,
    gradient_accumulation_steps=8,
    learning_rate=1e-4,
    warmup_ratio=0.05,
    max_length=256,
    packing=False,
    dataloader_num_workers=0,
    logging_steps=1,
    eval_strategy="steps",
    eval_steps=10,
    save_strategy="steps",
    save_steps=10,
    save_total_limit=2,
    report_to="none",
    seed=42,
)

trainer = SFTTrainer(
    model=model,
    args=config,
    train_dataset=dataset["train"],
    eval_dataset=dataset["validation"],
    processing_class=tokenizer,
    peft_config=lora,
)
trainer.model.print_trainable_parameters()

metadata = {
    "run_id": RUN_ID,
    "model": MODEL_ID,
    "dataset_dir": str(DATASET_DIR),
    "seed": 42,
    "threads": THREADS,
    "python": platform.python_version(),
    "torch": torch.__version__,
    "config": config.to_dict(),
}
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
(OUTPUT_DIR / "run-metadata.json").write_text(
    json.dumps(metadata, indent=2, default=str), encoding="utf-8"
)

resume = os.environ.get("RESUME_FROM") or None
trainer.train(resume_from_checkpoint=resume)
metrics = trainer.evaluate()
trainer.save_model(str(OUTPUT_DIR / "adapter-final"))
tokenizer.save_pretrained(str(OUTPUT_DIR / "adapter-final"))
(OUTPUT_DIR / "final-metrics.json").write_text(
    json.dumps(metrics, indent=2), encoding="utf-8"
)
print("Saved adapter to", OUTPUT_DIR / "adapter-final")
```

Why these defaults:

- float32 is predictable on CPU; do not assume CPU bfloat16 acceleration;
- rank 8 keeps the adapter small;
- only query/value projections are adapted for the first experiment;
- batch 1 and 256 tokens bound activation memory;
- accumulation 8 gives an effective batch of 8 examples per optimizer update;
- one epoch creates a baseline before tuning hyperparameters;
- no worker processes avoids extra memory and CPU contention;
- only two checkpoints are retained.

## 5. Run and monitor

```bash
export RUN_ID=qwen3-lora-001
set -o pipefail
time python /opt/data/llm-studio/training/train_lora.py \
  2>&1 | tee "/opt/data/llm-studio/logs/${RUN_ID}.log"
```

In another terminal:

```bash
watch -n 2 free -h
```

```bash
watch -n 5 'du -sh /opt/data/llm-studio/checkpoints/* 2>/dev/null'
```

At startup, inspect `print_trainable_parameters()`. The trainable count should
be a small fraction of total parameters. If every base parameter is trainable,
stop: LoRA was not applied as intended.

## 6. Load the adapter

```python
import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer

base_id = "Qwen/Qwen3-0.6B"
adapter_path = "/opt/data/llm-studio/checkpoints/qwen3-lora-001/adapter-final"

tokenizer = AutoTokenizer.from_pretrained(adapter_path)
base = AutoModelForCausalLM.from_pretrained(
    base_id,
    dtype=torch.float32,
    low_cpu_mem_usage=True,
)
model = PeftModel.from_pretrained(base, adapter_path)
model.eval()
```

Generate with the same system prompt, chat template, `enable_thinking=False`,
and decoding parameters used for the baseline.

## 7. What not to do yet

- Do not merge the adapter until evaluation is complete; base plus adapter is
  easier to compare and revert.
- Do not use the test split to tune epochs or learning rate.
- Do not increase sequence length because the model supports a larger context;
  your data and RAM budget determine the practical value.
- Do not present lower training loss as proof of better behavior.
- Do not attempt full fine-tuning on this host as the first experiment.
- Do not assume bitsandbytes QLoRA is a practical CPU optimization.
