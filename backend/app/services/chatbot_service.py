import json
from typing import Any

from langchain.agents import create_agent
from langchain.agents.middleware import ToolCallLimitMiddleware
from langchain.tools import tool
from langchain_groq import ChatGroq
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.chat_session import ChatSession
from app.services.account_service import get_user_balances
from app.services.exchange_cache import get_latest_exchange_rate
from app.services.transaction_query_service import (
    get_recent_transactions_for_user,
)

GROQ_CHATBOT_MODEL = "llama-3.3-70b-versatile"

_SYSTEM_PROMPT = """
You are NeoBank Lebanon's secure banking assistant.

Use the available tools whenever the user asks about:
- their wallet balances,
- their recent transactions,
- the latest exchange rate.

Rules:
- Never invent balances, transactions, or exchange rates.
- Use tool results as the source of truth.
- Keep answers concise and clear.
- Never expose internal database details.
- Never claim that a transfer was completed.
- The authenticated user's identity is already securely bound to the tools.
""".strip()


class ChatSessionOwnershipError(Exception):
    """Raised when a chat session belongs to another user."""


def _json_text(value: Any) -> str:
    return json.dumps(
        value,
        default=str,
        ensure_ascii=False,
    )


def build_chatbot_tools(
    user_id: int,
    db: AsyncSession,
) -> list[Any]:
    """
    Build tools bound to the authenticated user and current DB session.

    The model never supplies or chooses user_id.
    """

    @tool
    async def get_balance() -> str:
        """
        Get all wallet balances for the authenticated user,
        including USD, LBP, and USDT wallets.
        """
        balances = await get_user_balances(
            user_id=user_id,
            db=db,
        )

        if balances is None:
            return _json_text(
                {
                    "error": "No wallets found for this user",
                }
            )

        return _json_text(balances)

    @tool
    async def get_recent_transactions(
        limit: int = 5,
    ) -> str:
        """
        Get the authenticated user's most recent transactions.

        The default limit is 5.
        """
        transactions = await get_recent_transactions_for_user(
            user_id=user_id,
            db=db,
            limit=limit,
        )

        return _json_text(
            {
                "transactions": transactions,
            }
        )

    @tool
    async def get_exchange_rate() -> str:
        """
        Get the latest exchange-rate payload from Redis.
        """
        exchange_rate = await get_latest_exchange_rate()

        if exchange_rate is None:
            return _json_text(
                {
                    "error": "Latest exchange rate is unavailable",
                }
            )

        return _json_text(exchange_rate)

    return [
        get_balance,
        get_recent_transactions,
        get_exchange_rate,
    ]


async def _get_or_create_chat_session(
    db: AsyncSession,
    user_id: int,
    session_id: str,
) -> ChatSession:
    result = await db.execute(
        select(ChatSession).where(
            ChatSession.session_id == session_id,
        )
    )

    session = result.scalar_one_or_none()

    if session is None:
        session = ChatSession(
            session_id=session_id,
            user_id=user_id,
            messages=[],
        )
        db.add(session)

    elif session.user_id != user_id:
        raise ChatSessionOwnershipError("Chat session belongs to another user")

    return session


async def get_chat_history(
    db: AsyncSession,
    user_id: int,
    session_id: str,
) -> list[dict[str, Any]] | None:
    """
    Return the stored conversation for an owned chat session.

    Raw message text is stored only in chat_sessions.messages.
    chatbot_logs remains analytics-only.
    """
    result = await db.execute(
        select(ChatSession).where(
            ChatSession.session_id == session_id,
        )
    )

    session = result.scalar_one_or_none()

    if session is None:
        return None

    if session.user_id != user_id:
        raise ChatSessionOwnershipError("Chat session belongs to another user")

    return list(session.messages or [])


def _history_for_agent(
    messages: list[dict[str, Any]],
) -> list[dict[str, str]]:
    history: list[dict[str, str]] = []

    for message in messages:
        role = message.get("role")
        content = message.get("content")

        if role not in {"user", "assistant", "system"}:
            continue

        if not isinstance(content, str):
            continue

        history.append(
            {
                "role": role,
                "content": content,
            }
        )

    return history


def _extract_reply(
    agent_result: dict[str, Any],
) -> str:
    messages = agent_result.get("messages", [])

    if not messages:
        raise RuntimeError("Chatbot agent returned no messages")

    content = messages[-1].content

    if isinstance(content, str):
        return content

    if isinstance(content, list):
        parts: list[str] = []

        for item in content:
            if isinstance(item, str):
                parts.append(item)

            elif isinstance(item, dict):
                text = item.get("text")

                if text is not None:
                    parts.append(str(text))

        reply = "\n".join(parts).strip()

        if reply:
            return reply

    return str(content)


async def save_chat_turn(
    db: AsyncSession,
    user_id: int,
    session_id: str,
    message: str,
    reply: str,
) -> None:
    """
    Persist one user/assistant turn to chat_sessions.messages.
    """
    session = await _get_or_create_chat_session(
        db=db,
        user_id=user_id,
        session_id=session_id,
    )

    history = list(session.messages or [])

    session.messages = [
        *history,
        {
            "role": "user",
            "content": message,
        },
        {
            "role": "assistant",
            "content": reply,
        },
    ]

    await db.commit()


async def get_chatbot_response(
    message: str,
    session_id: str,
    user_id: int,
    db: AsyncSession,
) -> str:
    """
    Run the LangChain + ChatGroq banking agent.

    Conversation history is loaded from chat_sessions.messages
    and the new user/assistant turn is persisted after success.
    """
    session = await _get_or_create_chat_session(
        db=db,
        user_id=user_id,
        session_id=session_id,
    )

    stored_history = list(session.messages or [])

    agent_messages = _history_for_agent(stored_history)

    agent_messages.append(
        {
            "role": "user",
            "content": message,
        }
    )

    model = ChatGroq(
        model=GROQ_CHATBOT_MODEL,
        temperature=0,
        api_key=settings.GROQ_API_KEY,
        max_retries=2,
    )

    tools = build_chatbot_tools(
        user_id=user_id,
        db=db,
    )

    agent = create_agent(
        model=model,
        tools=tools,
        system_prompt=_SYSTEM_PROMPT,
        middleware=[
            ToolCallLimitMiddleware(
                run_limit=8,
                exit_behavior="end",
            )
        ],
    )

    agent_result = await agent.ainvoke(
        {
            "messages": agent_messages,
        }
    )

    reply = _extract_reply(agent_result)

    session.messages = [
        *stored_history,
        {
            "role": "user",
            "content": message,
        },
        {
            "role": "assistant",
            "content": reply,
        },
    ]

    await db.commit()

    return reply
