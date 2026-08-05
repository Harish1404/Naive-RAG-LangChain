import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI

from app.core.config import settings
from app.routes.chatbot import router as chatbot_router
from app.rag.rag_pipeline import rag_pipeline
from app.core.tracing import verify_langsmith_connection
from app.db.mongodb import connect_to_mongo, close_mongo_connection, get_database_client


# Configure logging to output INFO level logs to terminal
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger("uvicorn.error")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("App startup")

    # Ping LangSmith before Mongo, so the boot log reads top-down:
    # tracing -> database -> ingestion.
    app.state.langsmith = await verify_langsmith_connection()

    await connect_to_mongo()
    chunk_count = await rag_pipeline.ingest("uploads")
    logger.info(f"RAG startup ingestion complete: {chunk_count} new chunk(s) indexed.")
    yield
    logger.info("App shutdown")

    # Runs upload from a background thread; this makes sure the last few traces
    # are sent before the process goes away (e.g. Ctrl+C under --reload).
    if settings.tracing_enabled:
        try:
            from langsmith import Client
            Client().flush()
            logger.info("LangSmith traces flushed.")
        except Exception as e:
            logger.warning(f"Could not flush LangSmith traces: {e}")

    await close_mongo_connection()


app = FastAPI(lifespan=lifespan)
app.include_router(chatbot_router)



@app.get("/")
def landing_page():
    return {
        "message": " Hi this is your backend server"
    }

@app.get("/health")
async def health():
    """
    Reports the live state of both external dependencies.

    Checked on every call rather than echoing the startup result, so you can
    confirm a config fix without restarting the server. Never raises — a broken
    dependency shows up in the body, not as a 500.
    """
    try:
        await get_database_client().admin.command("ping")
        mongodb = {"status": "ok"}
    except Exception as e:
        mongodb = {"status": "error", "detail": str(e)[:250]}

    langsmith = await verify_langsmith_connection()

    healthy = mongodb["status"] == "ok" and langsmith["status"] in ("ok", "disabled")

    return {
        "status": "ok" if healthy else "degraded",
        "mongodb": mongodb,
        "langsmith": langsmith,
    }
