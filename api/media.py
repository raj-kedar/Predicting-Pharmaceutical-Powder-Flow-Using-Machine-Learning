"""
Secure image handling.

Every upload is treated as hostile:
  * size capped before reading, and only JPEG, PNG or WebP accepted by magic bytes;
  * decoded with a pixel limit, so decompression bombs are rejected;
  * re-encoded to a fresh square WebP, which drops EXIF (GPS, camera, author),
    colour profiles and any embedded payload, and defeats polyglot files;
  * stored under a random name in private storage, never under the user's file name;
  * served only through the API, with access checks and headers that stop the
    browser from treating the bytes as anything but an image.
"""
from __future__ import annotations

import hashlib
import io
import re
import secrets
from dataclasses import dataclass
from pathlib import Path

from fastapi import HTTPException, Response, status
from PIL import Image, ImageOps, UnidentifiedImageError

MAX_UPLOAD_BYTES = 5 * 1024 * 1024
MAX_SOURCE_PIXELS = 40_000_000
MAX_SIDE = 8000
OUTPUT_SIDE = {"profile": 512, "site": 640}
_MAGIC = {
    b"\xff\xd8\xff": "JPEG",
    b"\x89PNG\r\n\x1a\n": "PNG",
}
_ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp"}
_KEY = re.compile(r"^(profile|site)/[0-9a-f]{32}\.webp$")
Image.MAX_IMAGE_PIXELS = MAX_SOURCE_PIXELS


class ImageRejected(HTTPException):
    def __init__(self, detail: str):
        super().__init__(status.HTTP_422_UNPROCESSABLE_ENTITY, detail)


@dataclass(frozen=True)
class CleanImage:
    data: bytes
    width: int
    height: int
    sha256: str


def _sniff(data: bytes) -> str | None:
    for magic, kind in _MAGIC.items():
        if data.startswith(magic):
            return kind
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "WEBP"
    return None


def sanitize_image(data: bytes, content_type: str, kind: str) -> CleanImage:
    if content_type.split(";")[0].strip().lower() not in _ALLOWED_TYPES:
        raise ImageRejected("Upload a JPEG, PNG or WebP image.")
    if not data:
        raise ImageRejected("The file is empty.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise ImageRejected("Images must be 5 MB or smaller.")
    declared = _sniff(data)
    if declared is None:
        raise ImageRejected("This file is not a JPEG, PNG or WebP image.")
    try:
        with Image.open(io.BytesIO(data)) as source:
            if source.format != declared:
                raise ImageRejected("The file contents do not match its image type.")
            width, height = source.size
            if width < 32 or height < 32 or width > MAX_SIDE or height > MAX_SIDE:
                raise ImageRejected("Images must be between 32 and 8000 pixels on each side.")
            if width * height > MAX_SOURCE_PIXELS:
                raise ImageRejected("The image has too many pixels.")
            if getattr(source, "n_frames", 1) > 1:
                raise ImageRejected("Animated images are not allowed.")
            source.load()
            image = ImageOps.exif_transpose(source)
            if image.mode in ("RGBA", "LA", "P"):
                image = image.convert("RGBA")
                background = Image.new("RGB", image.size, (255, 255, 255))
                background.paste(image, mask=image.split()[-1])
                image = background
            else:
                image = image.convert("RGB")
    except ImageRejected:
        raise
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, ValueError,
            SyntaxError) as exc:
        raise ImageRejected("The image could not be read safely.") from exc

    side = OUTPUT_SIDE[kind]
    image = ImageOps.fit(image, (side, side), Image.Resampling.LANCZOS)
    out = io.BytesIO()
    image.save(out, format="WEBP", quality=85, method=6)   # writes no EXIF or ICC data
    clean = out.getvalue()
    return CleanImage(clean, side, side, hashlib.sha256(clean).hexdigest())


def new_image_id() -> str:
    return secrets.token_hex(16)


def storage_key(kind: str, image_id: str) -> str:
    key = f"{kind}/{image_id}.webp"
    if not _KEY.match(key):
        raise ValueError("invalid storage key")
    return key


class LocalStorage:
    """Development and fallback storage inside the private data volume."""

    def __init__(self, root: Path):
        self.root = root

    def _path(self, key: str) -> Path:
        if not _KEY.match(key):
            raise ValueError("invalid storage key")
        return self.root / key

    def put(self, key: str, data: bytes) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(data)
        tmp.replace(path)

    def get(self, key: str) -> bytes | None:
        path = self._path(key)
        return path.read_bytes() if path.is_file() else None

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)


class S3Storage:
    """Private, encrypted Amazon S3 bucket. Credentials come from the EC2 instance role."""

    def __init__(self, bucket: str, region: str | None, client=None):
        if client is None:
            import boto3
            from botocore.config import Config
            client = boto3.client("s3", region_name=region or None,
                                  config=Config(retries={"max_attempts": 3, "mode": "standard"}))
        self.bucket = bucket
        self.client = client

    def put(self, key: str, data: bytes) -> None:
        if not _KEY.match(key):
            raise ValueError("invalid storage key")
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType="image/webp",
                               ServerSideEncryption="AES256", CacheControl="private, no-store")

    def get(self, key: str) -> bytes | None:
        if not _KEY.match(key):
            raise ValueError("invalid storage key")
        try:
            return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()
        except self.client.exceptions.NoSuchKey:
            return None

    def delete(self, key: str) -> None:
        if _KEY.match(key):
            self.client.delete_object(Bucket=self.bucket, Key=key)


def image_response(data: bytes, cache: str) -> Response:
    """Bytes are only ever an image: no sniffing, no scripts, not embeddable elsewhere."""
    return Response(data, media_type="image/webp", headers={
        "Cache-Control": cache,
        "Content-Disposition": 'inline; filename="image.webp"',
        "Content-Security-Policy": "default-src 'none'; sandbox",
        "Cross-Origin-Resource-Policy": "same-origin",
        "X-Content-Type-Options": "nosniff",
    })
