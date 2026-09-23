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
    # local = load in llm-studio process; vast-ollama = catalog-only (GPU host)
    deployment: str = "local"
    ollama_model: str | None = None

    @property
    def download_repo_id(self) -> str:
        return self.repo_id or self.id

    @property
    def is_local(self) -> bool:
        return self.deployment == "local"


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
    for model in models:
        if model.deployment not in {"local", "vast-ollama"}:
            raise RuntimeError(f"unknown deployment for {model.id}: {model.deployment}")
        if model.deployment == "vast-ollama" and not model.ollama_model:
            raise RuntimeError(f"vast-ollama model {model.id} requires ollama_model")
    return models


CATALOG = _load_catalog()
BY_ID = {model.id: model for model in CATALOG}
BY_ALIAS = {model.alias: model for model in CATALOG}
LOCAL_CATALOG = tuple(model for model in CATALOG if model.is_local)


def allowed_models(raw: str) -> tuple[ModelSpec, ...]:
    requested = [item.strip() for item in raw.split(",") if item.strip()]
    unknown = [item for item in requested if item not in BY_ID]
    if unknown:
        raise RuntimeError(f"MODEL_ALLOWED_MODELS contains unknown IDs: {', '.join(unknown)}")
    selected = tuple(BY_ID[item] for item in requested)
    remote = [model.id for model in selected if not model.is_local]
    if remote:
        raise RuntimeError(
            "MODEL_ALLOWED_MODELS cannot include vast-ollama entries "
            f"(serve those on GPU/Ollama): {', '.join(remote)}"
        )
    return selected
