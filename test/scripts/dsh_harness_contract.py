#!/usr/bin/env python3
"""DSH headless lab: minimal + standard presets × living models × short/long real-world prompts.

Rewrites ~/.dsh/settings.yaml agent-default-model and agent-presets.default, restores after.
Loads HOMELAB_API_KEY from credentials without printing it.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from prompt_builders import SHORT_REAL as SHORT_BASE, LONG_REAL_QUESTION, long_realworld_prompt  # noqa: E402

HOMELAB_MODELS = (
    "Qwen/Qwen3.5-0.8B",
    "Qwen/Qwen3.5-2B",
    "Qwen/Qwen3-8B",
    "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B",
    "meta-llama/Llama-3.1-8B-Instruct",
)
PRESETS = ("minimal", "standard")
SETTINGS = Path.home() / ".dsh" / "settings.yaml"
CREDENTIALS = Path.home() / ".dsh" / ".credentials.yaml"

SHORT_REAL = SHORT_BASE + " Do not use tools."
LONG_REAL = long_realworld_prompt(LONG_REAL_QUESTION, target_tokens=10000) + " Do not use tools."


def fail(message: str) -> None:
    raise SystemExit(f"dsh-harness contract failed: {message}")


def load_homelab_key() -> str:
    if os.environ.get("HOMELAB_API_KEY"):
        return os.environ["HOMELAB_API_KEY"]
    text = CREDENTIALS.read_text()
    match = re.search(r"(?m)^\s*HOMELAB_API_KEY:\s*(\S+)\s*$", text)
    if not match:
        fail("HOMELAB_API_KEY not found")
    return match.group(1).strip().strip("\"'")


def set_setting_model(model: str) -> None:
    text = SETTINGS.read_text()
    match = re.search(
        r"(?ms)^(agent-default-model:\n(?:  .*\n)*?  model:\s*)(.+?)(\n)",
        text,
    )
    if not match:
        fail("agent-default-model.model missing")
    SETTINGS.write_text(text[: match.start(2)] + model + text[match.end(2) :])


def set_preset(preset: str) -> None:
    text = SETTINGS.read_text()
    match = re.search(r"(?m)^(agent-presets:\n  default:\s*)(\S+)(\s*)$", text)
    if not match:
        # alternate formatting
        match = re.search(r"(?m)^(  default:\s*)(\S+)(\s*)$", text)
        if not match or "agent-presets" not in text[: match.start()]:
            fail("agent-presets.default missing")
    SETTINGS.write_text(text[: match.start(2)] + preset + text[match.end(2) :])


def run_headless(prompt: str, *, env: dict[str, str], timeout: int) -> tuple[str, int]:
    dsh = shutil.which("dsh")
    if not dsh:
        fail("`dsh` not on PATH")
    started = time.perf_counter()
    if len(prompt) > 1800:
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as handle:
            handle.write(prompt)
            path = handle.name
        try:
            proc = subprocess.run(
                ["bash", "-lc", f'{dsh} --profile headless "$(cat {path})"'],
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
            )
        finally:
            Path(path).unlink(missing_ok=True)
    else:
        proc = subprocess.run(
            [dsh, "--profile", "headless", prompt],
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
    wall = int((time.perf_counter() - started) * 1000)
    if proc.returncode != 0:
        fail(f"dsh exit {proc.returncode}: {(proc.stderr or proc.stdout or '')[-1000:]}")
    answer = (proc.stdout or "").strip()
    if not answer:
        fail(f"empty stdout; stderr={(proc.stderr or '')[-400:]}")
    return answer, wall


def main() -> None:
    models_raw = os.environ.get("DSH_HARNESS_MODELS", "").strip()
    models = (
        [m.strip() for m in models_raw.split(",") if m.strip()]
        if models_raw
        else list(HOMELAB_MODELS)
    )
    presets_raw = os.environ.get("DSH_HARNESS_PRESETS", "").strip()
    presets = (
        [p.strip() for p in presets_raw.split(",") if p.strip()]
        if presets_raw
        else list(PRESETS)
    )
    # Optional faster CI: DSH_HARNESS_QUICK=1 → only 0.8B
    if os.environ.get("DSH_HARNESS_QUICK") == "1":
        models = ["Qwen/Qwen3.5-0.8B"]

    timeout = int(os.environ.get("DSH_HARNESS_TIMEOUT_SECONDS", "600"))
    out_path = Path(__file__).resolve().parents[1] / "reports" / "dsh-harness-perf.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["HOMELAB_API_KEY"] = load_homelab_key()

    original_settings = SETTINGS.read_text()
    case_total = len(presets) * len(models) * 2
    case_n = 0
    results: list[dict] = []
    try:
        for preset in presets:
            set_preset(preset)
            for model in models:
                set_setting_model(model)
                for label, prompt in (("short_realworld", SHORT_REAL), ("long_realworld", LONG_REAL)):
                    case_n += 1
                    print(
                        f"running test case {case_n}/{case_total}: "
                        f"dsh:{preset}:{model}:{label}",
                        flush=True,
                    )
                    answer, wall = run_headless(prompt, env=env, timeout=timeout)
                    results.append(
                        {
                            "preset": preset,
                            "model": model,
                            "label": label,
                            "wall_ms": wall,
                            "answer_preview": answer[:160],
                            "chars_in": len(prompt),
                        }
                    )
                    print(f"  ok wall_ms={wall} preview={answer[:50]!r}", flush=True)
    finally:
        SETTINGS.write_text(original_settings)

    out_path.write_text(
        json.dumps(
            {
                "provider": "homelab",
                "presets": presets,
                "models": models,
                "results": results,
            },
            indent=2,
        )
        + "\n"
    )
    print(f"wrote {out_path}", flush=True)
    print(f"dsh-harness contract PASS: {case_total}/{case_total}", flush=True)


if __name__ == "__main__":
    try:
        main()
    except subprocess.TimeoutExpired as exc:
        fail(f"timeout: {exc}")
    except KeyboardInterrupt:
        sys.exit(130)
