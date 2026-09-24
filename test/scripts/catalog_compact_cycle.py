#!/usr/bin/env python3
"""Catalog AUTO-compact cycle: DSH Standard + OpenCode for remaining models.

Skips OpenCode 9B/27B and DSH 9B (already PASS) unless --force.
Uses compact-lab ctx windows (32k/40k/64k) where catalog max is impractical.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "docs/perf-results"
SCRIPTS = ROOT / "test/scripts"
SUMMARY = RESULTS / "catalog-compact-cycle.jsonl"

# catalog_key, base, alias, ctx, reserved — small models first; 27B last (large pull)
MATRIX = [
    ("Qwen/Qwen3.5-0.8B", "qwen3.5:0.8b", "qwen3.5:0.8b-ctx32k", 32768, 8192),
    ("Qwen/Qwen3.5-2B", "qwen3.5:2b", "qwen3.5:2b-ctx32k", 32768, 8192),
    ("Qwen/Qwen3-1.7B", "qwen3:1.7b", "qwen3:1.7b-ctx32k", 32768, 8192),
    ("Qwen/Qwen3.5-4B", "qwen3.5:4b", "qwen3.5:4b-ctx32k", 32768, 8192),
    ("Qwen/Qwen3-8B", "qwen3:8b", "qwen3:8b-ctx40k", 40960, 10240),
    ("deepseek-ai/DeepSeek-R1-Distill-Qwen-7B", "deepseek-r1:7b", "deepseek-r1:7b-ctx64k", 65536, 16384),
    ("meta-llama/Llama-3.1-8B-Instruct", "llama3.1:8b", "llama3.1:8b-ctx64k", 65536, 16384),
    ("Qwen/Qwen3.8-27B", "qwen3.8:27b", "qwen3.8:27b-ctx64k", 65536, 16384),
]

SKIP_OC = {"Qwen/Qwen3.5-9B", "Qwen/Qwen3.8-27B", "Qwen/Qwen3.5-0.8B", "Qwen/Qwen3.5-2B"}
SKIP_DSH = {"Qwen/Qwen3.5-9B", "Qwen/Qwen3.5-0.8B", "Qwen/Qwen3.5-2B"}


def ssh(cmd: str, timeout: int = 7200) -> subprocess.CompletedProcess:
    host = os.environ.get("VAST_SSH_HOST", "root@50.217.254.165")
    port = os.environ.get("VAST_SSH_PORT", "40820")
    return subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=20", "-p", port, host, cmd],
        text=True,
        capture_output=True,
        timeout=timeout,
    )


def remote_ensure(base: str, alias: str, ctx: int) -> None:
    script = f"""
set -e
export OLLAMA_MODELS=/workspace/ollama/models
ollama list | awk '{{print $1}}' | grep -qx '{base}' || ollama pull '{base}'
if ! ollama list | awk '{{print $1}}' | grep -qx '{alias}'; then
  printf '%s\\n' 'FROM {base}' 'PARAMETER num_ctx {ctx}' > /tmp/Modelfile.lab
  ollama create '{alias}' -f /tmp/Modelfile.lab
fi
ollama list
curl -sS -m 180 http://127.0.0.1:11434/api/generate -d '{{"model":"{alias}","prompt":"Reply ONLY: OK","stream":false,"options":{{"num_predict":8}}}}' | head -c 300
echo
"""
    r = ssh(script, timeout=7200)
    print(r.stdout[-1500:] if r.stdout else "")
    if r.returncode != 0:
        print(r.stderr[-1000:])
        raise RuntimeError(f"ensure failed {alias}")


def remote_cleanup(*tags: str) -> None:
    lines = ["export OLLAMA_MODELS=/workspace/ollama/models"]
    for t in tags:
        lines.append(
            f"curl -sS http://127.0.0.1:11434/api/generate -d '{{\"model\":\"{t}\",\"keep_alive\":0}}' >/dev/null 2>&1 || true"
        )
        lines.append(f"ollama stop '{t}' 2>/dev/null || true")
        lines.append(f"ollama rm '{t}' 2>/dev/null || true")
    lines += [
        "sync; echo 3 > /proc/sys/vm/drop_caches 2>/dev/null || true",
        "ollama list || true",
        "nvidia-smi --query-gpu=memory.used --format=csv,noheader",
        "df -h /workspace | tail -1",
    ]
    r = ssh("\n".join(lines))
    print(r.stdout[-800:] if r.stdout else "")


def set_dsh_default(alias: str) -> None:
    p = Path.home() / ".dsh" / "settings.yaml"
    t = p.read_text()
    t2, n = re.subn(
        r"(agent-default-model:\n  provider: vast\n  model: )[^\n]+",
        rf"\g<1>{alias}",
        t,
        count=1,
    )
    if n != 1:
        # rebuild footer if corrupted
        idx = t.find("\nagent-default-model:")
        if idx < 0:
            raise RuntimeError("could not set agent-default-model")
        # keep everything after agent-presets if present
        rest = ""
        ap = t.find("\nagent-presets:")
        if ap > idx:
            rest = t[ap:]
        else:
            rest = """
agent-presets:
  default: standard
