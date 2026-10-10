"""Exporters: print-ready SVG (swell paper / embosser), preview SVG, heightmap, STL."""
from __future__ import annotations

import io
from xml.sax.saxutils import escape

import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from shapely.geometry import box

from . import braille as br
from .tactile import (KEY_X, LEADER_W, MARGIN, OUTLINE_W, PAGE_H, PAGE_W, POINT_R, TEXTURE_NAMES,
                      TEXTURE_W, Scene, texture_area, texture_primitives)

KEY_COLS = 11  # braille cells per key line


def _wrap(word: str, n: int) -> list[str]:
    out, cur = [], ""
    for w in word.split():
        if len(cur) + len(w) + (1 if cur else 0) <= n:
            cur = f"{cur} {w}".strip()
        else:
            if cur:
                out.append(cur)
            while len(w) > n:
                out.append(w[: n - 1] + "-")
                w = w[n - 1:]
            cur = w
    if cur:
        out.append(cur)
    return out or [""]


def primitives(scene: Scene) -> dict:
    """Flatten the scene into drawable primitives (mm): shared by SVG + heightmap."""
    P = {"outlines": [], "tex_lines": [], "tex_dots": [], "lines": [], "points": [],
         "braille": [], "leaders": [], "ink": [], "dividers": []}
    els = sorted(scene.elements, key=lambda e: -e["geom"].area if e["kind"] == "region" else 0)
    for e in els:
        g = e["geom"]
        if e["kind"] == "region":
            tex = texture_primitives(e.get("texture"), texture_area(e, scene))
            P["tex_lines"] += [list(l.coords) for l in tex["lines"]]
            P["tex_dots"] += tex["dots"]
            P["outlines"].append({"id": e["id"], "coords": list(g.exterior.coords)})
        elif e["kind"] == "line":
            P["lines"] += [list(l.coords) for l in g.geoms]
        else:
            P["points"].append((g.x, g.y))
    for L in scene.labels:
        P["braille"] += br.dots(L.text, L.x, L.y)
        P["ink"].append((L.x, L.y + br.CELL_H + 3.2, L.ink if L.kind == "word" else f"{L.text} = {L.ink}"))
        if L.leader is not None:
            P["leaders"].append(list(L.leader.coords))
    # title
    P["braille"] += br.dots(scene.title, MARGIN, MARGIN - 2)
    P["ink"].append((MARGIN, MARGIN + br.CELL_H + 1.5, scene.title))
    # key panel
    if scene.key_rows:
        x0 = KEY_X
        P["dividers"].append([(x0 - 4, MARGIN + 12), (x0 - 4, PAGE_H - MARGIN)])
        y = MARGIN + 12
        P["braille"] += br.dots("key", x0, y)
        P["ink"].append((x0, y + br.CELL_H + 3, "KEY"))
        y += br.LINE_PITCH + 2
        for row in scene.key_rows:
            if y > PAGE_H - MARGIN - 8:
                break
            if row["texture"]:
                sw = box(x0, y - 0.3, x0 + 10, y + 7)
                tex = texture_primitives(row["texture"], sw.buffer(-1.0))
                P["tex_lines"] += [list(l.coords) for l in tex["lines"]]
                P["tex_dots"] += tex["dots"]
                P["outlines"].append({"id": "swatch", "coords": list(sw.exterior.coords)})
            if row["key"]:
                P["braille"] += br.dots(row["key"], x0 + 13, y)
            lines = _wrap(row["name"], KEY_COLS)
            for i, ln in enumerate(lines):
                P["braille"] += br.dots(ln, x0 + 13 + 2 * br.CELL_PITCH + 0.5, y + i * br.LINE_PITCH)
            tex_note = f" ({TEXTURE_NAMES[row['texture']]})" if row["texture"] else ""
            P["ink"].append((x0 + 13, y + br.CELL_H + 2.6,
                             f"{row['key'] + ' = ' if row['key'] else ''}{row['name']}{tex_note}"))
            y += br.LINE_PITCH * len(lines) + 3
    return P


# ------------------------------------------------------------------ SVG
def _path(coords, close=False):
    s = "M" + " L".join(f"{x:.2f} {y:.2f}" for x, y in coords)
    return s + (" Z" if close else "")


