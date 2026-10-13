from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, String

from database import Base


class URLMapping(Base):
    """Store an original URL and its shortened code."""

    __tablename__ = "url_mappings"

    id = Column(Integer, primary_key=True)
    original_url = Column(String, nullable=False, unique=True, index=True)
    short_code = Column(String, nullable=False, unique=True, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    click_count = Column(Integer, default=0)

    def __repr__(self):
        return (
            f"URLMapping(id={self.id!r}, original_url={self.original_url!r}, "
            f"short_code={self.short_code!r})"
        )