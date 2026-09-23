#!/usr/bin/env python3
"""OCR / office-doc labs using real files under Documents/Work.

Default corpus: ``Work/test docs/OCR`` (pdf, docx, md, xlsx, csv, pptx, jpg/png).

For each living model × document kind:
  1) Extract text locally (pdftotext / OOXML / plain / csv)
  2) Ask the model a grounded question; assert expected tokens in the reply

Vision-capable models also get a scanned-image OCR case (tired_man_test.png or jpg).

Progress: running test case N/M. Does not print secrets.
"""

from __future__ import annotations

import base64
import csv
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

DEFAULT_WORK_OCR = Path("/home/tringuyen/Documents/Work/test docs/OCR")

VISION_MODELS = (
    "Qwen/Qwen3.5-0.8B",
    "Qwen/Qwen3.5-2B",
)
TEXT_MODELS = (
    "Qwen/Qwen3.5-0.8B",
    "Qwen/Qwen3.5-2B",
    "Qwen/Qwen3-8B",
    "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B",
    "meta-llama/Llama-3.1-8B-Instruct",
)

# kind -> (filename, question, must_contain_any)
DOC_CASES: list[tuple[str, str, str, tuple[str, ...]]] = [
    (
        "md",
        "message.md",
        "What city is this weather update for, and what is the observed temperature in °F? "
        "Reply in one short sentence.",
        ("Ho Chi Minh", "93"),
    ),
    (
        "pdf",
        "hcmc_weather_report.pdf",
        "From this weather report, what is the RealFeel temperature in °F? Reply with one number.",
        ("107",),
    ),
    (
        "docx",
        "hcmc_weather.docx",
        "What is the chance of rain percent today? Reply with one integer.",
        ("64",),
    ),
    (
        "pptx",
        "hcmc_weather.pptx",
        "What is the chance of rain percent in the forecast? Reply with one integer.",
        ("64",),
    ),
    (
        "xlsx",
        "usage-events-2026-08-21.xlsx",
        "From this spreadsheet extract, what is the sheet/table theme? "
        "Reply with one short phrase mentioning KPI if present.",
        ("KPI", "kpi"),
    ),
    (
        "csv",
        "usage-events-2026-08-21.csv",
        "What is the Kind column value on the first data row? Reply with one word.",
        ("Included",),
    ),
]

IMAGE_CASES: list[tuple[str, str, str, tuple[str, ...]]] = [
    (
        "jpg",
        "7b2784ef8b450a1b5354.jpg",
        "Describe the main subject of this photo in one short sentence.",
        (),  # soft: non-empty only
    ),
    (
        "png",
        "tired_man_test.png",
        "Describe the person or scene in one short sentence.",
        (),
    ),
]


def fail(message: str) -> None:
    raise SystemExit(f"ocr-docs contract failed: {message}")


def work_ocr_root() -> Path:
    raw = os.environ.get("LLM_STUDIO_OCR_ROOT", "").strip()
    root = Path(raw) if raw else DEFAULT_WORK_OCR
    if not root.is_dir():
        fail(f"OCR root missing: {root}")
    return root


def living_text_models() -> list[str]:
    raw = os.environ.get("LLM_STUDIO_TEST_MODELS", "").strip()
    if raw:
        return [m.strip() for m in raw.split(",") if m.strip()]
    return list(TEXT_MODELS)


def living_vision_models() -> list[str]:
    raw = os.environ.get("LLM_STUDIO_TEST_VISION_MODELS", "").strip()
    if raw:
        return [m.strip() for m in raw.split(",") if m.strip()]
    models = set(living_text_models())
    return [m for m in VISION_MODELS if m in models] or [
        m for m in VISION_MODELS if not os.environ.get("LLM_STUDIO_TEST_MODELS")
    ]


