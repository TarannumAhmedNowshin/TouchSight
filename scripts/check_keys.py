"""Check both vision providers with a synthetic image and report box accuracy.

    python scripts/check_keys.py
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from touchsight import vlm  # noqa: E402
from touchsight.config import settings  # noqa: E402

W, H = 500, 360
TRUTH = {"cell membrane": (60, 60, 440, 320), "nucleus": (200, 140, 300, 230)}  # x0, y0, x1, y1 in px


def synthetic_cell() -> bytes:
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    d.ellipse(TRUTH["cell membrane"], outline="black", width=5)
    d.ellipse(TRUTH["nucleus"], fill=(200, 200, 200), outline="black", width=4)
    d.text((215, 240), "Nucleus", fill="black")
    d.text((70, 35), "Cell membrane", fill="black")
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def iou(a, b) -> float:
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    return inter / ((a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter)


def main() -> int:
    padded, fy, fx = vlm.pad_square(synthetic_cell())
    failures = 0
    for name, call in (("gemini", vlm.call_gemini), ("groq", vlm.call_groq)):
        print(f"\n=== {name} ===")
        try:
            out = vlm.normalise(vlm.unpad_boxes(call(padded), fy, fx))
        except Exception as ex:  # report and keep going
            failures += 1
            print(f"FAILED: {type(ex).__name__}: {ex}")
            continue
        print(f"OK  model: {vlm.provider_label(name) if name == 'gemini' else settings.groq_model}")
        for e in out["elements"]:
            y0, x0, y1, x1 = e["box_2d"]
            box = (x0 / 1000 * W, y0 / 1000 * H, x1 / 1000 * W, y1 / 1000 * H)
            truth = TRUTH.get(e["name"])
            print(f"   {e['name']:15s} " + (f"box accuracy {iou(box, truth):.0%}" if truth else ""))
    return 1 if failures == 2 else 0


if __name__ == "__main__":
    raise SystemExit(main())
