import secrets
import string
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from database import Base, engine, get_db
from models import URLMapping
from schemas import AnalyticsResponse, URLRequest, URLResponse


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Create database tables during application startup."""
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(lifespan=lifespan)


def _build_url_response(mapping: URLMapping) -> URLResponse:
    """Build a response for a stored URL mapping."""
    return URLResponse(
        short_code=mapping.short_code,
        short_url=f"http://localhost:8000/{mapping.short_code}",
        original_url=mapping.original_url,
    )


@app.post(
    "/shorten",
    response_model=URLResponse,
    responses={
        422: {"description": "Invalid URL format"},
        500: {"description": "Database error or unable to generate a unique code"},
    },
)
def shorten_url(request: URLRequest, db: Session = Depends(get_db)) -> URLResponse:
    """Create a short URL or return the existing mapping for the original URL."""
    try:
        existing_mapping = (
            db.query(URLMapping)
            .filter(URLMapping.original_url == request.original_url)
            .first()
        )
        if existing_mapping is not None:
            return _build_url_response(existing_mapping)

        alphabet = string.ascii_letters + string.digits
        for _ in range(3):
            mapping = URLMapping(
                original_url=request.original_url,
                short_code="".join(secrets.choice(alphabet) for _ in range(6)),
            )
            db.add(mapping)
            try:
                db.commit()
                db.refresh(mapping)
                return _build_url_response(mapping)
            except IntegrityError:
                db.rollback()

        raise HTTPException(
            status_code=500,
            detail="Unable to generate a unique short code",
        )
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail="Database error") from exc


@app.get(
    "/{short_code}",
    responses={
        307: {"description": "Redirect to the original URL"},
        404: {"description": "Short URL not found"},
    },
)
def redirect_to_original(short_code: str, db: Session = Depends(get_db)) -> RedirectResponse:
    """Redirect to the original URL and increment its click count."""
    try:
        mapping = (
            db.query(URLMapping)
            .filter(URLMapping.short_code == short_code)
            .first()
        )
        if mapping is None:
            raise HTTPException(status_code=404, detail="Short URL not found")

        mapping.click_count += 1
        db.commit()
        return RedirectResponse(url=mapping.original_url, status_code=307)
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail="Database error") from exc


@app.get(
    "/analytics/{short_code}",
    response_model=AnalyticsResponse,
    responses={
        404: {"description": "Short URL not found"},
    },
)
def get_analytics(short_code: str, db: Session = Depends(get_db)) -> AnalyticsResponse:
    """Return analytics for a shortened URL."""
    try:
        mapping = (
            db.query(URLMapping)
            .filter(URLMapping.short_code == short_code)
            .first()
        )
        if mapping is None:
            raise HTTPException(status_code=404, detail="Short URL not found")
        return AnalyticsResponse.model_validate(mapping)
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail="Database error") from exc