"""Database seeding script for VehicleGPT.

Initializes SQLite schema, generates 3 weeks of synthetic vehicle telemetry and events,
and stores the validated records into the local database.
"""

import sys
from pathlib import Path

# Add project root to path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from backend.config import DB_ABSOLUTE_PATH, settings
from backend.database import init_db, reset_db
from backend.ingestion import IngestionPipeline
from backend.simulator import VehicleDataSimulator


def seed(days: int = 21, seed_val: int = 42) -> None:
    print(f"[*] Initializing SQLite database at: {DB_ABSOLUTE_PATH}")
    init_db(DB_ABSOLUTE_PATH)

    print("[*] Clearing any previous demo records...")
    reset_db(DB_ABSOLUTE_PATH)

    print(f"[*] Generating synthetic vehicle telemetry and events (days={days}, seed={seed_val})...")
    sim = VehicleDataSimulator(seed=seed_val)
    dataset = sim.generate_dataset(days=days)

    print(
        f"[*] Simulated: {len(dataset['telemetry'])} telemetry signals, "
        f"{len(dataset['events'])} events, {len(dataset['diagnostics'])} diagnostics."
    )

    print("[*] Ingesting and validating records through IngestionPipeline...")
    pipeline = IngestionPipeline(DB_ABSOLUTE_PATH)
    counts = pipeline.ingest_batch(dataset)

    print("[+] Seeding complete successfully!")
    print(f"    - Telemetry records ingested: {counts['telemetry_count']}")
    print(f"    - Vehicle events ingested:    {counts['event_count']}")
    print(f"    - Diagnostic logs ingested:   {counts['diagnostic_count']}")


if __name__ == "__main__":
    seed()
