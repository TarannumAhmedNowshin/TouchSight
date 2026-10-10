"""Vision-language "understanding" step.

Asks a multimodal model what the diagram is, which elements matter for
learning, where they are, and what can be dropped. Gemini is the primary
provider; Groq (open-source Qwen VL) is the automatic fallback. Results are
cached on disk by image hash so demos never depend on a live API call.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import re
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv()

PROMPT_VERSION = "v4"
CACHE_DIR = Path(__file__).resolve().parent.parent / "cache"

SYSTEM_PROMPT = """You are an expert transcriber of tactile graphics for blind students,
trained on the BANA "Guidelines and Standards for Tactile Graphics".
A tactile graphic must be SIMPLER than the print original: fingers resolve far
less detail than eyes, so keep only what a student needs to learn the concept,
and drop decoration, shading, duplicated detail and tiny parts.

Analyse the image and return ONLY a JSON object with this exact shape:
{
  "diagram_type": "biology" | "anatomy" | "physics" | "circuit" | "chemistry" | "geography" | "geometry" | "chart" | "other",
  "title": "short title for the graphic (max 5 words)",
  "summary": "one sentence: what a student should learn from this graphic",
  "is_3d_perspective": true | false,
  "elements": [
    {
      "id": "e1",
      "name": "short label a student needs, e.g. 'nucleus' (max 3 words, lowercase)",
      "kind": "region" | "line" | "point",
      "importance": 3 | 2 | 1,
      "box_2d": [ymin, xmin, ymax, xmax],
      "parent": "id of the element that encloses this one, or null",
      "reason": "why a blind student needs this (max 10 words)"
    }
  ],
  "text_labels": [ {"text": "label text as printed", "box_2d": [ymin, xmin, ymax, xmax]} ],
  "dropped": [ {"what": "thing left out", "reason": "why (max 10 words)"} ]
}

Rules:
- box_2d coordinates are integers normalised to 0-1000 (y first, then x).
- Make each element's box tight around the element itself, NOT around its printed label.
- "region" = an area/shape (organ, cell part, country). "line" = wires, arrows,
  vessels, axes, boundaries. "point" = a small location marker (city, node).
- importance 3 = essential to the concept, 2 = helpful, 1 = optional context.
- At most 10 elements. Prefer fewer, larger, meaningful elements.
- text_labels: every piece of printed text visible in the image (so it can be erased
  and replaced with braille). Include leader-line labels and the title if printed.
