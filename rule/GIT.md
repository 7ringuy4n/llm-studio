# Recommended Git workflow (llm-studio)

Adapted from Work/rule `GIT.md` for this repository.

## Core rule

**Develop on `develop` first. Merge to `main` only after it passes.**

| Branch | Meaning |
|--------|---------|
| **`develop`** | Integration branch — new work lands and is tested first |
| **`main`** | Production-ready / VPS deploy source after `develop` passes |
| **`feature/*` / `fix/*`** | Branched from `origin/develop` |
| **`release/*`** | Optional carrier for promoting passing `develop` → `main` |

```text
feature/* ──MR──> develop ──(pass: make test / authorized live)──> release/* ──MR──> main
```

### Mandatory

- Fetch and rebase onto the correct remote base before implementing or
  opening an MR.
- Never open, merge, or push an MR without explicit user permission in
  the current conversation.
- Never force-push `main` / `develop`.
- Do not commit secrets (`.env`, API keys, SSH passwords).