ui-theme:
  preference: dark
"""
        t2 = t[:idx] + f"""
agent-default-model:
  provider: vast
  model: {alias}
""" + rest
    p.write_text(t2)


def append(row: dict) -> None:
    SUMMARY.parent.mkdir(parents=True, exist_ok=True)
    with SUMMARY.open("a") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(json.dumps(row))


def run_opencode(key: str, alias: str, ctx: int, reserved: int) -> dict:
    lab = Path(f"/tmp/opencode-lab-{alias.replace(':', '_')}")
    if lab.exists():
        import shutil

        shutil.rmtree(lab)
    lab.mkdir(parents=True)
    out = RESULTS / f"opencode-compact-flood-{alias.replace(':', '_')}.jsonl"
    chunk = max(200, min(800, ctx // 50))
    turns = int(os.environ.get("OPENCODE_COMPACT_MAX_TURNS") or (25 if ctx <= 40960 else 40))
    env = os.environ.copy()
    env.update(
        {
            "OPENCODE_TEST_DIR": str(lab),
            "CATALOG_KEY": key,
            "OPENCODE_TAG": alias,
            "OPENCODE_CTX": str(ctx),
            "OPENCODE_MODEL": f"ollama/{alias}",
            "OPENCODE_COMPACT_CHUNK_REPS": str(chunk),
            "OPENCODE_COMPACT_MAX_TURNS": str(turns),
            "OPENCODE_RESERVED": str(reserved),
            "OPENCODE_OUTPUT_CAP": "512",
            "RESULTS": str(out),
        }
    )
    print(f"=== OpenCode {key} {alias} ctx={ctx} reserved={reserved} ===")
    subprocess.run(["bash", str(SCRIPTS / "opencode_compact_flood.sh")], env=env, check=False)
    # proof via export + token drop
    rows = []
    if out.exists():
        rows = [json.loads(l) for l in out.read_text().splitlines() if l.strip()]
    sid = None
    for r in rows:
        m = re.search(r"ses_[A-Za-z0-9]+", r.get("preview") or "")
        if m:
            sid = m.group(0)
            break
    if not sid and out.exists():
        m = re.search(r"ses_[A-Za-z0-9]+", out.read_text())
        sid = m.group(0) if m else None
    auto = any(r.get("saw_auto_compact") or r.get("token_drop") for r in rows)
    evidence = {}
    if sid:
        exp = Path(f"/tmp/oc-export-{alias.replace(':', '_')}.json")
        subprocess.run(
            ["opencode", "export", sid],
            cwd=str(lab),
            stdout=exp.open("w"),
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if exp.exists() and exp.stat().st_size > 20:
            data = json.loads(exp.read_text())
            for msg in data.get("messages", []):
                for part in msg.get("parts") or []:
                    if part.get("type") == "compaction" and part.get("auto") is True:
                        auto = True
                        evidence = {
                            "type": "compaction",
                            "auto": True,
                            "overflow": part.get("overflow"),
                        }
                info = msg.get("info") or {}
                if info.get("mode") == "compaction":
                    evidence["summary_finish"] = info.get("finish")
                    evidence["summary_tokens"] = info.get("tokens")
    # token drop fallback
    for i in range(1, len(rows)):
        a, b = rows[i - 1].get("tokens_total"), rows[i].get("tokens_total")
        if a and b and b < a - 8000:
            auto = True
            evidence.setdefault("token_drop", {"before": a, "after": b, "turn": rows[i].get("turn")})
    result = "PASS" if auto else "FAIL"
    proof = {
        "kind": "opencode-auto-compact-proof",
        "catalog_key": key,
        "model": f"ollama/{alias}",
        "test_context_tokens": ctx,
        "reserved": reserved,
        "result": result,
        "evidence": evidence,
    }
    (RESULTS / f"opencode-auto-compact-proof-{alias.replace(':', '_')}.json").write_text(
        json.dumps(proof, indent=2) + "\n"
    )
    row = {"agent": "opencode", "catalog_key": key, "alias": alias, "ctx": ctx, "result": result}
    append(row)
    return row


def run_dsh(key: str, alias: str, ctx: int) -> dict:
    set_dsh_default(alias)
    out = RESULTS / f"dsh-web-compact-flood-{alias.replace(':', '_')}.jsonl"
    url = Path("/tmp/dsh_url.txt").read_text().strip()
    env = os.environ.copy()
    env.update(
        {
            "DSH_WEB_URL": url,
            "DSH_COMPACT_CATALOG_KEY": key,
            "DSH_COMPACT_MODEL": alias,
            "DSH_COMPACT_MODE": "standard",
            "DSH_COMPACT_MAX_TURNS": "40",
            "DSH_COMPACT_CHUNK_REPS": str(400 if ctx > 40000 else 250),
            "DSH_COMPACT_FLOOD_CHARS": "12000",
            "DSH_COMPACT_CONTEXT_TOKENS": str(ctx),
            "RESULTS": str(out),
            "BSK_AUTO_START": "0",
        }
    )
    env.pop("BSK_SESSION", None)
    print(f"=== DSH {key} {alias} ctx={ctx} ===")
    # Patch META for alias/ctx: set env and rewrite CATALOG path via OPENCODE-style —
    # dsh script uses model_ctx; override by temporarily pointing SCRIPTS... 
    # Easiest: export fake via prepending PATH not available. Run with sed'd copy.
    flood_src = (SCRIPTS / "dsh_web_compact_flood.sh").read_text()
    flood_src = flood_src.replace(
        'META=$(python3 "$SCRIPTS/model_ctx.py" "$CATALOG_KEY")',
        f'META=\'{{"ollama_tag":"{alias}","test_context_tokens":{ctx},"chunk_reps":300,"max_turns":40}}\'',
    )
    flood_path = Path("/tmp/dsh_web_compact_flood_once.sh")
    flood_path.write_text(flood_src)
    subprocess.run(["timeout", "2400", "bash", str(flood_path)], env=env, check=False)

    rows = []
    if out.exists():
        rows = [json.loads(l) for l in out.read_text().splitlines() if l.strip()]
    auto = any(r.get("saw_auto_compact") for r in rows)
    detail = next((r.get("compact_detail") for r in rows if r.get("saw_auto_compact")), "")
    # session scan
    try:
        import glob

        sessions = sorted(
            glob.glob(str(Path.home() / ".dsh/sessions/**/session.v3.jsonl.zstd"), recursive=True),
            key=os.path.getmtime,
            reverse=True,
        )
        if sessions:
            raw = subprocess.check_output(["zstd", "-dc", sessions[0]], stderr=subprocess.DEVNULL)
            for line in raw.splitlines():
                if not line.strip():
                    continue
                o = json.loads(line)
                if o.get("type") == "compaction/start":
                    d = o.get("data") or {}
                    if not d.get("sourceCommandId"):
                        auto = True
                        detail = f"auto_turn={d.get('turn')}"
    except Exception as e:
        detail = f"{detail}|sess:{type(e).__name__}"
    result = "PASS" if auto else "FAIL"
    proof = {
        "kind": "dsh-auto-compact-proof",
        "catalog_key": key,
        "model": alias,
        "test_context_tokens": ctx,
        "result": result,
        "compact_detail": detail,
        "flood_rows": len(rows),
    }
    (RESULTS / f"dsh-auto-compact-proof-{alias.replace(':', '_')}.json").write_text(
        json.dumps(proof, indent=2) + "\n"
    )
    row = {
        "agent": "dsh",
        "catalog_key": key,
        "alias": alias,
        "ctx": ctx,
        "result": result,
        "detail": detail,
    }
    append(row)
    return row


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--agents", default="dsh,opencode", help="comma: dsh,opencode")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--only", default="", help="substring filter on catalog key")
    ap.add_argument(
        "--max-ctx",
        type=int,
        default=0,
        help="skip models with ctx above this (e.g. 40960 = small-ctx only)",
    )
    ap.add_argument(
        "--oc-turns",
        type=int,
        default=0,
        help="override OpenCode max turns (default: 25 if ctx<=40960 else 40)",
    )
    args = ap.parse_args()
    agents = {a.strip() for a in args.agents.split(",") if a.strip()}
    RESULTS.mkdir(parents=True, exist_ok=True)
    # Preserve prior PASS rows from earlier runs
    prior = SUMMARY.read_text() if SUMMARY.exists() else ""
    SUMMARY.write_text(prior if prior.endswith("\n") or not prior else prior + "\n")

    for key, base, alias, ctx, reserved in MATRIX:
        if args.only and args.only not in key and args.only not in alias:
            continue
        if args.max_ctx and ctx > args.max_ctx:
            print(f"skip (ctx>{args.max_ctx}) {key}")
            continue
        need_dsh = "dsh" in agents and (args.force or key not in SKIP_DSH)
        need_oc = "opencode" in agents and (args.force or key not in SKIP_OC)
        # Special: 27B OpenCode already PASS — skip OC unless force; still run DSH
        if key == "Qwen/Qwen3.8-27B" and not args.force:
            need_oc = False
            need_dsh = "dsh" in agents
        if not need_dsh and not need_oc:
            print(f"skip {key}")
            continue
        print(f"\n######## {key} ({alias}) ########")
        remote_ensure(base, alias, ctx)
        if need_dsh:
            try:
                run_dsh(key, alias, ctx)
            except Exception as e:
                append({"agent": "dsh", "catalog_key": key, "alias": alias, "result": "ERROR", "error": str(e)})
        if need_oc:
            try:
                # shorter floods for small ctx
                turns = args.oc_turns or (25 if ctx <= 40960 else 40)
                # temporarily monkey by env — run_opencode uses fixed turns; pass via env hack
                os.environ["OPENCODE_COMPACT_MAX_TURNS"] = str(turns)
                run_opencode(key, alias, ctx, reserved)
            except Exception as e:
                append(
                    {"agent": "opencode", "catalog_key": key, "alias": alias, "result": "ERROR", "error": str(e)}
                )
        remote_cleanup(alias, base)
        time.sleep(2)

    print("\n=== SUMMARY ===")
    print(SUMMARY.read_text())


if __name__ == "__main__":
    main()
