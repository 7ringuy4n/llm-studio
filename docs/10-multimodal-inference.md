# Qwen3.5 Multimodal Inference

Qwen3.5-0.8B accepts text and images through the same chat-completions endpoint.
This repository supports OpenAI-style `text` and `image_url` content parts. It
does not support video or audio.

## Security boundary

Only embedded `data:image/png;base64,...`, `data:image/jpeg;base64,...`, and
`data:image/webp;base64,...` values are accepted. Remote URLs and local paths
are rejected so an authenticated caller cannot make the VPS fetch internal
services or local files.

Per request:

- no more than two images;
- no more than 3 MiB decoded per image;
- no dimension above 2048 pixels;
- no more than eight content parts in one message;
- the HTTP body remains capped at 4 MiB.

Resize large screenshots before sending them. A smaller image is faster to
preprocess and consumes fewer visual tokens.

## OpenAI-compatible message shape

```json
{
  "model": "Qwen/Qwen3.5-0.8B",
  "messages": [
    {
      "role": "user",
      "content": [
        {
          "type": "image_url",
          "image_url": {
            "url": "data:image/png;base64,...",
            "detail": "low"
          }
        },
        {
          "type": "text",
          "text": "Describe the image and list any visible text."
        }
      ]
    }
  ],
  "max_tokens": 160,
  "temperature": 0.7,
  "top_p": 0.8,
  "top_k": 20,
  "enable_thinking": false
}
```

`detail` is accepted for OpenAI client compatibility, but the local processor
currently chooses its own image resizing policy.

## Postman exercises

Import the collection and VPN environment from `postman/`. The environment
contains a tiny sample image, so these requests run without public internet:

1. **Describe Image** — free-form captioning and color ordering.
2. **Extract Image as JSON** — structured visual output.
3. **Reason About Image** — visual reasoning with `enable_thinking=true`.
4. **Reject Remote Image URL** — verifies the SSRF defense returns HTTP 422.

Replace `sampleImageDataUrl` with your own complete data URL to test a
screenshot, diagram, document crop, or photograph.

## Prompt design

A useful vision prompt states:

- the observation task: describe, compare, count, classify, or transcribe;
- the output schema or fields;
- what to do when text is unreadable or evidence is uncertain;
- whether reasoning mode is required;
- a bounded answer length.

Do not ask the model to invent missing text. For OCR-like tasks, request
`null` or an `uncertain` field when a value cannot be read.

## Training boundary

The LoRA guide intentionally starts with text-only conversational examples. A
multimodal adapter requires paired image-text data, a collator that loads and
batches pixels, and an explicit decision about whether the vision encoder is
frozen. Do not treat the text-only LoRA recipe as a multimodal fine-tuning
pipeline.
