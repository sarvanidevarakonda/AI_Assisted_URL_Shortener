from datetime import datetime
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, field_validator


class URLRequest(BaseModel):
    """Request payload for creating a shortened URL."""

    original_url: str

    @field_validator("original_url")
    @classmethod
    def validate_original_url(cls, value: str) -> str:
        """Ensure the URL is structurally valid and uses HTTP or HTTPS."""
        if not isinstance(value, str) or not value.strip():
            raise ValueError("original_url must be a non-empty string")

        value = value.strip()

        if not value.startswith(("http://", "https://")):
            raise ValueError("original_url must start with http:// or https://")

        try:
            parsed = urlparse(value)
        except ValueError as exc:
            raise ValueError(f"original_url is not a valid URL: {exc}") from exc

        if parsed.scheme not in ("http", "https"):
            raise ValueError("original_url must use http or https scheme")

        if not parsed.netloc:
            raise ValueError("original_url must include a host")

        # Reject whitespace anywhere in the URL (common pasted-input bug).
        if any(ch.isspace() for ch in value):
            raise ValueError("original_url must not contain whitespace")

        # Basic host sanity: must contain a dot or be localhost.
        host = parsed.hostname or ""
        if host != "localhost" and "." not in host:
            raise ValueError("original_url host must be a domain name or localhost")

        return value


class URLResponse(BaseModel):
    """Response containing a shortened URL and its original URL."""

    model_config = ConfigDict(from_attributes=True)

    short_code: str
    short_url: str
    original_url: str


class AnalyticsResponse(BaseModel):
    """Response containing URL metadata and click analytics."""

    model_config = ConfigDict(from_attributes=True)

    original_url: str
    short_code: str
    click_count: int
    created_at: datetime