#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    rendered = subprocess.check_output(
        ["python3", str(ROOT / "scripts" / "models.py"), "dsh-config"],
        cwd=ROOT,
        text=True,
    )
    assert "inputModalities:" not in rendered

    catalog = json.loads((ROOT / "configs" / "models.json").read_text())
    models = catalog["models"]
    assert rendered.count("  - id: ") == len(models)
    assert rendered.count("    input: ") == len(models)

    for index, model in enumerate(models):
        start = rendered.index(f"  - id: {model['id']}\n")
        next_start = rendered.find("  - id: ", start + 1)
        block = rendered[start : next_start if next_start >= 0 else None]
        expected = "    input: [text, image]" if model["vision"] else "    input: [text]"
        assert expected in block, (model["id"], block)
        assert block.count("    input: ") == 1

    print("DSH model modality configuration regression passed")


if __name__ == "__main__":
    main()
