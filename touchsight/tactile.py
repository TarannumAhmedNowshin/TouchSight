"""Tactile design layer.

Turns segmented pixel geometry into a physically-sized tactile graphic that
follows tactile-graphics design guidance:
  * minimum element size 1/4" (6.35 mm) and minimum separation 1/8" (3.175 mm)
  * clearly different textures on neighbouring areas (graph colouring)
  * blank "dead zones" between textures, outlines and labels
  * braille labels, or key letters + a key when a label will not fit
  * a validator that scores readability and auto-fixes what it can
All coordinates in this module are millimetres on an A4 landscape page.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import shapely
from shapely import affinity
from shapely.geometry import LineString, MultiLineString, Point, Polygon, box
from shapely.ops import polylabel, unary_union

from . import braille as br

# ------------------------------------------------------------------ constants
PAGE_W, PAGE_H = 297.0, 210.0
MARGIN = 12.0
KEY_W = 95.0
TITLE_H = 14.0
MIN_SIZE = 6.35      # 1/4 inch
MIN_GAP = 3.175      # 1/8 inch
OUTLINE_W = 1.0
TEXTURE_W = 0.5
LEADER_W = 0.6
POINT_R = 2.6
LABEL_CLEAR = 1.6    # blank space kept around braille labels
TEXTURES = ["dots", "diagonal", "crosshatch", "horizontal", "vertical", "grid"]
TEXTURE_NAMES = {
    "dots": "dots", "diagonal": "diagonal lines", "crosshatch": "crosshatch",
    "horizontal": "horizontal lines", "vertical": "vertical lines", "grid": "grid", "none": "plain",
}

DRAW_BOX = (MARGIN, MARGIN + TITLE_H, PAGE_W - MARGIN - KEY_W - 6, PAGE_H - MARGIN)
KEY_X = PAGE_W - MARGIN - KEY_W


@dataclass
class Issue:
    code: str
    severity: str  # "error" | "warning"
    message: str
    ids: list[str] = field(default_factory=list)
    at: tuple[float, float] | None = None
    fixed: bool = False
    fix: str = ""

    def as_dict(self):
        return {"code": self.code, "severity": self.severity, "message": self.message, "ids": self.ids,
                "at": [round(self.at[0], 1), round(self.at[1], 1)] if self.at else None,
                "fixed": self.fixed, "fix": self.fix}


@dataclass
class Label:
    ids: list[str]
    text: str          # braille source text
    ink: str           # print text for sighted helpers
    kind: str          # "word" | "key"
    x: float
    y: float
    leader: LineString | None = None

    @property
    def w(self):
        return br.width_mm(self.text)

    @property
    def rect(self):
        return box(self.x, self.y, self.x + self.w, self.y + br.CELL_H)


@dataclass
class Scene:
    title: str
    summary: str
    elements: list[dict]
    labels: list[Label] = field(default_factory=list)
    key_rows: list[dict] = field(default_factory=list)
    issues_before: list[Issue] = field(default_factory=list)
    issues_after: list[Issue] = field(default_factory=list)
    fixes: list[str] = field(default_factory=list)
    dropped: list[dict] = field(default_factory=list)
    scale: float = 1.0


# ------------------------------------------------------------------ helpers
def _largest(g):
    if g.is_empty:
        return g
    if g.geom_type == "MultiPolygon":
        return max(g.geoms, key=lambda p: p.area)
    if g.geom_type == "GeometryCollection":
        polys = [p for p in g.geoms if p.geom_type == "Polygon"]
        return max(polys, key=lambda p: p.area) if polys else Polygon()
    return g


def _chaikin(coords, iters=2):
    pts = np.asarray(coords[:-1], float)
    for _ in range(iters):
        nxt = np.roll(pts, -1, axis=0)
        q = 0.75 * pts + 0.25 * nxt
        r = 0.25 * pts + 0.75 * nxt
        pts = np.empty((2 * len(q), 2))
        pts[0::2], pts[1::2] = q, r
    return pts


def _clean_poly(p: Polygon) -> Polygon:
    p = p.simplify(0.4)
    size = math.sqrt(max(p.area, 1e-6))
    r = min(4.0, max(0.8, 0.05 * size))  # strip leader-line stubs and specks, scaled to the shape
    opened = _largest(p.buffer(-r).buffer(r))
    if not opened.is_empty and opened.area > 0.5 * p.area:
        p = opened
    p = _largest(p.buffer(0.8).buffer(-0.8))
    if p.is_empty:
        return p
    p = Polygon(p.exterior).simplify(0.6)
    sm = Polygon(_chaikin(list(p.exterior.coords))).buffer(0)
    return Polygon(_largest(sm).exterior).simplify(0.15) if not sm.is_empty else p


def _too_small(p: Polygon) -> bool:
    return p.buffer(-MIN_SIZE / 2 + 0.05).is_empty


def _regions(els):
    return [e for e in els if e["kind"] == "region"]


def _by_id(els):
    return {e["id"]: e for e in els}


# ------------------------------------------------------------------ transform
def to_page(items: list[dict], img_shape) -> tuple[list[dict], float]:
    geoms = [i["geom"] for i in items]
    if not geoms:
        raise ValueError("nothing to draw")
    minx, miny, maxx, maxy = unary_union(geoms).bounds
    pad = 0.03 * max(maxx - minx, maxy - miny)
    minx, miny, maxx, maxy = minx - pad, miny - pad, maxx + pad, maxy + pad
    bx0, by0, bx1, by1 = DRAW_BOX
    s = min((bx1 - bx0) / (maxx - minx), (by1 - by0) / (maxy - miny))
    ox = bx0 + ((bx1 - bx0) - s * (maxx - minx)) / 2
    oy = by0 + ((by1 - by0) - s * (maxy - miny)) / 2
    out = []
    for it in items:
        g = affinity.affine_transform(it["geom"], [s, 0, 0, s, ox - s * minx, oy - s * miny])
        e = dict(it)
        if e["kind"] == "region":
            g = _clean_poly(g)
            if g.is_empty:
                continue
        elif e["kind"] == "line":
            g = g.simplify(0.4)
        e["geom"] = g
        out.append(e)
    return out, s


# ------------------------------------------------------------------ validator
def validate(els: list[dict], labels: list[Label] | None = None, three_d: bool = False) -> list[Issue]:
    issues: list[Issue] = []
    regs = _regions(els)
    ids = _by_id(els)
    for r in regs:
        p = r["geom"]
        if _too_small(p):
            issues.append(Issue("too_small", "error",
                                f"'{r['name']}' is smaller than 1/4 inch and cannot be felt as a shape.",
                                [r["id"]], (p.centroid.x, p.centroid.y)))
        par = ids.get(r.get("parent"))
        if par is not None and par["kind"] == "region":
            d = par["geom"].exterior.distance(p)
            if d < MIN_GAP:
                issues.append(Issue("crowded_edge", "error",
                                    f"'{r['name']}' is only {d:.1f} mm from the edge of '{par['name']}' (needs 3.2 mm).",
                                    [r["id"], par["id"]], tuple(p.exterior.interpolate(p.exterior.project(par['geom'].exterior.centroid)).coords[0])))
    for i, a in enumerate(regs):
        for b in regs[i + 1:]:
            if a.get("parent") != b.get("parent"):
                continue
            pa, pb = a["geom"], b["geom"]
            if pa.intersection(pb).area > 0.5:
                issues.append(Issue("overlap", "error", f"'{a['name']}' and '{b['name']}' overlap.",
                                    [a["id"], b["id"]], tuple(pa.intersection(pb).centroid.coords[0])))
                continue
            d = pa.distance(pb)
            if 0 < d < MIN_GAP:
                pt = shapely.shortest_line(pa, pb).centroid
                issues.append(Issue("too_close", "error",
                                    f"'{a['name']}' and '{b['name']}' are {d:.1f} mm apart; fingers need 3.2 mm.",
                                    [a["id"], b["id"]], (pt.x, pt.y)))
    for e in els:
        if e["kind"] == "line":
            short = [l for l in e["geom"].geoms if l.length < MIN_SIZE]
            if short:
                issues.append(Issue("short_lines", "warning",
                                    f"'{e['name']}' has {len(short)} line pieces under 1/4 inch.", [e["id"]]))
    n = len({e["name"] for e in els})
    if n > 10:
        issues.append(Issue("clutter", "warning", f"{n} different elements; tactile graphics read best with 10 or fewer."))
    tex = {}
    for r in regs:
        if r.get("texture") and r["texture"] != "none":
            tex.setdefault(r["texture"], set()).add(r["name"])
    for t, names in tex.items():
        if len(names) > 1:
            issues.append(Issue("texture_reuse", "warning", f"Texture '{t}' is used for different things: {', '.join(sorted(names))}."))
    if len(tex) > len(TEXTURES):
        issues.append(Issue("too_many_textures", "warning", "More than 5 textures; readers struggle to tell them apart."))
    if labels is not None:
        geoms = [e["geom"] for e in els]
        for L in labels:
            if L.x < 0 or L.y < 0 or L.x + L.w > PAGE_W or L.y + br.CELL_H > PAGE_H:
                issues.append(Issue("label_off_page", "error", f"Label '{L.ink}' runs off the page.", L.ids))
            for g in geoms:
                edge = g.exterior if g.geom_type == "Polygon" else g
                if L.rect.distance(edge) < 1.0:
                    issues.append(Issue("label_collision", "warning",
                                        f"Braille label '{L.ink}' touches a line.", L.ids, (L.x, L.y)))
                    break
    if three_d:
        issues.append(Issue("perspective", "warning",
                            "The original uses a 3-D view; tactile readers do better with a flat side or top view."))
    return issues


def score(issues: list[Issue]) -> int:
    s = 100
    for i in issues:
        if i.fixed:
            continue
        s -= 12 if i.severity == "error" else 5
    return max(0, s)


# ------------------------------------------------------------------ auto-fix
def autofix(els: list[dict], issues: list[Issue]) -> tuple[list[dict], list[str]]:
    fixes: list[str] = []
    ids = _by_id(els)
    drop: set[str] = set()
    for iss in issues:
        if iss.code == "too_small":
            e = ids[iss.ids[0]]
            if e["importance"] <= 1:
                drop.add(e["id"])
                iss.fixed, iss.fix = True, "removed (optional detail)"
            else:
                p = e["geom"]
                for f in (1.25, 1.5, 1.8, 2.2, 2.7, 3.2):
                    q = affinity.scale(p, f, f, origin="centroid")
                    if not _too_small(q):
                        par = ids.get(e.get("parent"))
                        if par is not None and par["kind"] == "region":
                            q = _largest(q.intersection(par["geom"].buffer(-MIN_GAP - 0.3)))
                        if not q.is_empty and not _too_small(q):
                            e["geom"] = q
                            iss.fixed, iss.fix = True, f"enlarged {f:.2g}x"
                            break
        elif iss.code == "crowded_edge":
            e, par = ids[iss.ids[0]], ids[iss.ids[1]]
            q = _largest(e["geom"].intersection(par["geom"].buffer(-MIN_GAP - 0.4)))
            if not q.is_empty and q.area > 0.55 * e["geom"].area:
                e["geom"] = Polygon(q.exterior)
                iss.fixed, iss.fix = True, "trimmed to keep a 1/8 inch gap from the outline"
            else:  # move it inwards instead
                c = par["geom"].centroid
                pc = e["geom"].centroid
                for t in (0.1, 0.2, 0.3, 0.4):
                    q = affinity.translate(e["geom"], (c.x - pc.x) * t, (c.y - pc.y) * t)
                    if par["geom"].exterior.distance(q) >= MIN_GAP and par["geom"].contains(q):
                        e["geom"] = q
                        iss.fixed, iss.fix = True, "moved inwards"
                        break
        elif iss.code in ("too_close", "overlap"):
            a, b = ids[iss.ids[0]], ids[iss.ids[1]]
            small, big = (a, b) if a["geom"].area < b["geom"].area else (b, a)
            q = _largest(small["geom"].difference(big["geom"].buffer(MIN_GAP + 0.3)))
            if not q.is_empty and q.area > 0.55 * small["geom"].area and not _too_small(q):
                small["geom"] = Polygon(q.exterior)
                iss.fixed, iss.fix = True, f"trimmed '{small['name']}' to open a 1/8 inch gap"
            else:
                # give the shared area to the smaller, more specific part: cut it out of the larger one
                q2 = _largest(big["geom"].difference(small["geom"].buffer(MIN_GAP + 0.3)))
                if not q2.is_empty and q2.area > 0.5 * big["geom"].area and not _too_small(q2):
                    big["geom"] = Polygon(q2.exterior)
                    iss.fixed, iss.fix = True, f"trimmed '{big['name']}' around '{small['name']}'"
                elif small["importance"] < big["importance"]:
                    drop.add(small["id"])
                    iss.fixed, iss.fix = True, f"removed less important '{small['name']}'"
        elif iss.code == "short_lines":
            e = ids[iss.ids[0]]
            keep = [l for l in e["geom"].geoms if l.length >= MIN_SIZE]
            if keep:
                e["geom"] = MultiLineString(keep)
            else:
                drop.add(e["id"])
            iss.fixed, iss.fix = True, "removed line pieces too short to trace"
        if iss.fixed:
            fixes.append(f"{iss.message} → {iss.fix}")
    kept = [e for e in els if e["id"] not in drop]
    for e in kept:
        if e.get("parent") in drop:
            e["parent"] = None
    return kept, fixes


# ------------------------------------------------------------------ textures
def assign_textures(els: list[dict]) -> None:
    regs = _regions(els)
    if not regs:
        return
    total = unary_union([r["geom"] for r in regs]).area
    groups: dict[str, list[dict]] = {}
    for r in regs:
        r["texture"] = None
        has_children = any(o.get("parent") == r["id"] for o in regs)
        if has_children and r["geom"].area > 0.3 * total:
            r["texture"] = "none"  # large container: outline only, keeps the page calm
        else:
            groups.setdefault(r["name"], []).append(r)
    names = list(groups)

    def adjacent(ga, gb):
        for a in ga:
            for b in gb:
                if a["geom"].distance(b["geom"]) < 2 * MIN_GAP or a.get("parent") == b["id"] or b.get("parent") == a["id"]:
                    return True
        return False

    adj = {n: {m for m in names if m != n and adjacent(groups[n], groups[m])} for n in names}
    order = sorted(names, key=lambda n: (-max(r["importance"] for r in groups[n]), -sum(r["geom"].area for r in groups[n])))
    chosen: dict[str, str] = {}
    usage = {t: 0 for t in TEXTURES}
    for n in order:
        taken = {chosen[m] for m in adj[n] if m in chosen}
        free = [t for t in TEXTURES if t not in taken]
        # prefer an unused texture (so one texture = one meaning), strongest first
        unused = [t for t in free if usage[t] == 0]
        neighbour_plain = any(chosen.get(m) == "none" for m in adj[n]) or any(
            o.get("texture") == "none" and any(r["geom"].distance(o["geom"]) < 2 * MIN_GAP for r in groups[n]) for o in regs)
        if unused:
            t = unused[0]
        elif not neighbour_plain:
            t = "none"  # out of distinct textures: leave it plain rather than give one texture two meanings
        else:
            t = (free or TEXTURES)[0]
        chosen[n] = t
        usage[t] = usage.get(t, 0) + 1
        for r in groups[n]:
            r["texture"] = t


def texture_primitives(texture: str, area) -> dict:
    """Return {'dots': [(x,y)], 'lines': [LineString]} filling `area`."""
    out = {"dots": [], "lines": []}
    if area.is_empty or texture in (None, "none"):
        return out
    minx, miny, maxx, maxy = area.bounds
    if texture == "dots":
        step = 3.4
        xs, ys = [], []
        for j, y in enumerate(np.arange(miny, maxy + step, step)):
            off = step / 2 if j % 2 else 0
            for x in np.arange(minx + off, maxx + step, step):
                xs.append(x)
                ys.append(y)
        pts = shapely.points(np.array(xs), np.array(ys))
        inside = shapely.contains(area.buffer(-0.8), pts)
        out["dots"] = [(p.x, p.y) for p, ok in zip(pts, inside) if ok]
        return out
    specs = {"diagonal": [(45, 3.6)], "crosshatch": [(45, 4.6), (-45, 4.6)],
             "horizontal": [(0, 3.2)], "vertical": [(90, 3.2)], "grid": [(0, 4.6), (90, 4.6)]}[texture]
    cx, cy = (minx + maxx) / 2, (miny + maxy) / 2
    R = math.hypot(maxx - minx, maxy - miny) / 2 + 5
    for ang, step in specs:
        a = math.radians(ang)
        dx, dy = math.cos(a), math.sin(a)
        nx_, ny_ = -dy, dx
        for k in np.arange(-R, R, step):
            px, py = cx + nx_ * k, cy + ny_ * k
            ln = LineString([(px - dx * R, py - dy * R), (px + dx * R, py + dy * R)])
            seg = ln.intersection(area)
            if seg.is_empty:
                continue
            parts = seg.geoms if hasattr(seg, "geoms") else [seg]
            out["lines"].extend(p for p in parts if p.geom_type == "LineString" and p.length > 2.5)
    return out


# ------------------------------------------------------------------ labels
def _short_keys(names: list[str]) -> dict[str, str]:
    keys, used = {}, set()
    for n in names:
        letters = [c for c in n.lower() if c.isalpha()] or ["x"]
        cand = [letters[0]] + [letters[0] + c for c in letters[1:]] + [letters[0] + str(i) for i in range(2, 10)]
        for k in cand:
            if k not in used:
                keys[n] = k
                used.add(k)
                break
    return keys


def _fit_rect(free, w: float, h: float, target: Point | None = None):
    """Find a w×h rectangle fully inside `free`, nearest to target."""
    if free.is_empty:
        return None
    minx, miny, maxx, maxy = free.bounds
    if maxx - minx < w or maxy - miny < h:
        return None
    step = max(1.0, min(w, h) / 3)
    xs = np.arange(minx, maxx - w + 0.01, step)
    ys = np.arange(miny, maxy - h + 0.01, step)
    if len(xs) == 0 or len(ys) == 0:
        return None
    X, Y = np.meshgrid(xs, ys)
    X, Y = X.ravel(), Y.ravel()
    rects = shapely.box(X, Y, X + w, Y + h)
    ok = shapely.contains(free, rects)
    if not ok.any():
        return None
    if target is None:
        target = free.centroid
    cx, cy = X + w / 2, Y + h / 2
    dist = (cx - target.x) ** 2 + (cy - target.y) ** 2
    dist[~ok] = np.inf
    i = int(np.argmin(dist))
    return float(X[i]), float(Y[i])


def place_labels(els: list[dict]) -> tuple[list[Label], dict[str, str]]:
    regs = _regions(els)
    labels: list[Label] = []
    keys = _short_keys(list(dict.fromkeys(e["name"] for e in els)))
    used_keys: dict[str, str] = {}
    draw_area = box(*DRAW_BOX)
    edges = unary_union([e["geom"].exterior if e["geom"].geom_type == "Polygon" else e["geom"] for e in els])
    obstacles = edges.buffer(MIN_GAP)
    h = br.CELL_H

    def taken():
        return unary_union([L.rect.buffer(2.5) for L in labels]) if labels else Polygon()

    order = sorted(els, key=lambda e: (e["geom"].area if e["kind"] == "region" else 0))
    for e in order:
        g = e["geom"]
        if e["kind"] == "region":
            children = [o["geom"] for o in regs if o.get("parent") == e["id"]]
            free = g.buffer(-(OUTLINE_W / 2 + LABEL_CLEAR + 0.5))
            if children:
                free = free.difference(unary_union(children).buffer(MIN_GAP + 0.5))
            free = free.difference(taken())
            target = polylabel(_largest(free), 0.5) if not free.is_empty and _largest(free).geom_type == "Polygon" else g.centroid
            pos = _fit_rect(free, br.width_mm(e["name"]), h, target)
            if pos:
                labels.append(Label([e["id"]], e["name"], e["name"], "word", *pos))
                continue
            k = keys[e["name"]]
            pos = _fit_rect(free, br.width_mm(k), h, target)
            if pos:
                labels.append(Label([e["id"]], k, e["name"], "key", *pos))
                used_keys[e["name"]] = k
                continue
        # outside placement with a leader line (lines, points, tiny regions)
        k = keys[e["name"]]
        w = br.width_mm(k)
        anchor = g.centroid if e["kind"] != "line" else g.interpolate(0.5, normalized=True) if g.geom_type == "LineString" else max(g.geoms, key=lambda l: l.length).interpolate(0.5, normalized=True)
        best = None
        for clearance in (MIN_GAP, 1.8):  # relax to a tighter gap only if the page is crowded
            blocked = edges.buffer(clearance).union(taken())
            for dist in (5, 8, 11, 15, 20, 26, 32):
                for ang in range(0, 360, 15):
                    ca, sa = math.cos(math.radians(ang)), math.sin(math.radians(ang))
                    if e["kind"] == "region":
                        ring_pt = g.exterior.interpolate(g.exterior.project(Point(anchor.x + ca * 50, anchor.y + sa * 50)))
                        cx, cy = ring_pt.x + ca * dist, ring_pt.y + sa * dist
                    else:
                        cx, cy = anchor.x + ca * dist, anchor.y + sa * dist
                    r = box(cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)
                    if draw_area.contains(r) and not r.intersects(blocked):
                        best = (cx - w / 2, cy - h / 2)
                        break
                if best:
                    break
            if best:
                break
        if best is None:
            best = (anchor.x + 4, anchor.y + 4)
        L = Label([e["id"]], k, e["name"], "key", *best)
        target_geom = g.exterior if e["kind"] == "region" else g
        start = Point(best[0] + w / 2, best[1] + h / 2)
        end = target_geom.interpolate(target_geom.project(start)) if e["kind"] != "point" else g
        ln = LineString([start, end])
        ln = ln.difference(L.rect.buffer(1.2))
        if not ln.is_empty and ln.length > 1.5:
            L.leader = ln if ln.geom_type == "LineString" else max(ln.geoms, key=lambda q: q.length)
        labels.append(L)
        used_keys[e["name"]] = k
    return labels, used_keys


def build_key(els: list[dict], used_keys: dict[str, str]) -> list[dict]:
    rows, seen = [], set()
    for e in sorted(els, key=lambda e: -e["importance"]):
        if e["name"] in seen:
            continue
        seen.add(e["name"])
        tex = e.get("texture") if e["kind"] == "region" else None
        if e["name"] in used_keys or (tex and tex != "none"):
            rows.append({"name": e["name"], "key": used_keys.get(e["name"]),
                         "texture": tex if tex and tex != "none" else None, "kind": e["kind"]})
    return rows


# ------------------------------------------------------------------ driver
def design(items_px: list[dict], analysis: dict, img_shape) -> Scene:
    els, s = to_page(items_px, img_shape)
    scene = Scene(analysis.get("title") or "diagram", analysis.get("summary", ""), els,
                  dropped=analysis.get("dropped", []), scale=s)
    before = validate(els, three_d=analysis.get("is_3d_perspective", False))
    scene.issues_before = before  # autofix marks which ones it resolved
    els, fixes = autofix(els, before)
    # second pass: fixes can create new conflicts
    for _ in range(2):
        els, more = autofix(els, validate(els))
        fixes += more
        if not more:
            break
    scene.fixes = fixes
    assign_textures(els)
    labels, used = place_labels(els)
    scene.elements, scene.labels = els, labels
    scene.key_rows = build_key(els, used)
    scene.issues_after = validate(els, labels, analysis.get("is_3d_perspective", False))
    return scene


def texture_area(e: dict, scene: Scene):
    """The region minus dead zones around its outline, children and labels."""
    g = e["geom"]
    area = g.buffer(-(OUTLINE_W / 2 + 1.2))
    kids = [o["geom"] for o in scene.elements if o.get("parent") == e["id"] and o["kind"] == "region"]
    if kids:
        area = area.difference(unary_union(kids).buffer(MIN_GAP))
    labs = [L.rect.buffer(LABEL_CLEAR) for L in scene.labels]
    if labs:
        area = area.difference(unary_union(labs))
    lines = [o["geom"] for o in scene.elements if o["kind"] == "line"]
    if lines:
        area = area.difference(unary_union(lines).buffer(MIN_GAP))
    return area
