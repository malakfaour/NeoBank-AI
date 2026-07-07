from unittest.mock import AsyncMock, patch

from langchain_core.messages import AIMessage

from app.models.chat_session import ChatSession
from app.services.chatbot_service import get_chatbot_response


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