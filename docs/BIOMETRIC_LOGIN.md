# Biometric Login API Contract

All paths are relative to `/api/v1`. The client generates and retains the Ed25519 private key. The backend receives only a PEM-encoded Ed25519 public key. Signatures are base64-encoded.

## `POST /auth/biometric/enroll` (Bearer access token required)

Request: `{"device_id":"device-123","public_key":"-----BEGIN PUBLIC KEY-----\n..."}`

Response: `{"id":1,"user_id":42,"device_id":"device-123","public_key":"-----BEGIN PUBLIC KEY-----\n...","created_at":"2026-07-10T12:00:00Z","last_used_at":null}`. Re-enrolling the same device for the current user updates its public key.

## `GET /auth/biometric/challenge` (Bearer access token required)

Response: `{"nonce":"random-url-safe-value"}`. The nonce expires after two minutes and can be consumed only once.

## `POST /auth/biometric/login` (public)

Request: `{"device_id":"device-123","signed_nonce":"base64-ed25519-signature"}` or `{"user_id":42,"signed_nonce":"base64-ed25519-signature"}`. Supply exactly one identifier. Sign the UTF-8 bytes of the nonce returned by the challenge endpoint.

Success: `{"access_token":"...","refresh_token":"...","token_type":"bearer"}`.

Failure: HTTP 401 with `{"detail":"Invalid credentials"}` for an expired, missing, reused, or incorrectly signed nonce.