def extract_md(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def extract_pdf(path: Path) -> str:
    try:
        proc = subprocess.run(
            ["pdftotext", "-layout", str(path), "-"],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except FileNotFoundError:
        fail("pdftotext not installed (poppler-utils)")
    if proc.returncode != 0 or not (proc.stdout or "").strip():
        fail(f"pdftotext failed for {path.name}: {(proc.stderr or '')[:300]}")
    return proc.stdout


def extract_docx(path: Path) -> str:
    with zipfile.ZipFile(path) as zf:
        xml = zf.read("word/document.xml")
    root = ET.fromstring(xml)
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    return "\n".join((n.text or "") for n in root.findall(".//w:t", ns))


def extract_pptx(path: Path) -> str:
    texts: list[str] = []
    with zipfile.ZipFile(path) as zf:
        slides = sorted(
            n
            for n in zf.namelist()
            if n.startswith("ppt/slides/slide") and n.endswith(".xml")
        )
        for name in slides:
            root = ET.fromstring(zf.read(name))
            for node in root.iter():
                if node.tag.endswith("}t") and node.text:
                    texts.append(node.text)
    return "\n".join(texts)


def extract_xlsx(path: Path, *, max_cells: int = 80) -> str:
    texts: list[str] = []
    with zipfile.ZipFile(path) as zf:
        if "xl/sharedStrings.xml" in zf.namelist():
            root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
            for si in list(root)[:200]:
                parts = [
                    t.text
                    for t in si.iter()
                    if t.tag.endswith("}t") and t.text
                ]
                texts.append("".join(parts))
        sheets = sorted(
            n
            for n in zf.namelist()
            if n.startswith("xl/worksheets/sheet") and n.endswith(".xml")
        )
        if not sheets:
            fail(f"xlsx has no worksheets: {path.name}")
        # Prefer first worksheet listed
        sheet_xml = zf.read(sheets[0])
        root = ET.fromstring(sheet_xml)
        for node in root.iter():
            if node.tag.endswith("}t") and node.text:
                texts.append(node.text)
            elif node.tag.endswith("}v") and node.text and len(texts) < max_cells:
                # keep a few numeric/raw values for grounding
                texts.append(node.text)
            if len(texts) >= max_cells:
                break
    return "\n".join(texts[:max_cells])


def extract_csv(path: Path, *, max_rows: int = 6) -> str:
    lines: list[str] = []
    with path.open(newline="", encoding="utf-8", errors="replace") as handle:
        reader = csv.reader(handle)
        for i, row in enumerate(reader):
            if i >= max_rows:
                break
            lines.append(",".join(row))
    return "\n".join(lines)


EXTRACTORS = {
    "md": extract_md,
    "pdf": extract_pdf,
    "docx": extract_docx,
    "pptx": extract_pptx,
    "xlsx": extract_xlsx,
    "csv": extract_csv,
}


def _post(base_url: str, api_key: str, body: dict, label: str) -> dict:
    request = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=json.dumps(body).encode(),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "X-Session-ID": f"ocr-{label}",
            "X-Correlation-ID": f"ocr-{label}",
        },
        method="POST",
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=900) as response:
            payload = json.load(response)
            headers = {k.lower(): v for k, v in response.headers.items()}
            status = response.status
    except urllib.error.HTTPError as exc:
        fail(f"{label}: HTTP {exc.code}: {exc.read().decode(errors='replace')[:500]}")
    except urllib.error.URLError as exc:
        fail(f"{label}: {exc.reason}")

    wall_ms = int((time.perf_counter() - started) * 1000)
    choice = (payload.get("choices") or [{}])[0]
    content = ((choice.get("message") or {}).get("content") or "").strip()
    if status != 200 or not content:
        fail(f"{label}: status={status} empty={not content}")
    usage = payload.get("usage") or {}
    return {
        "label": label,
        "wall_ms": wall_ms,
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "cache_hit_percent": headers.get("x-cache-hit-percent"),
        "first_token_ms": headers.get("x-first-token-latency-ms")
        or headers.get("x-first-token-ms"),
        "last_token_ms": headers.get("x-last-token-latency-ms")
        or headers.get("x-last-token-ms"),
        "answer_preview": content[:200],
        "answer": content,
    }


def chat_extracted(
    *,
    base_url: str,
    api_key: str,
    model: str,
    kind: str,
    extracted: str,
    question: str,
    expect_any: tuple[str, ...],
    label: str,
    case_n: int,
    case_total: int,
) -> dict:
    print(f"running test case {case_n}/{case_total}: {label}", flush=True)
    # Cap huge sheets
    body_text = extracted if len(extracted) <= 12000 else extracted[:12000] + "\n…[truncated]"
    prompt = (
        f"You are reading an extracted {kind} document.\n"
        f"----\n{body_text}\n----\n"
        f"{question}\n"
        "Do not invent facts that are absent from the document."
    )
    row = _post(
        base_url,
        api_key,
        {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
            "max_tokens": 96,
            "chat_template_kwargs": {"enable_thinking": False},
            "reasoning_effort": "off",
        },
        label,
    )
    answer = row["answer"]
    if expect_any and not any(token.lower() in answer.lower() for token in expect_any):
        fail(f"{label}: expected one of {expect_any} in reply: {answer[:240]!r}")
    print(
        f"  ok {label}: wall_ms={row['wall_ms']} cache%={row['cache_hit_percent']} "
        f"first={row['first_token_ms']}",
        flush=True,
    )
    row.pop("answer", None)
    return row


