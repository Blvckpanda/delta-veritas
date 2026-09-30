"""
Niger Delta Environmental Risk Observatory — FastAPI Application.

Serves GeoJSON endpoints for spills, flares, and disclosures data.
Run with:
    uvicorn src.api.main:app --reload --port 8766
"""

from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import config as api_config
from .database import init_db
from .routers import disclosures, flares, spills
from .schemas.common import HealthResponse


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: initialize database tables. Shutdown: clean up."""
    await init_db()
    yield


app = FastAPI(
    title="Niger Delta Environmental Risk Observatory API",
    version=api_config.CURRENT_DATA_VERSION,
    description=(
        "GeoJSON API for oil spill incidents, gas flaring data, "
        "and infrastructure disclosures across the Niger Delta."
    ),
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=api_config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(spills.router, prefix=api_config.API_PREFIX)
app.include_router(flares.router, prefix=api_config.API_PREFIX)
app.include_router(disclosures.router, prefix=api_config.API_PREFIX)


# ── Health check ───────────────────────────────────────────────────────────
@app.get("/health", response_model=HealthResponse, tags=["system"])
async def health():
    """API health check."""
    try:
        from sqlalchemy import text

        from .database import async_session_factory
        async with async_session_factory() as session:
            await session.execute(text("SELECT 1"))
            db_ok = True
    except Exception:
        db_ok = False

    return HealthResponse(
        status="ok" if db_ok else "degraded",
        version=api_config.CURRENT_DATA_VERSION,
        timestamp=datetime.utcnow(),
        db_connected=db_ok,
    )


@app.get("/", tags=["system"])
async def root():
    """Root endpoint — redirects to docs."""
    return {
        "message": "Niger Delta Environmental Risk Observatory API",
        "docs": f"{api_config.API_PREFIX}/docs",
        "version": api_config.CURRENT_DATA_VERSION,
    }
