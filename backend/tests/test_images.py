"""Image pipeline: sniffing, limits, EXIF strip, downscale, thumbnails."""

import io

import pytest
from PIL import Image

from app.errors import ApiError
from app.services import images
from tests.conftest import make_image

MAXB = 10 * 1024 * 1024


def test_valid_jpeg_png_webp():
    assert images.validate_bytes(make_image("JPEG"), MAXB) == "image/jpeg"
    assert images.validate_bytes(make_image("PNG"), MAXB) == "image/png"
    assert images.validate_bytes(make_image("WEBP"), MAXB) == "image/webp"


def test_rejects_executable_and_empty():
    with pytest.raises(ApiError) as e:
        images.validate_bytes(b"MZ\x90\x00evil.exe", MAXB)
    assert e.value.code == "invalid_image" and e.value.status == 400
    with pytest.raises(ApiError) as e:
        images.validate_bytes(b"", MAXB)
    assert e.value.code == "invalid_image"


def test_rejects_oversize_after_valid_type():
    big = make_image("JPEG", size=(64, 64)) + b"\x00" * (MAXB + 1)
    with pytest.raises(ApiError) as e:
        images.validate_bytes(big, MAXB)
    assert (e.value.code, e.value.status) == ("too_large", 413)


def test_rejects_tiny_and_corrupt():
    with pytest.raises(ApiError) as e:
        images.validate_bytes(make_image("JPEG", size=(1, 1)), MAXB)
    assert (e.value.code, e.value.status) == ("unusable_image", 422)
    with pytest.raises(ApiError) as e:
        images.validate_bytes(b"\xff\xd8\xff" + b"\x00" * 100, MAXB)
    assert e.value.code == "unusable_image"


def test_exif_stripped_on_reencode():
    src = make_image("JPEG", exif=True)
    assert len(Image.open(io.BytesIO(src)).getexif()) > 0  # fixture really has EXIF
    full, thumb = images.sanitize(src, "image/jpeg")
    assert len(Image.open(io.BytesIO(full)).getexif()) == 0
    assert b"TEST-CAMERA" not in full


def test_downscale_and_thumbnail_shapes():
    full, thumb = images.sanitize(make_image("JPEG", size=(5000, 100)), "image/jpeg")
    assert max(Image.open(io.BytesIO(full)).size) == 4096
    assert max(Image.open(io.BytesIO(thumb)).size) == 512
    assert Image.open(io.BytesIO(thumb)).format == "JPEG"
