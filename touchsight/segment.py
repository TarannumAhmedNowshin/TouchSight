"""Tracing step: turn the model's boxes into real shapes, then into vector geometry.

For every element the model kept, find its actual outline in the image:
  region -> shapely Polygon   (outer outline, holes removed)
  line   -> MultiLineString   (centre-lines of the strokes)
  point  -> Point

Regions are traced in this order of preference:
  1. Colour-patch assignment: the image is split into flat-colour patches and each
     patch goes to the smallest model box that (almost) contains it. Shaded parts are
     rebuilt from their gradient bands and neighbours can't overlap.
  2. Best single colour patch inside the box.
  3. GrabCut seeded with the box, then a filled edge hull as a last resort.
All coordinates in this module are pixels of the working image.
"""
from __future__ import annotations

import logging

import cv2
import networkx as nx
import numpy as np
from shapely.geometry import LineString, MultiLineString, Point, Polygon
from skimage.morphology import skeletonize

from .intake import ImageError, inspect

log = logging.getLogger(__name__)
MAX_SIDE = 1000  # working resolution (px, longer side)


def load_image(image_bytes: bytes) -> np.ndarray:
    inspect(image_bytes)
    img = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_UNCHANGED)
    if img is None:
        raise ImageError("Could not decode the image.")
    if img.ndim == 2:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    elif img.shape[2] == 4:  # flatten transparency onto white
        alpha = img[:, :, 3:4].astype(np.float32) / 255
        img = (img[:, :, :3] * alpha + 255 * (1 - alpha)).astype(np.uint8)
    h, w = img.shape[:2]
    scale = MAX_SIDE / max(h, w)
    if scale < 1:
        img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    return img


def box_px(box_2d, shape):
    h, w = shape[:2]
    y0, x0, y1, x1 = box_2d
    return (int(x0 / 1000 * w), int(y0 / 1000 * h), int(x1 / 1000 * w), int(y1 / 1000 * h))


def remove_text(img: np.ndarray, text_labels: list[dict], keep_boxes=None, thin_lines: bool = True) -> np.ndarray:
    """Erase printed labels (replaced by braille) and hairline leader lines."""
    mask = np.zeros(img.shape[:2], np.uint8)
    for t in text_labels or []:
        x0, y0, x1, y1 = box_px(t["box_2d"], img.shape)
        pad = 4
        mask[max(0, y0 - pad): y1 + pad, max(0, x0 - pad): x1 + pad] = 255
    if thin_lines:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        dark = (gray < 150).astype(np.uint8) * 255  # leader lines are often grey, not black
        thick = cv2.morphologyEx(dark, cv2.MORPH_OPEN, np.ones((4, 4), np.uint8))
        thin = cv2.subtract(dark, cv2.dilate(thick, np.ones((3, 3), np.uint8)))
        for b in keep_boxes or []:  # never erase strokes that ARE the content (wires, axes)
            x0, y0, x1, y1 = box_px(b, img.shape)
            thin[max(0, y0 - 3): y1 + 3, max(0, x0 - 3): x1 + 3] = 0
        mask = cv2.max(mask, cv2.dilate(thin, np.ones((3, 3), np.uint8)))
    if not mask.any():
        return img.copy()
    return cv2.inpaint(img, mask, 5, cv2.INPAINT_TELEA)


# ---------------------------------------------------------------- regions
def _largest_component(mask: np.ndarray) -> np.ndarray:
    n, lab, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    if n <= 1:
        return mask
    i = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    return np.where(lab == i, 255, 0).astype(np.uint8)


def _fill_holes(mask: np.ndarray) -> np.ndarray:
    cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    out = np.zeros_like(mask)
    cv2.drawContours(out, cnts, -1, 255, thickness=cv2.FILLED)
    return out


