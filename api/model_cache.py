from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from huggingface_hub import snapshot_download


def repo_path(cache_dir: Path, repo_id: str) -> Path:
    if "/" not in repo_id or repo_id.startswith(("/", ".")):
        raise ValueError("repository ID must use the owner/name form")
    owner, name = repo_id.split("/", 1)
    if not owner or not name or any(part in {".", ".."} for part in (owner, name)):
        raise ValueError("invalid repository ID")
    return cache_dir / "hub" / f"models--{owner}--{name}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage Hugging Face model cache entries")
    parser.add_argument("action", choices=("install", "remove", "status"))
    parser.add_argument("repo_id")
    parser.add_argument("--revision", default="main")
    parser.add_argument("--filename")
    parser.add_argument("--cache-dir", type=Path, default=Path("/data/models/huggingface"))
    args = parser.parse_args()
    target = repo_path(args.cache_dir, args.repo_id)
    if args.action == "status":
        print("installed" if target.is_dir() else "not-installed")
    elif args.action == "install":
        # Match the default $HF_HOME/hub location used by the runtime. Passing
        # HF_HOME itself as cache_dir creates an incompatible tree one level up.
        snapshot_download(
            repo_id=args.repo_id,
            revision=args.revision,
            cache_dir=args.cache_dir / "hub",
            allow_patterns=[args.filename] if args.filename else None,
        )
        print(f"installed {args.repo_id}")
    elif not target.is_dir():
        print(f"not installed: {args.repo_id}")
    else:
        hub = (args.cache_dir / "hub").resolve()
        resolved = target.resolve()
        if resolved.parent != hub:
            raise RuntimeError("refusing to remove a path outside the Hugging Face hub cache")
        shutil.rmtree(resolved)
        print(f"removed {args.repo_id}")


if __name__ == "__main__":
    main()
