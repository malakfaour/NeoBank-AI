import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from langchain_core.messages import AIMessage

from app.models.chat_session import ChatSession
from app.services.chatbot_service import (
    AGENT_HISTORY_MESSAGE_LIMIT,
    AGENT_UNAVAILABLE_REPLY,
    STORED_HISTORY_MESSAGE_LIMIT,
    _get_or_create_chat_session,
    get_chatbot_response,
    save_chat_turn,
)


async def test_lbp_balance_message_invokes_balance_tool():
    """
    NBL-510:
    - ChatGroq is fully mocked.
    - The LBP balance request reaches the balance tool.
    - The actual balance service is invoked for the authenticated user.
    - The chat turn is persisted in session history.
    """
    db = AsyncMock()

    session = ChatSession(
        session_id="test-lbp-session",
        user_id=1,
        messages=[],
    )

    balances = {
        "user_id": 1,
        "balances": [
            {
                "currency": "USD",
                "balance": 100.0,
                "account_number": "USD001",
                "iban": "LB00USD001",
            },
            {
                "currency": "LBP",
                "balance": 250000.0,
                "account_number": "LBP001",
                "iban": "LB00LBP001",
            },
            {
                "currency": "USDT",
                "balance": 50.0,
                "account_number": "USDT001",
                "iban": "LB00USDT001",
            },
        ],
    }

    captured_tools = []

    class FakeAgent:
        async def ainvoke(self, payload):
            assert (
                payload["messages"][-1]["content"]
                == "What is my LBP balance?"
            )

            balance_tool = next(
                tool
                for tool in captured_tools
                if tool.name == "get_balance"
            )

            tool_output = await balance_tool.ainvoke({})

            assert '"currency": "LBP"' in tool_output
            assert "250000.0" in tool_output

            return {
                "messages": [
                    AIMessage(
                        content="Your LBP balance is 250000.0."
                    )
                ]
            }

    def fake_create_agent(
        *,
        model,
        tools,
        system_prompt,
        middleware,
    ):
        captured_tools.extend(tools)

        assert model is not None
        assert system_prompt
        assert len(middleware) == 1

        return FakeAgent()

    with (
        patch(
            "app.services.chatbot_service._get_or_create_chat_session",
            new=AsyncMock(return_value=session),
        ),
        patch(
            "app.services.chatbot_service.get_user_balances",
            new=AsyncMock(return_value=balances),
        ) as mock_get_balances,
        patch(
            "app.services.chatbot_service.ChatGroq",
        ) as mock_chatgroq,
        patch(
            "app.services.chatbot_service.create_agent",
            side_effect=fake_create_agent,
        ),
    ):
        reply = await get_chatbot_response(
            message="What is my LBP balance?",
            session_id="test-lbp-session",
            user_id=1,
            db=db,
        )

    mock_chatgroq.assert_called_once()

    mock_get_balances.assert_awaited_once_with(
        user_id=1,
        db=db,
    )

    assert reply == "Your LBP balance is 250000.0."

    assert session.messages == [
        {
            "role": "user",
            "content": "What is my LBP balance?",
        },
        {
            "role": "assistant",
            "content": "Your LBP balance is 250000.0.",
        },
    ]

    db.commit.assert_awaited_once()


async def test_agent_history_and_stored_history_are_bounded():
    db = AsyncMock()
    original_messages = [
        {"role": "user" if index % 2 == 0 else "assistant", "content": str(index)}
        for index in range(STORED_HISTORY_MESSAGE_LIMIT + 20)
    ]
    session = ChatSession(
        session_id="bounded-history",
        user_id=1,
        messages=original_messages,
    )
    captured_payload = {}

    class FakeAgent:
        async def ainvoke(self, payload):
            captured_payload.update(payload)
            return {"messages": [AIMessage(content="bounded reply")]}

    with (
        patch(
            "app.services.chatbot_service._get_or_create_chat_session",
            new=AsyncMock(return_value=session),
        ),
        patch("app.services.chatbot_service.ChatGroq"),
        patch(
            "app.services.chatbot_service.create_agent",
            return_value=FakeAgent(),
        ),
    ):
        await get_chatbot_response(
            message="new message",
            session_id=session.session_id,
            user_id=1,
            db=db,
        )

    # The cap covers prior messages; the current user message is appended.
    assert len(captured_payload["messages"]) == AGENT_HISTORY_MESSAGE_LIMIT + 1
    assert captured_payload["messages"][0]["content"] == "100"
    assert len(session.messages) == STORED_HISTORY_MESSAGE_LIMIT
    assert session.messages[-2]["content"] == "new message"
    assert session.messages[-1]["content"] == "bounded reply"


async def test_agent_failure_returns_and_persists_honest_fallback():
    db = AsyncMock()
    session = ChatSession(
        session_id="agent-failure",
        user_id=1,
        messages=[],
    )
    failing_agent = MagicMock()
    failing_agent.ainvoke = AsyncMock(side_effect=TimeoutError("Groq timed out"))

    with (
        patch(
            "app.services.chatbot_service._get_or_create_chat_session",
            new=AsyncMock(return_value=session),
        ),
        patch("app.services.chatbot_service.ChatGroq"),
        patch(
            "app.services.chatbot_service.create_agent",
            return_value=failing_agent,
        ),
    ):
        reply = await get_chatbot_response(
            message="Can you help?",
            session_id=session.session_id,
            user_id=1,
            db=db,
        )

    assert reply == AGENT_UNAVAILABLE_REPLY
    assert session.messages[-1]["content"] == AGENT_UNAVAILABLE_REPLY
    db.commit.assert_awaited_once()


async def test_chat_session_write_query_uses_row_lock():
    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = ChatSession(
        session_id="locked-session",
        user_id=1,
        messages=[],
    )
    db.execute.return_value = result

    await _get_or_create_chat_session(
        db,
        user_id=1,
        session_id="locked-session",
        for_update=True,
    )

    query = db.execute.await_args.args[0]
    assert query._for_update_arg is not None


async def test_concurrent_save_chat_turn_calls_preserve_both_turns():
    db = AsyncMock()
    session = ChatSession(
        session_id="concurrent-session",
        user_id=1,
        messages=[],
    )
    lock = asyncio.Lock()

    async def get_locked_session(*args, **kwargs):
        await lock.acquire()
        return session

    async def commit_and_unlock():
        lock.release()

    db.commit.side_effect = commit_and_unlock

    with patch(
        "app.services.chatbot_service._get_or_create_chat_session",
        side_effect=get_locked_session,
    ):
        await asyncio.gather(
            save_chat_turn(db, 1, session.session_id, "first", "reply one"),
            save_chat_turn(db, 1, session.session_id, "second", "reply two"),
        )

    assert len(session.messages) == 4
    assert {item["content"] for item in session.messages} == {
        "first",
        "reply one",
        "second",
        "reply two",
    }
