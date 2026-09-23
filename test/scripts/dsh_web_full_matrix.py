#!/usr/bin/env python3
"""DSH web (BrowserSkill) matrix for lab-temp §511–533.

Drives the logged-in DSH web UI (not headless) across:
  modes: minimal | minimal-web | standard
  reasoning efforts: Default / off / low / medium / high (as exposed)
  models: catalog living models present in the model picker
  kinds: short | coding | compact-flood (standard only)

Requires: bsk daemon + extension connected; DSH web on http://127.0.0.1:8080
Progress: running test case N/M
Never prints API keys or Vast public host:port.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "perf-results" / "dsh-web-full-matrix.jsonl"
CATALOG = ROOT / "configs" / "models.json"
SID = os.environ.get("BSK_SESSION", "").strip()
BASE_URL = os.environ.get("DSH_WEB_URL", "http://127.0.0.1:8080")

# UI labels for catalog models (homelab + vast)
MODEL_LABELS = [
    "Qwen/Qwen3.5-0.8B",
    "Qwen3.5 2B",
    "Qwen3 8B Q4_K_M",
    "DeepSeek R1 Distill Qwen 7B Q4_K_M",
    "Llama 3.1 8B Instruct Q4_K_M",
    "qwen3.8:27b-ctx64k (Vast 64k)",
]

MODES = [
    ("minimal", r'@(e\d+) menuitem "Minimal mode '),
    ("minimal-web", r'@(e\d+) menuitem "Minimal \+ Web'),
    ("standard", r'@(e\d+) menuitem "Standard mode'),
]

EFFORTS = ["off", "low", "medium", "high", "Default"]  # tried in UI order of availability

CODING_PROMPT = (
    "Write a Python function `def add(a: int, b: int) -> int` that returns a+b. "
    "Reply with ONLY the function body line `return a + b` inside a one-line fenced "
    "python block. No explanation."
)

SHORT_PROMPT = "Reply with exactly: PONG. Do not use tools."


def bsk(*args: str, timeout: int = 120) -> str:
    env = os.environ.copy()
    env.setdefault("BSK_AUTO_START", "0")
    env.setdefault("BSK_HOME", str(Path.home() / ".bsk"))
    r = subprocess.run(
        ["bsk", *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )
    out = (r.stdout or "") + (r.stderr or "")
    if r.returncode != 0 and "ok" not in out.lower():
        raise RuntimeError(f"bsk {' '.join(args)} -> {r.returncode}: {out[:400]}")
    return out


def observe() -> str:
    return bsk("observe", "--session", SID)


def click(ref: str) -> None:
    bsk("click", ref if ref.startswith("@") else f"@{ref}", "--session", SID)


def fill(ref: str, value: str) -> None:
    bsk("fill", ref if ref.startswith("@") else f"@{ref}", "--value", value, "--session", SID)


def press(key: str) -> None:
    bsk("press", key, "--session", SID)


def find_ref(pattern: str, text: str | None = None) -> str | None:
    t = text if text is not None else observe()
    m = re.search(pattern, t)
    return m.group(1) if m else None


def ensure_session() -> None:
    global SID
    if SID:
        try:
            observe()
            return
        except Exception:
            SID = ""
    out = bsk("session", "start", "--json", "--no-focus")
    data = json.loads(out[out.find("{") : out.rfind("}") + 1])
    SID = data["session_id"]
    bsk("navigate", BASE_URL, "--session", SID)
    time.sleep(1.5)


def new_chat() -> None:
    try:
        press("Escape")
    except Exception:
        pass
    time.sleep(0.2)
    t = observe()
    refs = re.findall(r'@(e\d+) button "New session"', t)
    if refs:
        click(refs[0])
        time.sleep(1.0)


def set_mode(mode: str) -> str:
    try:
        press("Escape")
    except Exception:
        pass
    time.sleep(0.2)
    t = observe()
    btn = find_ref(r'@(e\d+) button "(?:Minimal|Standard|PTC|Creator) mode', t)
    if not btn:
        return "no-mode-btn"
    click(btn)
    time.sleep(0.6)
    t = observe()
    pat = dict(MODES)[mode]
    ref = find_ref(pat, t)
    if not ref:
        press("Escape")
        return "mode-item-missing"
    click(ref)
    time.sleep(1.0)
    t = observe()
    m = re.search(r'button "((?:Minimal|Standard|PTC|Creator)[^"]*mode[^"]*)"', t)
    return m.group(1) if m else "unknown"


def select_model(label: str) -> bool:
    try:
        press("Escape")
    except Exception:
        pass
    time.sleep(0.2)
    t = observe()
    btn = find_ref(r'@(e\d+) button "Select model', t)
    if not btn:
        return False
    click(btn)
    time.sleep(0.5)
    t = observe()
    if 'menuitem "Model ' in t:
        mref = find_ref(r'@(e\d+) menuitem "Model ', t)
        if mref:
            click(mref)
            time.sleep(0.6)
            t = observe()
    for pat in (
        rf'@(e\d+) menuitemradio "{re.escape(label)}"',
        rf'@(e\d+) menuitemradio "[^"]*{re.escape(label.split("(")[0].strip())}[^"]*"',
    ):
        ref = find_ref(pat, t)
        if ref:
            click(ref)
            time.sleep(0.7)
            try:
                press("Escape")
            except Exception:
                pass
            return True
    try:
        press("Escape")
    except Exception:
        pass
    return False


def select_effort(effort: str) -> str:
    """Open model menu → Effort → pick effort radio if present."""
    try:
        press("Escape")
    except Exception:
        pass
    time.sleep(0.2)
    t = observe()
    btn = find_ref(r'@(e\d+) button "Select model', t)
    if not btn:
        return "no-model-btn"
    click(btn)
    time.sleep(0.5)
    t = observe()
    eref = find_ref(r'@(e\d+) menuitem "Effort ', t)
    if not eref:
        try:
            press("Escape")
        except Exception:
            pass
        return "effort-menu-missing"
    click(eref)
    time.sleep(0.5)
    t = observe()
    # match case-insensitive label
    ref = None
    for line in t.splitlines():
        m = re.search(r'@(e\d+) menuitemradio "([^"]+)"', line)
        if not m:
            continue
        if m.group(2).lower() == effort.lower() or effort.lower() in m.group(2).lower():
            ref = m.group(1)
            break
    if not ref:
        try:
            press("Escape")
        except Exception:
            pass
        return "effort-missing"
    click(ref)
    time.sleep(0.5)
    try:
        press("Escape")
    except Exception:
        pass
    return f"set:{effort}"


def send_wait(msg: str, timeout: int = 240) -> dict:
    t = observe()
    box = find_ref(r'@(e\d+) textbox "Describe what you want', t)
    if not box:
        return {"ok": False, "error": "no-textbox"}
    fill(box, msg)
    time.sleep(0.3)
    t = observe()
    send = find_ref(r'@(e\d+) button "Send message"', t)
    if not send:
        return {"ok": False, "error": "no-send"}
    click(send)
    waited = 0
    last = ""
    while waited < timeout:
        time.sleep(2)
        waited += 2
        last = observe()
        if re.search(r'Stop|Generating|Thinking', last, re.I):
            continue
        if re.search(r'textbox .*\[empty\]', last) or re.search(
            r"PONG|return a \+ b|```|compact|CONTEXT|error|Error", last, re.I
        ):
            # prefer idle composer
            if not re.search(r"Stop generation|Stop$", last, re.I):
                break
    texts = re.findall(r'StaticText "([^"]{0,240})"', last)
    preview = " | ".join(texts[-12:])
    return {
        "ok": True,
        "wait_s": waited,
        "preview": preview[:600],
        "saw_compact_ui": bool(re.search(r"compact|summariz|compacted", last, re.I)),
        "saw_error": bool(re.search(r"CONTEXT_WINDOW|exceeded|Request failed", last, re.I)),
        "has_pong": "PONG" in preview,
        "has_return": bool(re.search(r"return a \+ b", preview)),
    }


def compact_flood() -> dict:
    """Push large paste to approach context window; look for compact UI."""
    filler = ("ops-note " * 400) * 40  # ~large paste
    return send_wait(
        "CONTEXT FLOOD for compact test. Ignore body; reply COMPACT_PROBE.\n\n" + filler,
        timeout=300,
    )


def main() -> None:
    ensure_session()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("")

    # Scope: modes × models × (short + coding) with effort Default first;
    # then effort sweep on vast+standard only to keep runtime bounded unless FULL=1.
    full = os.environ.get("DSH_MATRIX_FULL", "").strip() == "1"
    models = MODEL_LABELS if full else ["qwen3.8:27b-ctx64k (Vast 64k)", "Qwen/Qwen3.5-0.8B"]
    efforts = EFFORTS if full else ["Default", "off", "medium"]
    kinds = ["short", "coding"]

    plan: list[tuple] = []
    for mode, _ in MODES:
        for model in models:
            for effort in efforts:
                for kind in kinds:
                    plan.append((mode, model, effort, kind))
            if mode == "standard":
                plan.append((mode, model, "Default", "compact"))

    total = len(plan)
    n = 0
    rows = []

    for mode, model, effort, kind in plan:
        n += 1
        label = f"dsh-web/{mode}/{model}/{effort}/{kind}"
        print(f"running test case {n}/{total}: {label}", flush=True)
        new_chat()
        mode_now = set_mode(mode)
        selected = select_model(model)
        effort_now = select_effort(effort) if selected else "skip"
        t0 = time.time()
        if kind == "short":
            result = send_wait(SHORT_PROMPT)
            ok = bool(result.get("has_pong")) and not result.get("saw_error")
        elif kind == "coding":
            result = send_wait(CODING_PROMPT)
            ok = bool(result.get("has_return")) and not result.get("saw_error")
        else:
            result = compact_flood()
            ok = result.get("saw_compact_ui") or (
                not result.get("saw_error") and "COMPACT_PROBE" in (result.get("preview") or "")
            )
        row = {
            "n": n,
            "m": total,
            "mode": mode,
            "mode_now": mode_now,
            "model": model,
            "selected": selected,
            "effort": effort,
            "effort_now": effort_now,
            "kind": kind,
            "ok": ok and selected,
            "wall_s": round(time.time() - t0, 2),
            **{k: result.get(k) for k in result},
        }
        rows.append(row)
        with OUT.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    ok = sum(1 for r in rows if r.get("ok"))
    print(json.dumps({"wrote": str(OUT), "rows": len(rows), "ok": ok}, indent=2))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
