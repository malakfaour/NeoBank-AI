# DEVATTECH-111 / SP3-504 - Notification Delivery Rules

## Channels

notify() always writes the in-app notification row first.

External delivery channels are checked separately:

- email
- push
- sms

## User preferences

User preferences are stored on the users row as:

{
  "email": true,
  "push": true,
  "sms": true
}

The existing PATCH /api/v1/users/me endpoint updates these preferences.
No second preferences endpoint should be added.

## SMS rules

SMS is sent through the existing sms_gateway.send_sms function.

SMS is sent for:

- TX_FLAGGED
- high-value transfers above HIGH_VALUE_SMS_THRESHOLD

Default threshold:

HIGH_VALUE_SMS_THRESHOLD=500

## Security-relevant exception

Security-relevant notifications ignore user preferences.

Current security-relevant types:

- TX_FLAGGED
- KYC_REJECTED

This means email/push/SMS preferences do not suppress security-relevant delivery when that channel is applicable.

The in-app notification row is always written regardless of preferences.
