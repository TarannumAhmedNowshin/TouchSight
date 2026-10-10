"""End to end: image bytes -> tactile graphic package (print SVG, preview SVG, height map, report)."""
from __future__ import annotations

import base64
import logging
import time
from dataclasses import dataclass

import cv2
import numpy as np

from . import braille as br
from . import export, segment, tactile, vlm

log = logging.getLogger(__name__)


@dataclass
class Output:
    """What a conversion produces. `report` is JSON-safe; the rest stays server-side."""
    report: dict
    heightmap: np.ndarray
    svg_print: str
    analysis: dict


def _timer():
    start = time.perf_counter()
    return lambda: round(time.perf_counter() - start, 2)


def run(image_bytes: bytes, analysis: dict | None = None, exclude: set[str] | None = None,
        use_cache: bool = True) -> Output:
    """Convert a diagram.

    analysis: reuse an earlier reading instead of calling a vision model (teacher edits, tests).
    exclude:  element ids a teacher chose to leave out.
    """
    timings: dict[str, float] = {}
    elapsed = _timer()
    if analysis is None:
        analysis, provider = vlm.analyse(image_bytes, use_cache=use_cache)
    else:
        analysis, provider = vlm.normalise(analysis), "previous reading"
    timings["understand"] = elapsed()

    working = dict(analysis)
    if exclude:
        parents = {e["id"]: e["parent"] for e in analysis["elements"]}

        def surviving_parent(pid):  # a part whose parent was removed moves up to its grandparent
            while pid in exclude:
                pid = parents.get(pid)
            return pid

        working["elements"] = [{**e, "parent": surviving_parent(e["parent"])}
                               for e in analysis["elements"] if e["id"] not in exclude]
    if not working["elements"]:
        raise ValueError("Keep at least one part to build a tactile graphic.")

    elapsed = _timer()
    img = segment.load_image(image_bytes)
    keep_strokes = [e["box_2d"] for e in working["elements"] if e["kind"] != "region"]
    clean = segment.remove_text(img, working["text_labels"], keep_boxes=keep_strokes)
    traced = segment.segment_elements(clean, working)
    timings["segment"] = elapsed()

    elapsed = _timer()
    scene = tactile.design(traced, working, img.shape)
    timings["design"] = elapsed()

    elapsed = _timer()
    heightmap = export.heightmap(scene)
    svg_print = export.to_svg(scene, "print")
    svg_preview = export.to_svg(scene, "preview")
    timings["export"] = elapsed()

    ok, overlay = cv2.imencode(".png", segment.debug_overlay(clean, traced))
    kept_ids = {e["id"] for e in scene.elements}
    report = {
        "title": scene.title,
        "title_braille": br.to_unicode(scene.title),
        "summary": scene.summary,
        "description": describe(scene),
        "diagram_type": analysis["diagram_type"],
        "provider": provider,
        "elements": [
            {"id": e["id"], "name": e["name"], "kind": e["kind"], "importance": e["importance"],
             "reason": e["reason"], "braille": br.to_unicode(e["name"]),
             "included": e["id"] in kept_ids, "excluded_by_teacher": bool(exclude and e["id"] in exclude),
             "texture": next((k.get("texture") for k in scene.elements if k["id"] == e["id"]), None),
             "method": next((k.get("method", "") for k in scene.elements if k["id"] == e["id"]), "")}
            for e in analysis["elements"]
        ],
        "dropped": scene.dropped,
        "key": scene.key_rows,
        "validation": {
            "before": {"score": tactile.first_draft_score(scene),
                       "issues": [i.as_dict() for i in scene.issues_before]},
            "after": {"score": tactile.score(scene.issues_after),
                      "issues": [i.as_dict() for i in scene.issues_after]},
            "fixes": scene.fixes,
        },
        "svg_preview": svg_preview,
        "heightmap_png": base64.b64encode(export.png_bytes(heightmap)).decode(),
        "segmentation_png": base64.b64encode(overlay.tobytes()).decode() if ok else None,
        "page_mm": [tactile.PAGE_W, tactile.PAGE_H],
        "timings": timings,
    }
    return Output(report=report, heightmap=heightmap, svg_print=svg_print, analysis=analysis)


def describe(scene: tactile.Scene) -> str:
    """A plain-language companion description for screen-reader users."""
    parts = []
    for row in scene.key_rows:
        feel = f"felt as {tactile.TEXTURE_NAMES[row['texture']]}" if row.get("texture") else "outline only"
        label = f", labelled '{row['key']}'" if row.get("key") else ""
        parts.append(f"{row['name']} ({feel}{label})")
    unlabelled = [e["name"] for e in scene.elements if e["name"] not in {r["name"] for r in scene.key_rows}]
    text = f"{scene.title}. {scene.summary}".strip()
    if parts:
        text += " Key: " + "; ".join(parts) + "."
    if unlabelled:
        text += " Also labelled in braille on the page: " + ", ".join(dict.fromkeys(unlabelled)) + "."
    return text
