"""Run once to check your API keys work with a real image:   python test_keys.py"""
import io
import os

from PIL import Image, ImageDraw

from touchsight import vlm

W, H = 500, 360
img = Image.new("RGB", (W, H), "white")
d = ImageDraw.Draw(img)
d.ellipse((60, 60, 440, 320), outline="black", width=5)
d.ellipse((200, 140, 300, 230), fill=(200, 200, 200), outline="black", width=4)
d.text((215, 240), "Nucleus", fill="black")
d.text((70, 35), "Cell membrane", fill="black")
buf = io.BytesIO()
img.save(buf, "PNG")
data = buf.getvalue()

TRUTH = {"cell membrane": (60, 60, 440, 320), "nucleus": (200, 140, 300, 230)}  # x0,y0,x1,y1 px


def iou(a, b):
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    return inter / ((a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter)


padded, fy, fx = vlm.pad_square(data)
for name, fn in (("Gemini", vlm.call_gemini), ("Groq", vlm.call_groq)):
    print(f"\n=== {name} ===")
    try:
        out = vlm.normalise(vlm._unpad(fn(padded), fy, fx))
        model = vlm._GEMINI_MODEL if name == "Gemini" else os.getenv("GROQ_MODEL", "qwen/qwen3.8-27b")
        print(f"OK ✅  model: {model}")
        for e in out["elements"]:
            y0, x0, y1, x1 = e["box_2d"]
            px = (x0 / 1000 * W, y0 / 1000 * H, x1 / 1000 * W, y1 / 1000 * H)
            t = TRUTH.get(e["name"])
            acc = f"box accuracy {iou(px, t):.0%}" if t else ""
            print(f"   - {e['name']:15s} {acc}")
        print("   dropped:", [x.get("what") for x in out["dropped"]])
    except Exception as ex:
        print("FAILED ❌", type(ex).__name__, str(ex)[:400])
