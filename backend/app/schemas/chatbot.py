from pydantic import BaseModel, Field


class ChatbotMessageRequest(BaseModel):
    message: str = Field(..., min_length=1)


class ChatbotMessageResponse(BaseModel):
    message: str
    response: str