- Do not invent elements that are not visible.
"""


def _cache_path(image_bytes: bytes) -> Path:
    h = hashlib.sha256(image_bytes + PROMPT_VERSION.encode()).hexdigest()[:20]
    return CACHE_DIR / f"vlm_{h}.json"


def _extract_json(text: str) -> dict:
    text = text.strip()
    # strip <think> blocks and markdown fences some open models emit
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, flags=re.S)
    if fence:
        text = fence.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("model did not return JSON")
    return json.loads(text[start : end + 1])


def _mime(image_bytes: bytes) -> str:
    if image_bytes[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if image_bytes[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if image_bytes[:4] == b"RIFF" and image_bytes[8:12] == b"WEBP":
        return "image/webp"
    return "image/png"


_GEMINI_MODEL: str | None = None
_SKIP = ("image", "tts", "live", "audio", "embedding", "robotics", "native", "thinking-exp", "learnlm", "gemma")


def _version(name: str) -> float:
    m = re.search(r"gemini-(\d+(?:\.\d+)?)", name)
    return float(m.group(1)) if m else 0.0


def gemini_candidates(key: str) -> list[str]:
    """Flash models this key lists, best first. Listed ≠ usable (retired models still appear)."""
    r = httpx.get("https://generativelanguage.googleapis.com/v1beta/models",
                  headers={"x-goog-api-key": key}, params={"pageSize": 200}, timeout=30)
    r.raise_for_status()
    names = [m["name"].split("/", 1)[1] for m in r.json().get("models", [])
             if "generateContent" in m.get("supportedGenerationMethods", [])]
    flash = [n for n in names if "flash" in n and not any(k in n for k in _SKIP)]
    flash.sort(key=lambda n: (_version(n), "lite" not in n, "preview" not in n and "exp" not in n, -len(n)), reverse=True)
    wanted = os.getenv("GEMINI_MODEL")
    if wanted in flash:
        flash.remove(wanted)
        flash.insert(0, wanted)
    return flash


def call_gemini(image_bytes: bytes, timeout: float = 90) -> dict:
    global _GEMINI_MODEL
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY not set")
    body = {
        "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [
            {
                "parts": [
                    {"inline_data": {"mime_type": _mime(image_bytes),
                                     "data": base64.b64encode(image_bytes).decode()}},
                    {"text": "Analyse this diagram for tactile transcription. Return the JSON."},
                ]
            }
        ],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.2},
    }
    models = [_GEMINI_MODEL] if _GEMINI_MODEL else gemini_candidates(key)
    if not models:
        raise RuntimeError("no Gemini Flash model is available to this key")
    tried = []
    for model in models[:6]:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        r = httpx.post(url, headers={"x-goog-api-key": key}, json=body, timeout=timeout)
        if r.status_code in (400, 403, 404) and not _GEMINI_MODEL:
            tried.append(f"{model}: {r.status_code} {r.text[:120]}")
            continue  # retired / not enabled for this key -> try the next one
        r.raise_for_status()
        _GEMINI_MODEL = model
        text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
        return _extract_json(text)
    raise RuntimeError("no usable Gemini model. Tried -> " + " | ".join(tried))


def call_groq(image_bytes: bytes, timeout: float = 90) -> dict:
    key = os.getenv("GROQ_API_KEY")
    if not key:
        raise RuntimeError("GROQ_API_KEY not set")
    model = os.getenv("GROQ_MODEL", "qwen/qwen3.8-27b")
    b64 = base64.b64encode(image_bytes).decode()
    body = {
        "model": model,
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Analyse this diagram for tactile transcription. Return the JSON."},
                    {"type": "image_url", "image_url": {"url": f"data:{_mime(image_bytes)};base64,{b64}"}},
                ],
            },
        ],
    }
    r = httpx.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {key}"},
        json=body,
        timeout=timeout,
    )
    r.raise_for_status()
    return _extract_json(r.json()["choices"][0]["message"]["content"])


def normalise(analysis: dict) -> dict:
    """Make model output safe to consume downstream."""
    out = {
        "diagram_type": str(analysis.get("diagram_type", "other")),
        "title": str(analysis.get("title", "")).strip()[:60],
        "summary": str(analysis.get("summary", "")).strip(),
        "is_3d_perspective": bool(analysis.get("is_3d_perspective", False)),
        "elements": [],
        "text_labels": [],
        "dropped": analysis.get("dropped", []) or [],
    }

    def box(b):
        try:
            y0, x0, y1, x1 = [max(0, min(1000, int(round(float(v))))) for v in b]
        except Exception:
            return None
        if y1 < y0:
            y0, y1 = y1, y0
        if x1 < x0:
            x0, x1 = x1, x0
        if (y1 - y0) < 3 or (x1 - x0) < 3:
            return None
        return [y0, x0, y1, x1]

    seen = set()
    for i, e in enumerate(analysis.get("elements", []) or []):
        b = box(e.get("box_2d", []))
        if not b:
            continue
        eid = str(e.get("id") or f"e{i+1}")
        if eid in seen:
            eid = f"{eid}_{i}"
        seen.add(eid)
        kind = e.get("kind", "region")
        out["elements"].append({
            "id": eid,
            "name": str(e.get("name", f"part {i+1}")).strip().lower()[:30],
            "kind": kind if kind in ("region", "line", "point") else "region",
            "importance": int(e.get("importance", 2)) if str(e.get("importance", 2)).isdigit() else 2,
            "box_2d": b,
            "parent": e.get("parent") or None,
            "reason": str(e.get("reason", "")),
        })
    for t in analysis.get("text_labels", []) or []:
        b = box(t.get("box_2d", []))
        if b:
            out["text_labels"].append({"text": str(t.get("text", "")), "box_2d": b})
    ids = {e["id"] for e in out["elements"]}
    for e in out["elements"]:
        if e["parent"] not in ids or e["parent"] == e["id"]:
            e["parent"] = None
    return out


def pad_square(image_bytes: bytes) -> tuple[bytes, float, float]:
    """Pad to a white square (bottom/right) and cap the size.

    Models disagree on whether box_2d is normalised by width, height or the
    longer side; on a square image all three agree. Returns the padded PNG and
    the factors that map square-normalised coords back to the original image.
    """
    from PIL import Image  # local import keeps module import light

    im = Image.open(io.BytesIO(image_bytes))
    im = im.convert("RGBA")
    bg = Image.new("RGBA", im.size, "white")
    im = Image.alpha_composite(bg, im).convert("RGB")
    w, h = im.size
    side = max(w, h)
    sq = Image.new("RGB", (side, side), "white")
    sq.paste(im, (0, 0))
    if side > 1280:
        sq = sq.resize((1280, 1280), Image.LANCZOS)
    buf = io.BytesIO()
    sq.save(buf, "PNG")
    return buf.getvalue(), side / h, side / w


def _unpad(analysis: dict, fy: float, fx: float) -> dict:
    def fix(b):
        if not isinstance(b, (list, tuple)) or len(b) != 4:
            return b
        try:
            y0, x0, y1, x1 = [float(v) for v in b]
        except (TypeError, ValueError):
            return b
        return [y0 * fy, x0 * fx, y1 * fy, x1 * fx]

    for e in analysis.get("elements", []) or []:
        e["box_2d"] = fix(e.get("box_2d"))
    for t in analysis.get("text_labels", []) or []:
        t["box_2d"] = fix(t.get("box_2d"))
    return analysis


def analyse(image_bytes: bytes, use_cache: bool = True) -> tuple[dict, str]:
    """Return (analysis, provider). Tries cache → Gemini → Groq."""
    cp = _cache_path(image_bytes)
    if use_cache and cp.exists():
        return json.loads(cp.read_text()), "cache"
    errors = []
    padded, fy, fx = pad_square(image_bytes)
    for name, fn in (("gemini", call_gemini), ("groq", call_groq)):
        try:
            result = normalise(_unpad(fn(padded), fy, fx))
            if not result["elements"]:
                raise ValueError("no elements returned")
            CACHE_DIR.mkdir(exist_ok=True)
            cp.write_text(json.dumps(result, indent=2))
            label = f"{name} ({_GEMINI_MODEL})" if name == "gemini" else f"groq ({os.getenv('GROQ_MODEL', 'qwen/qwen3.8-27b')})"
            return result, label
        except Exception as ex:  # noqa: BLE001
            errors.append(f"{name}: {ex}")
    raise RuntimeError("All vision providers failed -> " + " | ".join(errors))


def save_to_cache(image_bytes: bytes, analysis: dict) -> Path:
    cp = _cache_path(image_bytes)
    CACHE_DIR.mkdir(exist_ok=True)
    cp.write_text(json.dumps(normalise(analysis), indent=2))
    return cp
