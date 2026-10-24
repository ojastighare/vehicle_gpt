"""Natural-language question query and development demo-reset endpoints."""

from fastapi import APIRouter, HTTPException, status
from backend.config import settings
from backend.database import DB_ABSOLUTE_PATH, init_db, reset_db
from backend.ingestion import IngestionPipeline
from backend.response_builder import ResponseBuilder
from backend.schemas import QueryRequest, QueryResponse
from backend.simulator import VehicleDataSimulator

router = APIRouter(prefix="/api", tags=["Natural Language Query"])
response_builder = ResponseBuilder()


@router.post("/query", response_model=QueryResponse)
async def process_natural_language_query(req: QueryRequest):
    """Process natural language question through retrieval, deterministic analytics, and optional SLM."""
    try:
        response = await response_builder.execute_query(
            question=req.question,
            use_llm=bool(req.use_llm),
            user_start=req.start_time,
            user_end=req.end_time,
        )
        return response
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Query execution error: {str(e)}",
        )


@router.post("/demo/reset")
async def reset_demo_database():
    """Reset and reseed demo database. Protected development-only endpoint."""
    if not settings.ALLOW_RESET or settings.ENVIRONMENT != "development":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Reset endpoint disabled in non-development environments.",
        )

    try:
        init_db(DB_ABSOLUTE_PATH)
        reset_db(DB_ABSOLUTE_PATH)
        sim = VehicleDataSimulator(seed=settings.RANDOM_SEED)
        dataset = sim.generate_dataset(days=21)
        pipeline = IngestionPipeline(DB_ABSOLUTE_PATH)
        counts = pipeline.ingest_batch(dataset)

        return {
            "status": "success",
            "message": "Demo database successfully reset and re-seeded.",
            "records_created": counts,
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database reset failure: {str(e)}",
        )
