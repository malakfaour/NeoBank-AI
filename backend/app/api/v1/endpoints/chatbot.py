from fastapi import APIRouter

from app.schemas.chatbot import ChatbotMessageRequest, ChatbotMessageResponse
from app.services.chatbot_service import get_chatbot_response

router = APIRouter()


@router.post(
    "/message",
    response_model=ChatbotMessageResponse,
    summary="Send a message to the chatbot",
)
async def send_chatbot_message(
    body: ChatbotMessageRequest,
) -> ChatbotMessageResponse:
    response = get_chatbot_response(body.message)

    return ChatbotMessageResponse(
        message=body.message,
        response=response,
    )