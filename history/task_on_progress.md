# Current Task

## Goal

Lab-temp §512–526 on Vast GPU for Qwen3.8-27B; docs/report/hardware.

## Current status

Done for Vast path (2026-09-23).

- Disk cleaned; lab **9/9 PASS** (`vast-qwen38-27b-lab.jsonl`)
- Catalog `Qwen/Qwen3.8-27B` vast-ollama; reports + HARDWARE updated
- DSH compact: fails under 32k overflow; use ctx64k + matching DSH window

## Next exact step

When VPN stable: re-run full living-model matrix on llm-studio VPS
(`make test-models` / OCR / vision / cache) and merge into statistic report.
