"""TouchSight engine API (FastAPI).

Run locally:  uvicorn app:app --port 8000   (the Next.js app in ./frontend proxies /api here)
"""
from __future__ import annotations

import io
import logging
import os
import re
import threading
import time
import uuid
import zipfile
from collections import OrderedDict, defaultdict, deque

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from touchsight import export, intake, pipeline, vlm
from touchsight.config import settings
from touchsight.intake import ImageError
from touchsight.vlm import VisionError

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("touchsight.api")
DEBUG_ERRORS = os.getenv("DEBUG_ERRORS", "0") == "1"   # local dev only: show error details to the client
IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp")  # trusted demo samples only

app = FastAPI(title="TouchSight", docs_url="/api/docs" if DEBUG_ERRORS else None, redoc_url=None)
app.add_middleware(CORSMiddleware, allow_origins=settings.allowed_origins, allow_methods=["GET", "POST"],
                   allow_headers=["Content-Type"])
settings.samples_dir.mkdir(exist_ok=True)
app.mount("/samples", StaticFiles(directory=settings.samples_dir), name="samples")


# ------------------------------------------------------------------ in-memory job store
class JobStore:
    """Recent results, so downloads and teacher edits don't repeat the work. Bounded LRU."""

    def __init__(self, capacity: int = 24):
        self._jobs: OrderedDict[str, dict] = OrderedDict()
        self._lock = threading.Lock()
        self._capacity = capacity

    def put(self, job: dict) -> str:
        job_id = uuid.uuid4().hex
        with self._lock:
            self._jobs[job_id] = job
            while len(self._jobs) > self._capacity:
                self._jobs.popitem(last=False)
        return job_id

    def get(self, job_id: str) -> dict:
        with self._lock:
            job = self._jobs.get(job_id)
        if job is None:
            raise HTTPException(404, "This result has expired. Convert the image again.")
        return job


JOBS = JobStore()


# ------------------------------------------------------------------ rate limiting
_hits: dict[str, deque] = defaultdict(deque)
_hits_lock = threading.Lock()


def rate_limit(request: Request, bucket: str = "convert", per_min: int | None = None) -> None:
    """Sliding-window limit per client and endpoint (protects the vision API quota)."""
    limit = per_min or settings.rate_limit_per_min
    # the right-most X-Forwarded-For entry is the one added by our own proxy; earlier ones are client-supplied
    forwarded = [h.strip() for h in request.headers.get("x-forwarded-for", "").split(",") if h.strip()]
    client = forwarded[-1] if forwarded else (request.client.host if request.client else "?")
    now = time.monotonic()
    with _hits_lock:
        q = _hits[f"{bucket}:{client}"]
        while q and now - q[0] > 60:
            q.popleft()
        if len(q) >= limit:
            raise HTTPException(429, "That's a lot of requests in a minute. Wait a moment and try again.")
        q.append(now)


# ------------------------------------------------------------------ helpers
def _sample_files() -> dict[str, "os.PathLike"]:
    return {p.stem: p for p in sorted(settings.samples_dir.iterdir()) if p.suffix.lower() in IMAGE_SUFFIXES}


async def _read_upload(file: UploadFile) -> bytes:
    """Read an upload within the size cap and normalise it (any supported format -> upright PNG)."""
    data = await file.read(settings.max_upload_bytes + 1)
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(413, "Image is larger than 12 MB. Try a smaller export.")
    try:
        return await run_in_threadpool(intake.normalise, data)
    except ImageError as ex:
        raise HTTPException(415, str(ex)) from ex


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:50] or "tactile"


def _convert(image: bytes, analysis: dict | None = None, exclude: set[str] | None = None,
             fresh: bool = False) -> dict:
    try:
        out = pipeline.run(image, analysis=analysis, exclude=exclude, use_cache=not fresh)
    except VisionError as ex:
        log.warning("vision providers failed: %s", ex)
        raise HTTPException(502, "Couldn't reach a vision model right now. Try again in a minute.") from ex
    except (ImageError, ValueError) as ex:
        raise HTTPException(422, str(ex)) from ex
    except Exception as ex:
        error_id = uuid.uuid4().hex[:8]
        log.exception("conversion failed [%s]", error_id)
        detail = f"The engine hit an error (ref {error_id})."
        if DEBUG_ERRORS:
            detail += f" {type(ex).__name__}: {ex}"
        raise HTTPException(500, detail) from ex
    job_id = JOBS.put({"image": image, "analysis": out.analysis, "heightmap": out.heightmap,
                       "svg": out.svg_print, "title": out.report["title"], "facts": out.facts})
    return {**out.report, "job": job_id}


# ------------------------------------------------------------------ routes
log.info("vision providers configured: gemini=%s groq=%s",
         "yes" if settings.gemini_api_key else "NO", "yes" if settings.groq_api_key else "NO")


