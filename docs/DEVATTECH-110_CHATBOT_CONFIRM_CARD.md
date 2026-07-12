# DEVATTECH-110 - Chatbot Transfer Confirm Card Contract

## Endpoint

POST /api/v1/chatbot/message

Requires the normal Bearer token.

## Start a transfer

Request body:

{
  "session_id": "chat-session-123",
  "message": "send 10 USD to +96170123456"
}

Response when the chatbot extracts a complete transfer draft:

{
  "reply": "Please confirm this transfer: 10 USD to +96170123456. To proceed, verify your passcode and send confirm with the action token.",
  "session_id": "chat-session-123",
  "intent": "TRANSFER_INTENT",
  "confidence": 0.92,
  "confirmation_required": true,
  "pending_action": {
    "type": "transfer",
    "method": "mobile",
    "recipient": "+96170123456",
    "amount": "10",
    "currency": "USD"
  },
  "transfer_receipt": null
}

The backend stores the pending action in Redis:

chat_action:{session_id}

TTL: 5 minutes.

## Confirm flow

1. User starts a transfer in the chatbot.
2. Backend returns confirmation_required=true and pending_action.
3. Frontend displays a confirm card using pending_action.
4. User verifies passcode using POST /api/v1/auth/passcode/verify.
5. Frontend sends a confirm message to POST /api/v1/chatbot/message.

Confirm request body:

{
  "session_id": "chat-session-123",
  "message": "confirm"
}

Required header:

X-Action-Token: <action_token>

Success response:

{
  "reply": "Transfer completed: 10 USD to Receiver Name.",
  "session_id": "chat-session-123",
  "intent": "GENERAL",
  "confidence": 0.0,
  "confirmation_required": false,
  "pending_action": null,
  "transfer_receipt": {
    "transaction_id": 123,
    "amount": "10",
    "currency": "USD",
    "receiver_display_name": "Receiver Name",
    "sender_new_balance": "90",
    "timestamp": "2026-07-12T10:00:00"
  }
}

## Cancel flow

Request body:

{
  "session_id": "chat-session-123",
  "message": "cancel"
}

The backend deletes chat_action:{session_id} and returns confirmation_required=false.

## Security rules

- A transfer intent never executes directly.
- The only execution path is the existing transfer service.
- Confirmation requires a valid single-use action_token.
- Missing, expired, replayed, or another user's action token returns 403.
- Pending actions expire after 5 minutes.
- The pending action stores the authenticated user_id; another user cannot confirm it.
