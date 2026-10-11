"""Plain domain types (no ORM in MVP). Pydantic contracts live in schemas.py."""

from dataclasses import dataclass


@dataclass
class TempImage:
    """An uploaded, sanitized image awaiting analysis or journal save."""

    id: str            # tmp_xxx (server-generated, matches ^[A-Za-z0-9_-]{1,64}$)
    filename: str      # e.g. tmp_xxx.jpg (server-generated name, never user input)
    mime: str          # image/jpeg | image/png | image/webp
    size: int          # bytes of the sanitized file
