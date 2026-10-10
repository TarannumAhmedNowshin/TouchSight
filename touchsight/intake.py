"""Image intake: accept whatever a phone, scanner or browser produces and hand the
pipeline one predictable format.

Accepted: PNG, JPEG, WebP, HEIC/HEIF (iPhone camera), AVIF, GIF, BMP, TIFF.
Steps: identify from the header (the filename and content type are never trusted),
reject decompression bombs before decoding, apply the EXIF orientation phone cameras
store instead of rotating pixels, take the first frame of animations, flatten
transparency onto white, cap the size, re-encode as PNG.

Normalised output is deterministic, so the same photo always maps to the same cache entry.
"""
from __future__ import annotations

import io
import logging

from PIL import Image, ImageOps, UnidentifiedImageError

from .config import settings

log = logging.getLogger(__name__)

try:  # HEIC/HEIF support (iPhone photos); optional so the engine still runs without it
    from pillow_heif import register_heif_opener

    register_heif_opener()
    HEIF_SUPPORTED = True
except ImportError:  # pragma: no cover
    HEIF_SUPPORTED = False

ACCEPTED_FORMATS = {"PNG", "JPEG", "WEBP", "HEIF", "AVIF", "GIF", "BMP", "TIFF", "MPO"}
MAX_SIDE = 2400        # px; more detail than the tracer uses, small enough to send to a model
MIN_SIDE = 32
Image.MAX_IMAGE_PIXELS = settings.max_image_pixels  # Pillow's own bomb guard as a second line


class ImageError(ValueError):
    """The upload is not an image we can safely process."""


def inspect(data: bytes) -> tuple[int, int, str]:
    """Header-only check: (width, height, format). Raises ImageError for anything unsafe."""
    try:
        with Image.open(io.BytesIO(data)) as im:
            w, h, fmt = im.width, im.height, (im.format or "").upper()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as ex:
        raise ImageError("That file isn't an image we can read. Try a PNG, JPG, HEIC or WebP.") from ex
    if fmt not in ACCEPTED_FORMATS:
        raise ImageError(f"{fmt or 'This'} images aren't supported. Try a PNG, JPG, HEIC or WebP.")
    if w * h > settings.max_image_pixels:
        raise ImageError("That image is too large (over 40 megapixels). Export a smaller version.")
    if min(w, h) < MIN_SIDE:
        raise ImageError("That image is too small to read. Use one at least 32 pixels across.")
    return w, h, fmt


def normalise(data: bytes) -> bytes:
    """Return the upload as an upright, opaque, size-capped PNG."""
    inspect(data)
    try:
        with Image.open(io.BytesIO(data)) as im:
            im.seek(0)                              # first frame of GIF / animated WebP / multi-page TIFF
            im = ImageOps.exif_transpose(im)        # phone photos: honour the stored orientation
            if im.mode in ("RGBA", "LA", "P", "PA"):
                im = im.convert("RGBA")
                flat = Image.new("RGB", im.size, "white")
                flat.paste(im, mask=im.getchannel("A"))
                im = flat
            elif im.mode != "RGB":
                im = im.convert("RGB")              # CMYK, 16-bit, greyscale, ...
            if max(im.size) > MAX_SIDE:
                im.thumbnail((MAX_SIDE, MAX_SIDE), Image.LANCZOS)
            out = io.BytesIO()
            im.save(out, "PNG", optimize=False)
            return out.getvalue()
    except ImageError:
        raise
    except (OSError, ValueError, Image.DecompressionBombError) as ex:
        log.warning("could not normalise upload: %s", ex)
        raise ImageError("That image appears to be damaged. Try exporting it again.") from ex