@app.get("/api/health")
def health():
    # whether each provider has a key (never the key itself) makes deployment problems obvious
    return {"status": "ok", "gemini_configured": bool(settings.gemini_api_key),
            "groq_configured": bool(settings.groq_api_key)}


@app.get("/api/samples")
def samples():
    return [{"name": name, "url": f"/samples/{p.name}?v={int(p.stat().st_mtime)}",
             "label": name.replace("_", " ").capitalize()} for name, p in _sample_files().items()]


@app.post("/api/convert")
async def convert(request: Request, file: UploadFile | None = File(None), sample: str | None = Form(None),
                  fresh: bool = Form(False)):
    rate_limit(request)
    if file is not None:
        image = await _read_upload(file)
    elif sample:
        path = _sample_files().get(sample)  # whitelist lookup: no user input reaches the filesystem
        if path is None:
            raise HTTPException(404, "Sample not found.")
        image = path.read_bytes()
    else:
        raise HTTPException(400, "Upload an image or choose a sample.")
    return JSONResponse(await run_in_threadpool(_convert, image, None, None, fresh))


class RedesignRequest(BaseModel):
    job: str = Field(min_length=8, max_length=64, pattern=r"^[a-f0-9]+$")
    exclude: list[str] = Field(default_factory=list, max_length=20)


@app.post("/api/redesign")
async def redesign(request: Request, body: RedesignRequest):
    """Teacher edit: rebuild the page without some parts, reusing the earlier reading (no model call)."""
    rate_limit(request)
    job = JOBS.get(body.job)
    known = {e["id"] for e in job["analysis"]["elements"]}
    exclude = {i for i in body.exclude if i in known}
    return JSONResponse(await run_in_threadpool(_convert, job["image"], job["analysis"], exclude))


class AskRequest(BaseModel):
    job: str = Field(min_length=8, max_length=64, pattern=r"^[a-f0-9]+$")
    question: str = Field(min_length=1, max_length=300)


@app.post("/api/ask")
async def ask(request: Request, body: AskRequest):
    """Answer a spoken question about the current page, grounded in its layout facts."""
    rate_limit(request, bucket="ask", per_min=30)
    job = JOBS.get(body.job)
    try:
        answer, provider = await run_in_threadpool(vlm.answer_question, body.question, job["facts"])
    except ValueError as ex:
        raise HTTPException(422, str(ex)) from ex
    except VisionError as ex:
        log.warning("ask failed: %s", ex)
        raise HTTPException(502, "Couldn't reach a model to answer right now. Try again in a moment.") from ex
    return {"answer": answer, "provider": provider}


def _attachment(content: bytes | str, media_type: str, filename: str) -> Response:
    return Response(content, media_type=media_type,
                    headers={"Content-Disposition": f'attachment; filename="{filename}"',
                             "X-Content-Type-Options": "nosniff"})


@app.get("/api/download/{job_id}/svg")
def download_svg(job_id: str):
    job = JOBS.get(job_id)
    return _attachment(job["svg"], "image/svg+xml", f"{_slug(job['title'])}-tactile.svg")


@app.get("/api/download/{job_id}/stl")
def download_stl(job_id: str):
    job = JOBS.get(job_id)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(f"{_slug(job['title'])}-tactile.stl", export.to_stl(job["heightmap"]))
    return _attachment(buf.getvalue(), "application/zip", f"{_slug(job['title'])}-stl.zip")


@app.get("/api/download/{job_id}/heightmap")
def download_heightmap(job_id: str):
    job = JOBS.get(job_id)
    return _attachment(export.png_bytes(job["heightmap"]), "image/png", f"{_slug(job['title'])}-heightmap.png")


@app.post("/api/samples/save")
async def save_sample(file: UploadFile = File(...), name: str = Form(...), credit: str = Form("")):
    """Local authoring helper for demo samples. Off unless ALLOW_SAMPLE_UPLOAD=1."""
    if not settings.allow_sample_upload:
        raise HTTPException(403, "Saving samples is turned off on this server.")
    slug = re.sub(r"[^a-z0-9_]+", "_", name.lower()).strip("_")[:40]
    if not slug:
        raise HTTPException(400, "Give the sample a name.")
    image = await _read_upload(file)
    filename = f"{slug}.png"
    (settings.samples_dir / filename).write_bytes(image)
    if credit:
        credit_line = re.sub(r"[\r\n]+", " ", credit)[:300]
        credits = settings.samples_dir / "CREDITS.md"
        lines = credits.read_text().splitlines() if credits.exists() else ["# Sample image credits", ""]
        lines = [line for line in lines if not line.startswith(f"- **{filename}**")]
        lines.append(f"- **{filename}**: {credit_line}")
        credits.write_text("\n".join(lines) + "\n")
    return {"saved": filename}
