from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator


class URLRequest(BaseModel):
    """Request payload for creating a shortened URL."""

    original_url: str

    @field_validator("original_url")
    @classmethod
    def validate_original_url(cls, value: str) -> str:
        """Ensure the URL uses HTTP or HTTPS."""
        if not value.startswith(("http://", "https://")):
            raise ValueError("original_url must start with http:// or https://")
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
