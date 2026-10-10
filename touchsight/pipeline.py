"""End-to-end: image bytes -> tactile graphic package."""
from __future__ import annotations

import base64
import time

import cv2

from . import braille as br
from . import export, segment, tactile, vlm


def run(image_bytes: bytes, analysis: dict | None = None, use_cache: bool = True) -> dict:
    t0 = time.time()
    timings = {}
    provider = "provided"
    if analysis is None:
        analysis, provider = vlm.analyse(image_bytes, use_cache=use_cache)
    else:
        analysis = vlm.normalise(analysis)
    timings["understand"] = round(time.time() - t0, 2)

    t = time.time()
    img = segment.load_image(image_bytes)
    clean = segment.remove_text(img, analysis["text_labels"],
                                keep_boxes=[e["box_2d"] for e in analysis["elements"] if e["kind"] != "region"])
    items = segment.segment_elements(clean, analysis)
    timings["segment"] = round(time.time() - t, 2)

    t = time.time()
    scene = tactile.design(items, analysis, img.shape)
    timings["design"] = round(time.time() - t, 2)

    t = time.time()
    hm = export.heightmap(scene)
    svg_print = export.to_svg(scene, "print")
    svg_preview = export.to_svg(scene, "preview")
    timings["export"] = round(time.time() - t, 2)

    ok, seg_png = cv2.imencode(".png", segment.debug_overlay(clean, items))
    before, after = scene.issues_before, scene.issues_after
    elements = []
    for e in scene.elements:
        elements.append({
            "id": e["id"], "name": e["name"], "kind": e["kind"], "importance": e["importance"],
            "texture": e.get("texture"), "reason": e.get("reason", ""), "method": e.get("method", ""),
            "braille": br.to_unicode(e["name"]),
        })
    return {
        "title": scene.title,
        "title_braille": br.to_unicode(scene.title),
        "summary": scene.summary,
        "diagram_type": analysis.get("diagram_type"),
        "provider": provider,
        "analysis": analysis,
        "elements": elements,
        "dropped": scene.dropped,
        "key": scene.key_rows,
        "labels": [{"text": L.text, "ink": L.ink, "kind": L.kind, "braille": br.to_unicode(L.text),
                    "x": round(L.x, 1), "y": round(L.y, 1)} for L in scene.labels],
        "validation": {
            # the first draft is scored on the same checks as the final page (labels included)
            "before": {"score": tactile.score([tactile.Issue(**{**i.__dict__, "fixed": False}) for i in before]
                                              + [i for i in after if i.code.startswith("label")]),
                       "issues": [i.as_dict() for i in before]},
            "after": {"score": tactile.score(after), "issues": [i.as_dict() for i in after]},
            "fixes": scene.fixes,
        },
        "svg_print": svg_print,
        "svg_preview": svg_preview,
        "heightmap_png": base64.b64encode(export.png_bytes(hm)).decode(),
        "segmentation_png": base64.b64encode(seg_png.tobytes()).decode() if ok else None,
        "page_mm": [tactile.PAGE_W, tactile.PAGE_H],
        "timings": timings,
        "_heightmap": hm,
    }
