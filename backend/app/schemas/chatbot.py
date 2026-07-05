from pydantic import BaseModel, Field

from app.services.chatbot_intent import IntentLabel


class ChatbotMessageRequest(BaseModel):
    message: str = Field(..., min_length=1)


class ChatbotMessageResponse(BaseModel):
    message: str
    response: str
    intent: IntentLabel
    confidence: float
    original_message: str
    confirmation_required: bool = False