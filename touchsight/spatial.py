"""Spatial language for a tactile page: where things are, in words a reader can follow by touch.

Conventions: "top" is the edge of the sheet farthest from the reader; distances are given in
centimetres and finger-widths (about 1.6 cm), the units teachers use when guiding a hand.
"""
from __future__ import annotations

import math

from shapely.geometry import Point

from .tactile import DRAW_BOX, TEXTURE_NAMES, Scene

FINGER_CM = 1.6


def page_position(x: float, y: float) -> str:
    """Coarse 3x3 position inside the drawing area."""
    x0, y0, x1, y1 = DRAW_BOX
    col = min(2, max(0, int(3 * (x - x0) / (x1 - x0))))
    row = min(2, max(0, int(3 * (y - y0) / (y1 - y0))))
    names = [["top left", "top", "top right"], ["left", "centre", "right"], ["bottom left", "bottom", "bottom right"]]
    return names[row][col]


def direction(from_xy: tuple[float, float], to_xy: tuple[float, float]) -> str:
    """Where `to` lies relative to `from` (page coordinates: y grows downwards)."""
    dx, dy = to_xy[0] - from_xy[0], from_xy[1] - to_xy[1]
    if math.hypot(dx, dy) < 4:
        return "at the same place as"
    angle = (math.degrees(math.atan2(dy, dx)) + 360) % 360
    words = ["to the right of", "up and to the right of", "above", "up and to the left of",
             "to the left of", "down and to the left of", "below", "down and to the right of"]
    return words[int(((angle + 22.5) % 360) // 45)]


def distance_words(mm: float) -> str:
    if mm < 5:
        return "almost touching"
    cm = mm / 10
    fingers = max(1, round(cm / FINGER_CM))
    return f"about {cm:.0f} cm ({fingers} finger-width{'s' if fingers != 1 else ''})"


def _anchor(e: dict) -> tuple[float, float]:
    g = e["geom"]
    p = g.representative_point() if g.geom_type in ("Polygon", "MultiLineString") else g
    return (p.x, p.y)


def _size_words(e: dict) -> str:
    g = e["geom"]
    if g.geom_type != "Polygon":
        return ""
    minx, miny, maxx, maxy = g.bounds
    return f"about {(maxx - minx) / 10:.0f} by {(maxy - miny) / 10:.0f} cm"


def _feel(e: dict) -> str:
    """Short form for layout facts."""
    if e["kind"] == "line":
        return "a raised line"
    if e["kind"] == "point":
        return "a raised dot"
    tex = e.get("texture")
    return f"textured with {TEXTURE_NAMES[tex]}" if tex and tex != "none" else "an outline with a plain inside"


def _feel_sentence(e: dict) -> str:
    if e["kind"] == "line":
        return "It's a raised line."
    if e["kind"] == "point":
        return "It's a raised dot."
    tex = e.get("texture")
    return f"Its inside is textured with {TEXTURE_NAMES[tex]}." if tex and tex != "none" \
        else "It's an outline with a plain inside."


def _ancestors(e: dict, by_id: dict) -> set[str]:
    seen, p = set(), e.get("parent")
    while p in by_id and p not in seen:
        seen.add(p)
        p = by_id[p].get("parent")
    return seen


def _sentence(text: str) -> str:
    text = text.strip().rstrip(".")
    return f"{text[0].upper()}{text[1:]}." if text else ""


def describe_part(e: dict, scene: Scene) -> str:
    """One spoken sentence block for a single part."""
    by_id = {o["id"]: o for o in scene.elements}
    x, y = _anchor(e)
    parent = by_id.get(e.get("parent"))
    where = f"inside the {parent['name']}, " if parent else ""
    where += f"towards the {page_position(x, y)} of the page" if page_position(x, y) != "centre" else "near the centre of the page"
    label = next((L for L in scene.labels if e["id"] in L.ids), None)
    label_text = ""
    if label is not None:
        label_text = (f" Its braille label reads '{label.ink}'." if label.kind == "word"
                      else f" It is marked with the braille key letter '{label.text}'.")
    reason = f" {_sentence(e['reason'])}" if e.get("reason") else ""
    return f"{_sentence(e['name'])} {_sentence(where)} {_feel_sentence(e)}{reason}{label_text}"


def layout_facts(scene: Scene) -> list[str]:
    """Compact, verifiable facts about the page for grounding spoken answers."""
    facts = ["Page: A4 landscape, 29.7 cm wide and 21 cm tall. The key is in a column on the right edge."]
    by_id = {o["id"]: o for o in scene.elements}
    for e in scene.elements:
        x, y = _anchor(e)
        parent = by_id.get(e.get("parent"))
        bits = [f"'{e['name']}' ({e['kind']}): {page_position(x, y)} of the drawing, centre at "
                f"{x / 10:.1f} cm from the left and {y / 10:.1f} cm from the top"]
        if (size := _size_words(e)):
            bits.append(size)
        bits.append(_feel(e))
        if parent:
            bits.append(f"inside '{parent['name']}'")
        facts.append(", ".join(bits) + ".")
    elements = scene.elements
    for i, a in enumerate(elements):
        for b in elements[i + 1:]:
            if a["id"] in _ancestors(b, by_id) or b["id"] in _ancestors(a, by_id):
                continue  # containment is already stated; "above its container" would mislead
            gap = a["geom"].distance(b["geom"])
            if gap > 80:
                continue  # only nearby pairs: keeps the prompt short and the answers local
            gap_words = distance_words(gap)
            facts.append(f"'{b['name']}' is {direction(_anchor(a), _anchor(b))} '{a['name']}', "
                         f"{gap_words if gap_words == 'almost touching' else 'edge to edge ' + gap_words}.")
    return facts


def tour(scene: Scene) -> list[str]:
    """A guided reading order: title, summary, then containers before contents, big before small."""
    depth = {}
    by_id = {o["id"]: o for o in scene.elements}
    for e in scene.elements:
        d, p = 0, e.get("parent")
        while p in by_id and d < 5:
            d, p = d + 1, by_id[p].get("parent")
        depth[e["id"]] = d
    order = sorted(scene.elements, key=lambda e: (depth[e["id"]], -e["importance"], -e["geom"].area))
    steps = [f"{scene.title}. {scene.summary}".strip()]
    steps += [describe_part(e, scene) for e in order]
    steps.append("The key is on the right edge of the page. That's the whole page.")
    return steps


def hit_shapes(scene: Scene) -> list[dict]:
    """Simplified outlines (mm) the browser uses to work out which part a finger is on."""
    shapes = []
    for e in sorted(scene.elements, key=lambda e: -(e["geom"].area if e["kind"] == "region" else 0)):
        g = e["geom"]
        if g.geom_type == "Polygon":
            shape = {"type": "polygon", "points": [[round(x, 1), round(y, 1)] for x, y in g.simplify(0.6).exterior.coords]}
        elif g.geom_type == "MultiLineString":
            shape = {"type": "lines", "lines": [[[round(x, 1), round(y, 1)] for x, y in ln.simplify(0.6).coords] for ln in g.geoms]}
        else:
            shape = {"type": "point", "at": [round(g.x, 1), round(g.y, 1)]}
        shapes.append({"id": e["id"], "name": e["name"], "spoken": describe_part(e, scene), **shape})
    return shapes


def nearest_part(scene: Scene, x: float, y: float) -> dict | None:
    """Server-side equivalent of the browser hit test (used by tests)."""
    p = Point(x, y)
    regions = [e for e in scene.elements if e["kind"] == "region" and e["geom"].contains(p)]
    if regions:
        return min(regions, key=lambda e: e["geom"].area)
    near = [e for e in scene.elements if e["geom"].distance(p) < 4]
    return min(near, key=lambda e: e["geom"].distance(p)) if near else None
