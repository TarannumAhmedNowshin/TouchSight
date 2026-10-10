"""TouchSight engine API.   Run:  uvicorn app:app --port 8000   (the Next.js frontend in ./frontend talks to it)"""
from __future__ import annotations

import io
import json
import os
import re
import logging
import traceback
import uuid
import zipfile
from collections import OrderedDict
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from touchsight import export, pipeline, vlm

ROOT = Path(__file__).resolve().parent
SAMPLES = ROOT / "samples"
app = FastAPI(title="TouchSight")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/samples", StaticFiles(directory=SAMPLES), name="samples")

JOBS: OrderedDict[str, dict] = OrderedDict()
MAX_JOBS = 20
MAX_UPLOAD = 12 * 1024 * 1024


@app.get("/")
def index():
    return {"service": "TouchSight engine", "frontend": "run `npm run dev` in ./frontend and open http://localhost:3000"}


@app.get("/api/samples")
def samples():
    out = []
    for p in sorted(SAMPLES.glob("*")):
        if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"):
            out.append({"name": p.stem, "url": f"/samples/{p.name}?v={int(p.stat().st_mtime)}",
                        "label": p.stem.replace("_", " ").capitalize()})
    return out


def _run(image_bytes: bytes, sample: str | None = None, fresh: bool = False) -> dict:
    try:
        return pipeline.run(image_bytes, use_cache=not fresh)
    except RuntimeError as ex:
        # vision APIs unreachable: samples fall back to their bundled analysis
        mock = SAMPLES / f"{sample}.mock.json" if sample else None
        if mock and mock.exists():
            r = pipeline.run(image_bytes, analysis=json.loads(mock.read_text()))
            r["provider"] = "bundled sample analysis (vision API unavailable)"
            return r
        raise HTTPException(502, f"Could not reach a vision model. {ex}")


@app.post("/api/convert")
async def convert(file: UploadFile | None = File(None), sample: str | None = Form(None),
                  fresh: bool = Form(False)):
    if file is not None:
        data = await file.read()
        if len(data) > MAX_UPLOAD:
            raise HTTPException(413, "Image is larger than 12 MB. Try a smaller export.")
    elif sample:
        paths = [p for p in SAMPLES.glob(f"{sample}.*") if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp")]
        if not paths:
            raise HTTPException(404, "Sample not found")
        data = paths[0].read_bytes()
    else:
        raise HTTPException(400, "Upload an image or choose a sample.")
    try:
        result = await run_in_threadpool(_run, data, sample, fresh)  # keep the server responsive
    except HTTPException:
        raise
    except ValueError as ex:
        raise HTTPException(422, str(ex))
    except Exception as ex:  # surface the real cause instead of a bare 500
        tb = traceback.format_exc()
        logging.getLogger("touchsight").error(tb)
        (ROOT / "cache" / "last_error.txt").write_text(tb)
        raise HTTPException(500, f"The engine hit an error: {type(ex).__name__}: {ex}. Details saved to cache/last_error.txt")
    job = uuid.uuid4().hex[:10]
    JOBS[job] = {"heightmap": result.pop("_heightmap"), "svg": result["svg_print"], "title": result["title"]}
    while len(JOBS) > MAX_JOBS:
        JOBS.popitem(last=False)
    result["job"] = job
    return JSONResponse(result)


@app.post("/api/samples/save")
async def save_sample(file: UploadFile = File(...), name: str = Form(...), credit: str = Form("")):
    """Local helper: store an image as a demo sample (disabled when ALLOW_SAMPLE_UPLOAD=0)."""
    if os.getenv("ALLOW_SAMPLE_UPLOAD", "1") != "1":
        raise HTTPException(403, "Saving samples is turned off on this server.")
    slug = re.sub(r"[^a-z0-9_]+", "_", name.lower()).strip("_")[:40]
    if not slug:
        raise HTTPException(400, "Give the sample a name.")
    data = await file.read()
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, "Image is larger than 12 MB.")
    ext = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}.get(file.content_type or "", ".png")
    (SAMPLES / f"{slug}{ext}").write_bytes(data)
    if credit:
        credits = SAMPLES / "CREDITS.md"
        lines = credits.read_text().splitlines() if credits.exists() else ["# Sample image credits", ""]
        lines = [l for l in lines if not l.startswith(f"- **{slug}{ext}**")]
        lines.append(f"- **{slug}{ext}**: {credit}")
        credits.write_text("\n".join(lines) + "\n")
    return {"saved": f"{slug}{ext}"}


def _job(job: str) -> dict:
    if job not in JOBS:
        raise HTTPException(404, "This result has expired. Convert the image again.")
    return JOBS[job]


def _slug(t: str) -> str:
    return "".join(c if c.isalnum() else "-" for c in t.lower()).strip("-") or "tactile"


@app.get("/api/download/{job}/svg")
def download_svg(job: str):
    j = _job(job)
    return Response(j["svg"], media_type="image/svg+xml",
                    headers={"Content-Disposition": f'attachment; filename="{_slug(j["title"])}-tactile.svg"'})


@app.get("/api/download/{job}/stl")
def download_stl(job: str):
    j = _job(job)
    stl = export.to_stl(j["heightmap"])
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(f"{_slug(j['title'])}-tactile.stl", stl)
    return Response(buf.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{_slug(j["title"])}-stl.zip"'})


@app.get("/api/download/{job}/heightmap")
def download_hm(job: str):
    j = _job(job)
    return Response(export.png_bytes(j["heightmap"]), media_type="image/png",
                    headers={"Content-Disposition": f'attachment; filename="{_slug(j["title"])}-heightmap.png"'})


@app.get("/api/health")
def health():
    import os
    return {"gemini_key": bool(os.getenv("GEMINI_API_KEY")), "groq_key": bool(os.getenv("GROQ_API_KEY")),
            "prompt_version": vlm.PROMPT_VERSION}
