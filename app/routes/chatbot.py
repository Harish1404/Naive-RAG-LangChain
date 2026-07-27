from fastapi import APIRouter
from app.ai.chat import ChatService
from fastapi.responses import StreamingResponse

router = APIRouter(tags=["Chatbot"])

@router.post("/chatbot")
async def chatbot(model_type: str, user_prompt: str):
    service = ChatService(model_type=model_type, user_prompt=user_prompt)

    stream_generator = service.chat()

    # Wrap the generator in FastAPI's StreamingResponse
    return StreamingResponse(
        stream_generator,      # The async generator that yields text chunks
        media_type="text/event-stream",  #SSE(Server Sent Events) format
        status_code=200,
    )



