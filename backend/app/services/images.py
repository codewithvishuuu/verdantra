"""Image intake: validate, sanitize, thumbnail (SECURITY.md sections 3-4).

Server is authoritative; client checks are UX only. Filenames are always
server-generated (never user input) so path traversal is impossible by
construction. EXIF (incl. GPS) is stripped on every upload; only
`exif_stripped: true` is ever logged, never tag contents.
"""

import io

from PIL import Image

from app.errors import ApiError

ALLOWED = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}

_JPEG_SIG = b"\xff\xd8\xff"
_PNG_SIG = b"\x89PNG\r\n\x1a\n"

MIN_DIM = 64
MAX_EDGE = 4096
THUMB_EDGE = 512


def sniff_mime(head: bytes) -> str | None:
    if head.startswith(_JPEG_SIG):
        return "image/jpeg"
    if head.startswith(_PNG_SIG):
        return "image/png"
    if len(head) >= 12 and head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    return None


def validate_bytes(data: bytes, max_bytes: int) -> str:
    """Return the MIME type or raise the documented ApiError. Order: type, size, decodability."""
    if not data:
        raise ApiError(400, "invalid_image",
                       "That file could not be read as a photo. Try a different photo.")
    mime = sniff_mime(data[:12])
    if mime is None or mime not in ALLOWED:
        raise ApiError(400, "invalid_image",
                       "Please choose a JPEG, PNG, or WebP photo.")
    if len(data) > max_bytes:
        raise ApiError(413, "too_large",
                       "That photo is over %d MB. Choose a smaller one."
                       % (max_bytes // (1024 * 1024),))
    try:
        with Image.open(io.BytesIO(data)) as img:
            img.load()
            if img.width < MIN_DIM or img.height < MIN_DIM:
                raise ApiError(422, "unusable_image",
                               "That photo is too small to analyze. Try a different photo.")
    except ApiError:
        raise
    except Exception:
        raise ApiError(422, "unusable_image",
                       "That photo could not be decoded. Try a different photo.")
    return mime


def _fit(img: Image.Image, edge: int) -> Image.Image:
    longest = max(img.width, img.height)
    if longest <= edge:
        return img
    scale = edge / longest
    return img.resize((max(1, int(img.width * scale)), max(1, int(img.height * scale))),
                      Image.LANCZOS)


def make_thumbnail(data: bytes) -> bytes:
    """512px JPEG thumbnail from sanitized full-size bytes (M3 promotion reuses this)."""
    with Image.open(io.BytesIO(data)) as img:
        img.load()
        thumb = _fit(img, THUMB_EDGE)
        thumb_buf = io.BytesIO()
        thumb.save(thumb_buf, format="JPEG", quality=80, optimize=True)
    return thumb_buf.getvalue()


def sanitize(data: bytes, mime: str) -> tuple[bytes, bytes]:
    """Re-encode (EXIF dropped) + downscale; return (full_bytes, thumb_bytes).

    Pillow's save paths below never carry EXIF blocks: JPEG is saved without
    an exif parameter, PNG/WebP are saved plain. Conservative + auditable.
    """
    with Image.open(io.BytesIO(data)) as img:
        img.load()
        if img.mode in ("RGBA", "LA", "PA"):
            canvas = Image.new("RGB", img.size, (255, 255, 255))
            canvas.paste(img, mask=img.split()[-1])
            img = canvas
        elif img.mode != "RGB":
            img = img.convert("RGB")
        img = _fit(img, MAX_EDGE)
        full_buf = io.BytesIO()
        if mime == "image/png":
            img.save(full_buf, format="PNG", optimize=True)
        elif mime == "image/webp":
            img.save(full_buf, format="WEBP", quality=85, method=4)
        else:
            img.save(full_buf, format="JPEG", quality=85, optimize=True)
        thumb_bytes = make_thumbnail(full_buf.getvalue())
    return full_buf.getvalue(), thumb_bytes


def ext_for(mime: str) -> str:
    return ALLOWED[mime]


def prepare_transmit(data: bytes, mime: str, max_edge: int = 2048,
                     quality: int = 82) -> tuple[bytes, str]:
    """Smaller provider payload from already-sanitized bytes.

    Already-suitable JPEGs pass through untouched (EXIF was stripped
    upstream, so no rewrite is needed). Anything over the edge budget or
    non-JPEG is downscaled/re-encoded to JPEG. Aspect ratio preserved.
    Stored files are unaffected — this only shapes the provider request.
    """
    with Image.open(io.BytesIO(data)) as img:
        img.load()
        if max(img.width, img.height) <= max_edge and mime == "image/jpeg":
            return data, mime
        if img.mode in ("RGBA", "LA", "PA"):
            canvas = Image.new("RGB", img.size, (255, 255, 255))
            canvas.paste(img, mask=img.split()[-1])
            img = canvas
        elif img.mode != "RGB":
            img = img.convert("RGB")
        small = _fit(img, max_edge)
        buf = io.BytesIO()
        small.save(buf, format="JPEG", quality=quality, optimize=True)
    return buf.getvalue(), "image/jpeg"
