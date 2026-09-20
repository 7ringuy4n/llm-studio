# Tiny Model From Scratch

This exercise teaches the mechanics of training without claiming that a useful
Qwen model is being pretrained. The model is a character-level bigram model: it
predicts the next character from the current character. It has no attention and
is intentionally small enough to train quickly on CPU.

## What it demonstrates

```text
raw text -> integer IDs -> batches -> forward pass -> cross-entropy loss
         -> backward pass -> optimizer update -> checkpoint -> generation
```

## Educational script

Create a UTF-8 text file containing non-confidential sample prose, then use this
script in an experiment directory:

```python
from pathlib import Path

import torch
import torch.nn as nn
from torch.nn import functional as F

torch.manual_seed(42)
torch.set_num_threads(3)

text = Path("tiny-corpus.txt").read_text(encoding="utf-8")
assert len(text) >= 1_000, "Use at least 1,000 characters for this exercise"

vocabulary = sorted(set(text))
to_id = {character: index for index, character in enumerate(vocabulary)}
to_character = {index: character for character, index in to_id.items()}
data = torch.tensor([to_id[character] for character in text], dtype=torch.long)

split = int(0.9 * len(data))
train_data = data[:split]
validation_data = data[split:]
block_size = 32
batch_size = 16


def get_batch(source):
    starts = torch.randint(len(source) - block_size, (batch_size,))
    inputs = torch.stack([source[i : i + block_size] for i in starts])
    targets = torch.stack([source[i + 1 : i + block_size + 1] for i in starts])
    return inputs, targets


class BigramLanguageModel(nn.Module):
    def __init__(self, vocabulary_size):
        super().__init__()
        self.table = nn.Embedding(vocabulary_size, vocabulary_size)

    def forward(self, input_ids, targets=None):
        logits = self.table(input_ids)
        loss = None
        if targets is not None:
            batch, time, channels = logits.shape
            loss = F.cross_entropy(logits.view(batch * time, channels), targets.view(batch * time))
        return logits, loss

    def generate(self, input_ids, new_tokens):
        for _ in range(new_tokens):
            logits, _ = self(input_ids)
            probabilities = F.softmax(logits[:, -1, :], dim=-1)
            next_id = torch.multinomial(probabilities, num_samples=1)
            input_ids = torch.cat((input_ids, next_id), dim=1)
        return input_ids


model = BigramLanguageModel(len(vocabulary))
optimizer = torch.optim.AdamW(model.parameters(), lr=1e-2)

for step in range(501):
    inputs, targets = get_batch(train_data)
    _, loss = model(inputs, targets)
    optimizer.zero_grad(set_to_none=True)
    loss.backward()
    optimizer.step()
    if step % 100 == 0:
        with torch.no_grad():
            validation_inputs, validation_targets = get_batch(validation_data)
            _, validation_loss = model(validation_inputs, validation_targets)
        print(step, "train", round(loss.item(), 4), "validation", round(validation_loss.item(), 4))

checkpoint = {
    "model_state": model.state_dict(),
    "optimizer_state": optimizer.state_dict(),
    "step": 500,
    "vocabulary": vocabulary,
}
torch.save(checkpoint, "tiny-checkpoint.pt")

start = torch.zeros((1, 1), dtype=torch.long)
generated = model.generate(start, new_tokens=300)[0].tolist()
print("".join(to_character[index] for index in generated))
```

## Experiments

Change only one variable per run:

1. learning rate: `1e-3`, `1e-2`, `1e-1`;
2. batch size: `4`, `16`, `64`;
3. corpus size;
4. number of steps;
5. random seed.

Record training and validation loss. A large learning rate may make loss
unstable; too many steps on a small corpus may improve training loss without
improving held-out text. The generated output will remain locally plausible but
incoherent because a bigram model has only one-character context.

## Questions you should be able to answer

- Which tensors contain inputs, targets, logits, and loss?
- Why is the target shifted by one character?
- What does `loss.backward()` create?
- Why clear gradients before the next step?
- Which checkpoint fields are needed to continue training?
- Why is this exercise not equivalent to pretraining Qwen3-0.6B?