def _grabcut(img: np.ndarray, rect) -> np.ndarray:
    x0, y0, x1, y1 = rect
    h, w = img.shape[:2]
    pad = max(6, int(0.04 * max(x1 - x0, y1 - y0)))
    x0, y0 = max(1, x0 - pad), max(1, y0 - pad)
    x1, y1 = min(w - 2, x1 + pad), min(h - 2, y1 + pad)
    mask = np.zeros((h, w), np.uint8)
    bgd, fgd = np.zeros((1, 65), np.float64), np.zeros((1, 65), np.float64)
    cv2.grabCut(img, mask, (x0, y0, x1 - x0, y1 - y0), bgd, fgd, 4, cv2.GC_INIT_WITH_RECT)
    return np.where((mask == cv2.GC_FGD) | (mask == cv2.GC_PR_FGD), 255, 0).astype(np.uint8)


def _edge_hull(img: np.ndarray, rect) -> np.ndarray:
    """Fallback: filled outer contour of strong edges inside the box."""
    x0, y0, x1, y1 = rect
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150)
    sub = np.zeros_like(edges)
    sub[y0:y1, x0:x1] = edges[y0:y1, x0:x1]
    sub = cv2.dilate(sub, np.ones((5, 5), np.uint8))
    filled = _fill_holes(sub)
    if filled.sum() == 0:
        cv2.ellipse(filled, ((x0 + x1) // 2, (y0 + y1) // 2), ((x1 - x0) // 2, (y1 - y0) // 2), 0, 0, 360, 255, -1)
    return filled


class ColourRegions:
    """Flat-colour regions of a diagram (textbook figures fill each structure with one colour)."""

    def __init__(self, img: np.ndarray, k: int = 12):
        h, w = img.shape[:2]
        smooth = cv2.medianBlur(img, 5)
        lab = cv2.cvtColor(smooth, cv2.COLOR_BGR2LAB)
        small = cv2.resize(lab, (max(1, w // 3), max(1, h // 3)), interpolation=cv2.INTER_AREA)
        data = small.reshape(-1, 3).astype(np.float32)
        crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 1.0)
        k = min(k, max(2, len(np.unique(data, axis=0))))
        _, _, centers = cv2.kmeans(data, k, None, crit, 2, cv2.KMEANS_PP_CENTERS)
        flat = lab.reshape(-1, 3).astype(np.float32)
        d = ((flat[:, None, :] - centers[None, :, :]) ** 2).sum(-1)
        labels = d.argmin(1).reshape(h, w).astype(np.int32)
        dark = lab[:, :, 0] < 70  # outlines and text are boundaries, never regions
        labels[dark] = -1
        self.shape = (h, w)
        self.comps: list[tuple[np.ndarray, int, tuple]] = []  # (mask, area, bbox)
        min_area = 0.0008 * h * w
        for c in range(k):
            m = (labels == c).astype(np.uint8)
            n, lab_c, stats, _ = cv2.connectedComponentsWithStats(m, 4)
            for i in range(1, n):
                a = stats[i, cv2.CC_STAT_AREA]
                if a < min_area:
                    continue
                x, y, bw, bh = stats[i, :4]
                touches_edge = x <= 1 or y <= 1 or x + bw >= w - 1 or y + bh >= h - 1
                if touches_edge and a > 0.3 * h * w:
                    continue  # page background
                self.comps.append(((lab_c == i), int(a), (x, y, x + bw, y + bh)))

    def assign(self, rects: dict[str, tuple]) -> dict[str, np.ndarray]:
        """Superpixel-style assignment: each colour patch goes to the SMALLEST box that
        (almost) contains it. Shaded structures are rebuilt from their gradient bands,
        and neighbouring parts compete for patches instead of overlapping."""
        h, w = self.shape
        acc = {k: np.zeros((h, w), np.uint8) for k in rects}
        areas = {k: max(1, (r[2] - r[0]) * (r[3] - r[1])) for k, r in rects.items()}
        for m, a, (bx0, by0, bx1, by1) in self.comps:
            best, best_area = None, None
            for k, (x0, y0, x1, y1) in rects.items():
                if bx1 < x0 or bx0 > x1 or by1 < y0 or by0 > y1:
                    continue
                inside = int(m[y0:y1, x0:x1].sum())
                if inside / a >= 0.8 and (best is None or areas[k] < best_area):
                    best, best_area = k, areas[k]
            if best is not None:
                acc[best][m] = 255
        out = {}
        for k, mk in acc.items():
            if not mk.any():
                continue
            mk = cv2.morphologyEx(mk, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
            mk = _fill_holes(_largest_component(mk))
            if mk.sum() / 255 / areas[k] >= 0.2:
                out[k] = mk
        return out

    def best_for(self, rect) -> np.ndarray | None:
        x0, y0, x1, y1 = rect
        box_area = max(1, (x1 - x0) * (y1 - y0))
        best, best_score = None, 0.0
        for m, a, (bx0, by0, bx1, by1) in self.comps:
            if bx1 < x0 or bx0 > x1 or by1 < y0 or by0 > y1:
                continue
            inside = int(m[y0:y1, x0:x1].sum())
            frac_in, cover = inside / a, inside / box_area
            if frac_in < 0.7 or cover < 0.12:
                continue
            score = cover * (0.5 + 0.5 * frac_in)
            if score > best_score:
                best, best_score = m, score
        if best is None:
            return None
        mask = best.astype(np.uint8) * 255
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))  # bridge outline gaps
        mask = _fill_holes(_largest_component(mask))
        filled = mask.sum() / 255
        return mask if filled / box_area >= 0.2 else None


def segment_box(img: np.ndarray, rect, regions: ColourRegions | None = None,
                assigned: np.ndarray | None = None) -> tuple[np.ndarray, str]:
    """Return (binary mask of the object inside rect, method used)."""
    x0, y0, x1, y1 = rect
    box_area = max(1, (x1 - x0) * (y1 - y0))
    if assigned is not None:
        return assigned, "colour patches"
    colour = regions.best_for(rect) if regions is not None else None
    if colour is not None:
        return colour, "colour region"
    method = "grabcut"
    try:
        m = _grabcut(img, rect)
    except cv2.error:
        m = np.zeros(img.shape[:2], np.uint8)
    k = max(3, int(0.015 * max(x1 - x0, y1 - y0)) | 1)
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((k, k), np.uint8))  # cut leader lines
    m = _fill_holes(_largest_component(m))
    frac = m.sum() / 255 / box_area
    if frac < 0.2 or frac > 1.6:  # implausible -> fall back
        m = _fill_holes(_largest_component(_edge_hull(img, rect)))
        method = "edges"
    return m, method


def mask_to_polygon(mask: np.ndarray) -> Polygon | None:
    cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if not cnts:
        return None
    c = max(cnts, key=cv2.contourArea)
    if len(c) < 4:
        return None
    poly = Polygon(c[:, 0, :].astype(float)).buffer(0)
    if poly.geom_type == "MultiPolygon":
        poly = max(poly.geoms, key=lambda g: g.area)
    return Polygon(poly.exterior)


# ---------------------------------------------------------------- lines
def _skeleton_paths(skel: np.ndarray, min_len: int = 12) -> list[list[tuple[int, int]]]:
    ys, xs = np.nonzero(skel)
    pts = set(zip(xs.tolist(), ys.tolist()))
    G = nx.Graph()
    for x, y in pts:
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if (dx or dy) and (x + dx, y + dy) in pts:
                    G.add_edge((x, y), (x + dx, y + dy))
    paths = []
    for comp in nx.connected_components(G):
        sub = G.subgraph(comp)
        nodes = [n for n in sub if sub.degree(n) != 2] or [next(iter(sub))]
        visited = set()
        for s in nodes:
            for nb in sub.neighbors(s):
                e = frozenset((s, nb))
                if e in visited:
                    continue
                path = [s, nb]
                visited.add(e)
                prev, cur = s, nb
                while sub.degree(cur) == 2:
                    nxt = [n for n in sub.neighbors(cur) if n != prev][0]
                    e = frozenset((cur, nxt))
                    if e in visited:
                        break
                    visited.add(e)
                    path.append(nxt)
                    prev, cur = cur, nxt
                if len(path) >= min_len:
                    paths.append(path)
    return paths


def segment_line(img: np.ndarray, rect) -> MultiLineString | None:
    x0, y0, x1, y1 = rect
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, dark = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    sub = np.zeros_like(dark)
    sub[y0:y1, x0:x1] = dark[y0:y1, x0:x1]
    sub = cv2.morphologyEx(sub, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    skel = skeletonize(sub > 0)
    if skel.sum() > 40000:  # far too much ink for one line element: keep only the long strokes
        skel = skeletonize(cv2.morphologyEx(sub, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8)) > 0)
    paths = _skeleton_paths(skel)
    diag = float(np.hypot(x1 - x0, y1 - y0))
    min_len = max(10.0, 0.08 * diag if (x1 - x0) * (y1 - y0) > 0.3 * img.shape[0] * img.shape[1] else 10.0)
    lines = [LineString(p).simplify(1.5) for p in paths if len(p) >= 2]
    lines = [l for l in lines if l.length > min_len]
    return MultiLineString(lines) if lines else None


# ---------------------------------------------------------------- driver
def segment_elements(img: np.ndarray, analysis: dict) -> list[dict]:
    """Attach pixel-space geometry to each element of the analysis."""
    try:
        regions = ColourRegions(img)
        assigned = regions.assign({e["id"]: box_px(e["box_2d"], img.shape)
                                   for e in analysis["elements"] if e["kind"] == "region"})
    except (cv2.error, ValueError) as ex:
        log.warning("colour regions unavailable: %s", ex)
        regions, assigned = None, {}
    out = []
    for e in analysis["elements"]:
        try:
            item = _segment_one(img, e, regions, assigned.get(e["id"]))
        except Exception:  # one awkward element must never sink the whole page
            log.exception("could not trace %r", e.get("name"))
            item = None
        if item is not None:
            out.append(item)
    _clip_children_to_parents(out)
    return out


def _segment_one(img: np.ndarray, e: dict, regions: ColourRegions | None,
                 assigned: np.ndarray | None) -> dict | None:
    rect = box_px(e["box_2d"], img.shape)
    item = dict(e)
    if e["kind"] == "region":
        mask, method = segment_box(img, rect, regions, assigned)
        poly = mask_to_polygon(mask)
        if poly is None or poly.area < 30:
            return None
        item["geom"], item["method"] = poly, method
    elif e["kind"] == "line":
        lines = segment_line(img, rect)
        if lines is None:
            return None
        item["geom"], item["method"] = lines, "stroke skeleton"
    else:
        item["geom"], item["method"] = Point((rect[0] + rect[2]) / 2, (rect[1] + rect[3]) / 2), "box centre"
    return item


def _clip_children_to_parents(items: list[dict]) -> None:
    by_id = {i["id"]: i for i in items}
    for it in items:
        p = by_id.get(it.get("parent"))
        if p is not None and it["kind"] == "region" and p["kind"] == "region":
            clipped = it["geom"].intersection(p["geom"])
            if not clipped.is_empty and clipped.area > 0.5 * it["geom"].area:
                if clipped.geom_type == "MultiPolygon":
                    clipped = max(clipped.geoms, key=lambda g: g.area)
                if clipped.geom_type == "Polygon":
                    it["geom"] = clipped


def debug_overlay(img: np.ndarray, items: list[dict]) -> np.ndarray:
    vis = img.copy()
    for it in items:
        g = it["geom"]
        if g.geom_type == "Polygon":
            cv2.polylines(vis, [np.array(g.exterior.coords, np.int32)], True, (0, 0, 255), 3)
        elif g.geom_type == "MultiLineString":
            for l in g.geoms:
                cv2.polylines(vis, [np.array(l.coords, np.int32)], False, (255, 0, 0), 3)
        else:
            cv2.circle(vis, (int(g.x), int(g.y)), 8, (0, 160, 0), -1)
    return vis


