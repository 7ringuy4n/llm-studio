from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ModelSpec:
    alias: str
    id: str
    name: str
    backend: str
    revision: str
    context_tokens: int
    max_new_tokens: int
    dtype: str
    vision: bool
    reasoning: bool
    repo_id: str | None = None
    gguf_filename: str | None = None

    @property
    def download_repo_id(self) -> str:
        return self.repo_id or self.id


def _catalog_path() -> Path:
    configured = os.getenv("MODEL_CATALOG_PATH")
    return Path(configured) if configured else Path(__file__).resolve().parent.parent / "configs" / "models.json"


def _load_catalog() -> tuple[ModelSpec, ...]:
    payload = json.loads(_catalog_path().read_text(encoding="utf-8"))
    models = tuple(ModelSpec(**item) for item in payload["models"])
    ids = [model.id for model in models]
    aliases = [model.alias for model in models]
    if len(ids) != len(set(ids)) or len(aliases) != len(set(aliases)):
        raise RuntimeError("model catalog IDs and aliases must be unique")
    return models


CATALOG = _load_catalog()
BY_ID = {model.id: model for model in CATALOG}
BY_ALIAS = {model.alias: model for model in CATALOG}


def allowed_models(raw: str) -> tuple[ModelSpec, ...]:
    requested = [item.strip() for item in raw.split(",") if item.strip()]
    unknown = [item for item in requested if item not in BY_ID]
    if unknown:
        raise RuntimeError(f"MODEL_ALLOWED_MODELS contains unknown IDs: {', '.join(unknown)}")
    return tuple(BY_ID[item] for item in requested)
