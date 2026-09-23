#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / ".env"
CATALOG_FILE = ROOT / "configs" / "models.json"
COMPOSE = ["docker", "compose", "--project-name", "llm-studio", "--env-file", str(ENV_FILE), "--file", str(ROOT / "compose.yaml")]


def catalog() -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    for model in json.loads(CATALOG_FILE.read_text(encoding="utf-8"))["models"]:
        result[str(model["alias"])] = model
        result[str(model["id"])] = model
    return result


def select(value: str) -> dict[str, object]:
    try:
        return catalog()[value]
    except KeyError as exc:
        raise SystemExit(f"unknown model {value!r}; run scripts/models.py list") from exc


def read_env() -> dict[str, str]:
    values: dict[str, str] = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                values[key] = value
    return values


def update_env(updates: dict[str, str]) -> None:
    lines = ENV_FILE.read_text(encoding="utf-8").splitlines()
    seen: set[str] = set()
    output: list[str] = []
    for line in lines:
        key = line.split("=", 1)[0] if "=" in line and not line.startswith("#") else None
        if key in updates:
            output.append(f"{key}={updates[key]}")
            seen.add(key)
        else:
            output.append(line)
    output.extend(f"{key}={value}" for key, value in updates.items() if key not in seen)
    mode = ENV_FILE.stat().st_mode & 0o777
    fd, temporary = tempfile.mkstemp(prefix=".env.models.", dir=ROOT, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write("\n".join(output) + "\n")
        os.chmod(temporary, mode)
        os.replace(temporary, ENV_FILE)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def compose(*args: str) -> None:
    environment = read_env()
    command = [*COMPOSE, "--profile", environment.get("LLM_STUDIO_TRAEFIK_MODE", "local")]
    if environment.get("LLM_STUDIO_OBSERVABILITY_ENABLED", "false") == "true":
        command.extend(("--profile", "observability"))
    subprocess.run([*command, *args], check=True)


def cache_action(action: str, model: dict[str, object]) -> None:
    command = [
        "run", "--rm", "--no-deps", "api", "python", "-m", "api.model_cache",
        action, str(model.get("repo_id") or model["id"]), "--revision", str(model["revision"]),
    ]
    if model.get("gguf_filename"):
        command.extend(("--filename", str(model["gguf_filename"])))
    compose(*command)


def unique_models() -> list[dict[str, object]]:
    return list({str(model["id"]): model for model in catalog().values()}.values())


def list_models() -> None:
    active = read_env().get("MODEL_ID", "")
    for model in unique_models():
        marker = "*" if model["id"] == active else " "
        capabilities = ["vision" if model["vision"] else "text-only"]
        if model["reasoning"]:
            capabilities.append("reasoning")
        print(f"{marker} {model['alias']:<14} {model['id']:<24} {','.join(capabilities)} context={model['context_tokens']}")


def dsh_yaml() -> None:
    configured_gguf_context = int(
        read_env().get("MODEL_GGUF_CONTEXT_TOKENS", "32768")
    )
    print("models:")
    for model in unique_models():
        modalities = "[text, image]" if model["vision"] else "[text]"
        context_tokens = int(model["context_tokens"])
        if model["backend"] == "gguf":
            context_tokens = min(context_tokens, configured_gguf_context)
        print(
            f"  - id: {model['id']}\n"
            f"    name: {model['name']}\n"
            f"    contextWindow: {context_tokens}\n"
            f"    maxTokens: {int(model['max_new_tokens'])}\n"
            f"    input: {modalities}"
        )
        if model["reasoning"]:
            print("    reasoningEfforts:\n      'off': null")
            for effort in ("low", "medium", "high", "xhigh", "max"):
                print(f"      {effort}: {effort}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Install, select, and remove LLM Studio models")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list")
    install = sub.add_parser("install")
    install.add_argument("models", nargs="+")
    activate = sub.add_parser("activate")
    activate.add_argument("model")
    remove = sub.add_parser("remove")
    remove.add_argument("models", nargs="+")
    remove.add_argument("--force-active", action="store_true")
    sub.add_parser("dsh-config")
    args = parser.parse_args()
    if args.command == "list":
        list_models()
        return
    if args.command == "dsh-config":
        dsh_yaml()
        return
    if args.command == "install":
        for value in args.models:
            cache_action("install", select(value))
        return
    if args.command == "activate":
        model = select(args.model)
        cache_action("install", model)
        current_allowed = [
            item for item in read_env().get("MODEL_ALLOWED_MODELS", "").split(",") if item
        ]
        if str(model["id"]) not in current_allowed:
            current_allowed.append(str(model["id"]))
        update_env({"MODEL_ID": str(model["id"]), "MODEL_BACKEND": str(model["backend"]), "MODEL_REVISION": str(model["revision"]), "MODEL_CONTEXT_TOKENS": str(model["context_tokens"]), "MODEL_MAX_INPUT_TOKENS": str(model["context_tokens"]), "MODEL_DTYPE": str(model["dtype"]), "MODEL_ALLOWED_MODELS": ",".join(current_allowed)})
        compose("up", "--detach", "--force-recreate", "api")
        print(f"active model: {model['id']}")
        return
    active = read_env().get("MODEL_ID", "")
    selected = [select(value) for value in args.models]
    removing_active = any(model["id"] == active for model in selected)
    if removing_active:
        if not args.force_active:
            raise SystemExit("refusing to remove the active model; pass --force-active to stop the API first")
    # Stop the API even for an inactive catalog entry: the dynamically selected
    # resident model may differ from MODEL_ID and can still have cache files
    # memory-mapped.
    compose("stop", "api")
    for model in selected:
        cache_action("remove", model)
    removed_ids = {str(model["id"]) for model in selected}
    enabled = [
        item
        for item in read_env().get("MODEL_ALLOWED_MODELS", "").split(",")
        if item and item not in removed_ids
    ]
    update_env({"MODEL_ALLOWED_MODELS": ",".join(enabled)})
    if removing_active:
        print("active model removed; run model-activate for another model before starting the API")
    else:
        compose("up", "--detach", "api")


if __name__ == "__main__":
    main()
