# Training Troubleshooting

Diagnose one layer at a time: environment, data, tokenization, model loading,
adapter wiring, optimization, then evaluation.

## Process killed or `Killed` appears

Likely cause: the Linux OOM killer terminated Python.

Check:

```bash
free -h
journalctl -k --since '-30 min' | grep -Ei 'oom|out of memory|killed process'
```

Respond in this order:

1. ensure the AI API is stopped;
2. reduce sequence length from 512 to 256 or 128;
3. keep batch size at 1;
4. reduce the number of CPU threads to 2;
5. close unrelated lab processes;
6. verify no duplicate training process is running;
7. consider gradient checkpointing only after the simple run works, because it
   trades additional compute for activation memory.

Do not solve OOM by allowing the experiment to consume all swap; that can make
the VPS unresponsive and affect Hermes.

## Training is extremely slow

CPU LoRA is expected to be slow. First distinguish expected compute from a
configuration mistake:

```bash
ps -eo pid,%cpu,%mem,rss,etime,cmd --sort=-%cpu | head
```

Check that:

- exactly one training process exists;
- sequence length is 256;
- batch is 1;
- data loader workers are 0;
- the process uses approximately the intended three cores;
- swap is not continuously active;
- antivirus, backup, or indexing jobs are not contending for disk and CPU.

Measure examples/second before changing code. More threads can reduce
performance through contention and can interfere with other services.

## No `q_proj` or `v_proj` modules found

Stop. Possible causes are an unexpected model architecture, wrong model ID, or a
breaking library change.

```python
for name, module in model.named_modules():
    if "proj" in name.lower():
        print(name, type(module).__name__)
```

Select targets only after inspecting the actual model and current PEFT guidance.
Do not guess module names merely to bypass the guard.

## All parameters are trainable

LoRA was not applied as intended or the wrong model object is being trained.
Call:

```python
trainer.model.print_trainable_parameters()
```

The trainable fraction should be small. Stop the run before it allocates full
optimizer state for the base model.

## Loss is NaN or unstable

Check for:

- empty or malformed target messages;
- examples truncated before the assistant answer;
- an excessive learning rate;
- unsupported reduced precision on CPU;
- non-finite values introduced by a custom collator or preprocessing step.

Return to float32, `1e-4` or `5e-5`, sequence length 256, and the smallest valid
dataset. Reproduce the first bad step with the same seed.

## Training loss falls but validation gets worse

Likely overfitting or data leakage. Do not add epochs automatically. Inspect:

- duplicate/paraphrased examples across splits;
- class imbalance;
- inconsistent labels;
- templated wording that lets the model memorize shortcuts;
- whether the validation set covers the same task but genuinely new phrasing.

Prefer better examples and clearer labels before a larger LoRA rank.

## Adapter outputs prose instead of JSON

Measure this as a schema failure. Then verify:

- every training assistant response is valid JSON with one canonical schema;
- the system prompt is identical in training and evaluation;
- no examples contain Markdown fences around JSON;
- output length is sufficient but not so large that the model continues talking;
- deterministic decoding is used for evaluation.

More training cannot repair conflicting output formats in the dataset.

## Package/API errors after an upgrade

Do not patch the experiment environment in place. Compare:

```bash
python -m pip freeze
python -m pip check
```

Recreate a new virtual environment using the saved requirements file and rerun a
small smoke experiment. Treat package upgrades as a new environment version.

## Model download fails

Check free disk, DNS, outbound HTTPS, Hugging Face availability, and cache
permissions. Keep the cache inside `/opt/data/llm-studio/models/huggingface`.

Do not disable TLS verification or paste access tokens into scripts. Public Qwen
weights normally do not require a token. If a proxy or mirror is required, use
the VPS's approved administrative configuration.

## Checkpoint will not resume

Compare the checkpoint's trainer state and adapter configuration with the new
run. Common causes include changed dataset length, model revision, LoRA rank,
target modules, package versions, or a partial checkpoint caused by full disk.

If compatibility is uncertain, load only the completed adapter for a new run
and record that as continued adapter training—not a byte-for-byte resume.

## Before asking for help

Collect without including secrets or training examples:

```text
OS and kernel
CPU/RAM/free disk
package versions
model ID and revision
dataset sizes and hashes
LoRA configuration
sequence length/batch/accumulation
last 100 sanitized log lines
peak RAM and elapsed time
exact error traceback
```

