# Training Fundamentals

## The five different activities

| Activity | Starting point | What changes | Best use |
|---|---|---|---|
| Training from scratch | Random weights | Every model weight | Learning mechanics or creating a foundation model with enormous data/compute |
| Continued pretraining | Pretrained weights | Usually every weight | Adapting language/domain patterns from large unlabeled corpora |
| Supervised fine-tuning | Pretrained weights | Every selected trainable weight | Teaching input/output behavior with labeled examples |
| LoRA fine-tuning | Pretrained weights | Small adapter matrices | Practical behavior adaptation with less memory and storage |
| RAG | Frozen model plus documents | No model weights | Supplying current, attributable knowledge at request time |

Quantization is not training. It stores or computes weights with fewer bits to
reduce memory and often improve inference speed. QLoRA combines a quantized base
model with trainable LoRA adapters, but common bitsandbytes QLoRA workflows are
GPU-oriented and are not the recommended first experiment on this CPU VPS.

## What one training step does

```text
examples
  -> tokenizer
  -> token IDs and attention masks
  -> model forward pass
  -> predicted next-token probabilities
  -> loss against expected next tokens
  -> backward pass computes gradients
  -> optimizer updates trainable parameters
  -> gradients are cleared
```

The loss is a differentiable measure of prediction error. The backward pass
computes how each trainable parameter contributed to that error. The optimizer
uses those gradients and the learning rate to change the parameters.

## Terms to understand before Qwen training

- **Token:** a unit from the tokenizer vocabulary, not necessarily a whole word.
- **Parameter:** a learned numeric value in the model.
- **Batch:** examples processed before one gradient calculation.
- **Gradient accumulation:** several small forward/backward passes combined
  before one optimizer update. It imitates a larger batch without holding that
  larger batch in RAM simultaneously.
- **Epoch:** one pass over all training examples.
- **Learning rate:** optimizer step size. Too high can destabilize training; too
  low can make the run ineffective.
- **Sequence length:** maximum tokens per example. Activation memory and compute
  rise rapidly as it increases.
- **Checkpoint:** saved training state used for recovery or later comparison.
- **Training loss:** fit on examples used for updates.
- **Validation loss:** fit on held-out examples. A rising validation loss while
  training loss falls is a common overfitting signal.

## Why not pretrain Qwen3.5-0.8B from scratch here?

Pretraining a useful foundation model requires a very large token corpus and a
large amount of accelerator compute. Four CPU cores are suitable for observing
the mechanics on a tiny educational model, but not for reproducing Qwen
pretraining. Calling a tiny local exercise “Qwen pretraining” would be
misleading.

Use this VPS for:

- tokenizer and data experiments;
- a tiny from-scratch model that teaches the algorithm;
- short Qwen3.5-0.8B LoRA runs on 20–100 examples;
- deterministic evaluation and checkpoint practice;
- RAG experiments where model weights stay unchanged.

## A useful mental model

Fine-tuning changes **behavior**. RAG supplies **knowledge**. Fine-tuning can
make the model emit the right schema, classification, tone, or workflow. RAG is
usually better for facts that change, must be cited, or come from private
documents. They can be combined: a LoRA-adapted model follows the desired
response format while RAG supplies current evidence.

