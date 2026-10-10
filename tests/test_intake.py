import dataclasses
import io

import pytest
from PIL import Image

from touchsight import intake


def encode(im: Image.Image, fmt: str, **kw) -> bytes:
    buf = io.BytesIO()
    im.save(buf, fmt, **kw)
    return buf.getvalue()


def decode(png: bytes) -> Image.Image:
    im = Image.open(io.BytesIO(png))
    assert im.format == "PNG" and im.mode == "RGB"
    return im


@pytest.mark.parametrize("fmt", ["PNG", "JPEG", "WEBP", "GIF", "BMP", "TIFF", "AVIF"])
def test_common_formats_become_rgb_png(fmt):
    src = Image.new("RGB", (120, 80), (200, 30, 30))
    out = decode(intake.normalise(encode(src, fmt)))
    assert out.size == (120, 80)


def test_iphone_heic():
    pytest.importorskip("pillow_heif")
    src = Image.new("RGB", (160, 90), (20, 120, 200))
    out = decode(intake.normalise(encode(src, "HEIF")))
    assert out.size == (160, 90)


def test_exif_orientation_is_applied():
    src = Image.new("RGB", (200, 100), "white")
    exif = Image.Exif()
    exif[0x0112] = 6  # "rotate 90° clockwise to view", as phone cameras write it
    out = decode(intake.normalise(encode(src, "JPEG", exif=exif)))
    assert out.size == (100, 200)


def test_transparency_is_flattened_onto_white():
    src = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    out = decode(intake.normalise(encode(src, "PNG")))
    assert out.getpixel((10, 10)) == (255, 255, 255)


def test_cmyk_and_animation_are_handled():
    cmyk = Image.new("CMYK", (64, 64), (0, 255, 255, 0))
    decode(intake.normalise(encode(cmyk, "TIFF")))
    frames = [Image.new("RGB", (64, 64), c) for c in ("red", "blue")]
    buf = io.BytesIO()
    frames[0].save(buf, "GIF", save_all=True, append_images=frames[1:])
    assert decode(intake.normalise(buf.getvalue())).getpixel((5, 5))[0] > 200  # first frame (red)


def test_large_photos_are_downscaled():
    out = decode(intake.normalise(encode(Image.new("RGB", (4032, 3024), "white"), "JPEG")))
    assert max(out.size) == intake.MAX_SIDE


@pytest.mark.parametrize("data", [b"not an image", b"%PDF-1.7 fake", b""])
def test_non_images_are_rejected(data):
    with pytest.raises(intake.ImageError):
        intake.normalise(data)


def test_tiny_and_huge_images_are_rejected(monkeypatch):
    with pytest.raises(intake.ImageError):
        intake.normalise(encode(Image.new("RGB", (10, 10)), "PNG"))
    monkeypatch.setattr(intake, "settings", dataclasses.replace(intake.settings, max_image_pixels=5000))
    with pytest.raises(intake.ImageError):
        intake.normalise(encode(Image.new("RGB", (100, 100)), "PNG"))


def test_output_is_deterministic():
    data = encode(Image.new("RGB", (300, 200), "teal"), "JPEG")
    assert intake.normalise(data) == intake.normalise(data)
