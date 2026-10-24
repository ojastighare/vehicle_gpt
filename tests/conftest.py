"""Pytest configuration ensuring project root is in sys.path and demo DB is available."""

import sys
from pathlib import Path

# Add project root to sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Ensure baseline database is initialized
from backend.config import DB_ABSOLUTE_PATH, settings
from backend.database import init_db
from backend.ingestion import IngestionPipeline
from backend.simulator import VehicleDataSimulator

init_db(DB_ABSOLUTE_PATH)
sim = VehicleDataSimulator(seed=settings.RANDOM_SEED)
dataset = sim.generate_dataset(days=21)
pipeline = IngestionPipeline(DB_ABSOLUTE_PATH)
pipeline.ingest_batch(dataset)