def to_svg(scene: Scene, mode: str = "print") -> str:
    """mode='print': black only, ready for swell paper. mode='preview': adds ink labels + ids."""
    P = primitives(scene)
    preview = mode == "preview"
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{PAGE_W}mm" height="{PAGE_H}mm" '
         f'viewBox="0 0 {PAGE_W} {PAGE_H}">',
         f'<rect width="{PAGE_W}" height="{PAGE_H}" fill="#fff"/>']
    if P["tex_lines"]:
        o.append(f'<path class="tex" d="{" ".join(_path(c) for c in P["tex_lines"])}" '
                 f'stroke="#000" stroke-width="{TEXTURE_W}" fill="none" stroke-linecap="round"/>')
    if P["tex_dots"]:
        o.append('<g class="tex" fill="#000">' + "".join(
            f'<circle cx="{x:.2f}" cy="{y:.2f}" r="0.75"/>' for x, y in P["tex_dots"]) + "</g>")
    for ol in P["outlines"]:
        o.append(f'<path class="outline" data-id="{ol["id"]}" d="{_path(ol["coords"], True)}" stroke="#000" '
                 f'stroke-width="{OUTLINE_W}" fill="none" stroke-linejoin="round"/>')
    for c in P["lines"]:
        o.append(f'<path class="line" d="{_path(c)}" stroke="#000" stroke-width="{OUTLINE_W}" fill="none" '
                 f'stroke-linecap="round" stroke-linejoin="round"/>')
    for x, y in P["points"]:
        o.append(f'<circle class="point" cx="{x:.2f}" cy="{y:.2f}" r="{POINT_R}" fill="#000"/>')
    for c in P["leaders"] + P["dividers"]:
        o.append(f'<path class="leader" d="{_path(c)}" stroke="#000" stroke-width="{LEADER_W}" fill="none"/>')
    if P["braille"]:
        o.append('<g class="braille" fill="#000">' + "".join(
            f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{br.DOT_R}"/>' for x, y in P["braille"]) + "</g>")
    if preview:
        o.append('<g class="ink" fill="#0b7a75" font-family="Helvetica, Arial, sans-serif" font-size="3.2">' + "".join(
            f'<text x="{x:.2f}" y="{y:.2f}">{escape(t)}</text>' for x, y, t in P["ink"]) + "</g>")
    o.append("</svg>")
    return "\n".join(o)


# ------------------------------------------------------------------ heightmap
def heightmap(scene: Scene, px_per_mm: int = 4) -> np.ndarray:
    """Greyscale relief: 0 = paper, 255 = highest. Same geometry as the SVG."""
    P = primitives(scene)
    W, H = int(PAGE_W * px_per_mm), int(PAGE_H * px_per_mm)
    im = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(im)
    s = px_per_mm

    def pts(c):
        return [(x * s, y * s) for x, y in c]

    for c in P["tex_lines"]:
        d.line(pts(c), fill=150, width=max(1, round(TEXTURE_W * s)))
    for x, y in P["tex_dots"]:
        r = 0.75 * s
        d.ellipse((x * s - r, y * s - r, x * s + r, y * s + r), fill=160)
    for c in P["leaders"] + P["dividers"]:
        d.line(pts(c), fill=190, width=max(1, round(LEADER_W * s)))
    for ol in P["outlines"]:
        d.line(pts(ol["coords"]), fill=235, width=max(2, round(OUTLINE_W * s)), joint="curve")
    for c in P["lines"]:
        d.line(pts(c), fill=235, width=max(2, round(OUTLINE_W * s)), joint="curve")
    for x, y in P["points"]:
        r = POINT_R * s
        d.ellipse((x * s - r, y * s - r, x * s + r, y * s + r), fill=235)
    im = im.filter(ImageFilter.GaussianBlur(0.35 * s))
    # braille dots as domes (drawn after blur so they stay crisp)
    dome = Image.new("L", (W, H), 0)
    dd = ImageDraw.Draw(dome)
    for x, y in P["braille"]:
        for k, v in ((1.0, 140), (0.7, 200), (0.4, 255)):
            r = br.DOT_R * s * k
            dd.ellipse((x * s - r, y * s - r, x * s + r, y * s + r), fill=v)
    arr = np.maximum(np.asarray(im), np.asarray(dome))
    return arr


def png_bytes(arr: np.ndarray) -> bytes:
    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, "PNG", optimize=True)
    return buf.getvalue()


# ------------------------------------------------------------------ STL
def to_stl(hm: np.ndarray, px_per_mm: int = 4, target_px_per_mm: int = 2,
           base_mm: float = 1.6, relief_mm: float = 0.9) -> bytes:
    """Watertight binary STL of a tactile tile (A4 at 1:1 scale)."""
    f = max(1, px_per_mm // target_px_per_mm)
    h = hm[::-1, :].astype(np.float32)  # flip y so the tile reads correctly when printed face up
    h = h[: h.shape[0] // f * f, : h.shape[1] // f * f].reshape(h.shape[0] // f, f, h.shape[1] // f, f).max(axis=(1, 3))
    rows, cols = h.shape
    step = 1.0 / (px_per_mm / f)
    z = base_mm + h / 255.0 * relief_mm
    xs = np.arange(cols) * step
    ys = np.arange(rows) * step
    X, Y = np.meshgrid(xs, ys)
    top = np.stack([X, Y, z], -1)
    bot = np.stack([X, Y, np.zeros_like(z)], -1)

    def quads(a, b, c, d):  # two triangles per quad, arrays (...,3)
        return np.concatenate([np.stack([a, b, c], -2).reshape(-1, 3, 3), np.stack([a, c, d], -2).reshape(-1, 3, 3)])

    tris = [
        quads(top[:-1, :-1], top[:-1, 1:], top[1:, 1:], top[1:, :-1]),
        quads(bot[:-1, :-1], bot[1:, :-1], bot[1:, 1:], bot[:-1, 1:]),
        # side walls
        quads(bot[0, :-1], bot[0, 1:], top[0, 1:], top[0, :-1]),
        quads(bot[-1, 1:], bot[-1, :-1], top[-1, :-1], top[-1, 1:]),
        quads(bot[1:, 0], bot[:-1, 0], top[:-1, 0], top[1:, 0]),
        quads(bot[:-1, -1], bot[1:, -1], top[1:, -1], top[:-1, -1]),
    ]
    T = np.concatenate(tris).astype(np.float32)
    n = np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0])
    n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-9
    header = b"TouchSight tactile tile".ljust(80, b" ")
    rec = np.zeros(len(T), dtype=[("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")])
    rec["n"], rec["v"] = n, T
    return header + np.uint32(len(T)).tobytes() + rec.tobytes()
