"""FastAPI application entrypoint for VehicleGPT."""

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.config import DB_ABSOLUTE_PATH, settings
from backend.database import get_db, init_db
from backend.ingestion import IngestionPipeline
from backend.routers import events, health, query, telemetry
from backend.simulator import VehicleDataSimulator

BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Ensure database and initial demo data are present on application startup."""
    init_db(DB_ABSOLUTE_PATH)

    # Seed if database is empty
    with get_db() as conn:
        count = conn.execute("SELECT COUNT(*) FROM telemetry;").fetchone()[0]
        if count == 0:
            print("[VehicleGPT Startup] Empty database detected. Seeding 3-week synthetic baseline...")
            sim = VehicleDataSimulator(seed=settings.RANDOM_SEED)
            dataset = sim.generate_dataset(days=21)
            pipeline = IngestionPipeline(DB_ABSOLUTE_PATH)
            pipeline.ingest_batch(dataset)
            print("[VehicleGPT Startup] Baseline database seeded successfully.")

    yield


app = FastAPI(
    title="VehicleGPT",
    description="Natural Language Vehicle Intelligence Using On-Device AI (Tata Elxsi Teliport Case Study 5)",
    version="1.0.0",
    lifespan=lifespan,
)

# Restrict CORS to local development origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# Register API routers
app.include_router(health.router)
app.include_router(telemetry.router)
app.include_router(events.router)
app.include_router(query.router)

# Mount frontend static assets
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


@app.get("/", include_in_schema=False)
async def serve_index():
    """Serve the VehicleGPT dashboard homepage."""
    index_file = FRONTEND_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return {"message": "VehicleGPT API running. Frontend static directory not initialized."}
