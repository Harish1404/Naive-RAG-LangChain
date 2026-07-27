import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI

from app.routes.chatbot import router as chatbot_router
from app.rag.rag_pipeline import rag_pipeline
from app.db.mongodb import connect_to_mongo, close_mongo_connection
# Configure logging to output INFO level logs to terminal
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger("uvicorn.error")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("App startup")
    await connect_to_mongo()
    chunk_count = await rag_pipeline.ingest("uploads")
    logger.info(f"RAG startup ingestion complete: {chunk_count} new chunk(s) indexed.")
    yield
    logger.info("App shutdown")
    await close_mongo_connection()


app = FastAPI(lifespan=lifespan)
app.include_router(chatbot_router)



@app.get("/")
def landing_page():
    return {
        "message": " Hi this is your backend server"
    }

@app.get("/health")
def health():
    return {
        "status": "Your backend server is good"
    }