def chat_vision(
    *,
    base_url: str,
    api_key: str,
    model: str,
    image_path: Path,
    question: str,
    expect_any: tuple[str, ...],
    label: str,
    case_n: int,
    case_total: int,
) -> dict:
    print(f"running test case {case_n}/{case_total}: {label}", flush=True)
    suffix = image_path.suffix.lower().lstrip(".")
    mime = "image/jpeg" if suffix in {"jpg", "jpeg"} else "image/png"
    b64 = base64.standard_b64encode(image_path.read_bytes()).decode("ascii")
    row = _post(
        base_url,
        api_key,
        {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": question},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime};base64,{b64}"},
                        },
                    ],
                }
            ],
            "temperature": 0,
            "max_tokens": 96,
            "chat_template_kwargs": {"enable_thinking": False},
        },
        label,
    )
    answer = row["answer"]
    if expect_any and not any(token.lower() in answer.lower() for token in expect_any):
        fail(f"{label}: expected one of {expect_any} in reply: {answer[:240]!r}")
    print(
        f"  ok {label}: wall_ms={row['wall_ms']} cache%={row['cache_hit_percent']} "
        f"first={row['first_token_ms']}",
        flush=True,
    )
    row.pop("answer", None)
    return row


def main() -> None:
    base_url = os.environ.get("LLM_STUDIO_TEST_BASE_URL", "http://10.8.0.1:18080/v1").rstrip("/")
    api_key = os.environ.get("LLM_STUDIO_API_KEY", "")
    if not api_key:
        fail("set LLM_STUDIO_API_KEY without printing it")

    root = work_ocr_root()
    text_models = living_text_models()
    vision_models = living_vision_models()

    prepared: list[tuple[str, str, str, str, tuple[str, ...]]] = []
    for kind, filename, question, expect in DOC_CASES:
        path = root / filename
        if not path.is_file():
            fail(f"missing Work OCR file: {path}")
        extracted = EXTRACTORS[kind](path)
        if len(extracted.strip()) < 8:
            fail(f"empty extract for {filename}")
        prepared.append((kind, filename, extracted, question, expect))

    image_prepared: list[tuple[str, Path, str, tuple[str, ...]]] = []
    for kind, filename, question, expect in IMAGE_CASES:
        path = root / filename
        if path.is_file():
            image_prepared.append((kind, path, question, expect))

    case_total = len(text_models) * len(prepared) + len(vision_models) * len(image_prepared)
    case_n = 0
    rows: list[dict] = []

    for model in text_models:
        for kind, filename, extracted, question, expect in prepared:
            case_n += 1
            rows.append(
                chat_extracted(
                    base_url=base_url,
                    api_key=api_key,
                    model=model,
                    kind=kind,
                    extracted=extracted,
                    question=question,
                    expect_any=expect,
                    label=f"{model}::ocr-{kind}:{filename}",
                    case_n=case_n,
                    case_total=case_total,
                )
            )

    for model in vision_models:
        for kind, path, question, expect in image_prepared:
            case_n += 1
            rows.append(
                chat_vision(
                    base_url=base_url,
                    api_key=api_key,
                    model=model,
                    image_path=path,
                    question=question,
                    expect_any=expect,
                    label=f"{model}::ocr-image-{kind}:{path.name}",
                    case_n=case_n,
                    case_total=case_total,
                )
            )

    out = Path(__file__).resolve().parents[1] / "reports" / "ocr-docs-perf.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(
            {
                "ocr_root": str(root),
                "doc_kinds": [c[0] for c in DOC_CASES],
                "results": rows,
            },
            indent=2,
        )
        + "\n"
    )
    print(f"wrote {out}", flush=True)
    print(f"ocr-docs contract PASS: {case_total}/{case_total}", flush=True)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
