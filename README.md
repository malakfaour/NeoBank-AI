# NeoBank Lebanon 🏦

An AI-enhanced digital banking platform inspired by Neo by Bank Audi, built as a full-stack fintech project with real ML integration and a full compliance/admin back office.

## Features

**Core banking**
- Dual-currency wallets (USD, LBP, USDT) with wallet locking and status controls
- Peer-to-peer transfers, beneficiary management (mobile and IBAN), and bill payments
- Currency exchange with live rates, exchange forecasting, and audit logging
- Top-ups via Stripe (with 3D Secure)
- Transaction history, categorization, and statement generation

**Identity & security**
- AI-powered KYC verification with liveness detection and document matching (DeepFace)
- Passcode login, biometric login, OTP verification, and device/session management
- Rate limiting and action-token confirmation on sensitive operations

**AI / ML**
- Real-time fraud detection and scoring (XGBoost, Isolation Forest)
- Automatic spending categorization
- AI financial assistant chatbot (Llama 3 via Groq) with transfer confirmation flows
- Exchange rate forecasting

**Compliance & admin console**
- Admin KYC review queue with document viewer
- Flagged transactions / fraud resolution queue
- User management (search, suspend/activate)
- Wallet administration
- Full audit logging (KYC, transactions, exchange, account status)

**Notifications**
- Email and push notifications (FCM), with configurable retention

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 16, React 19, Tailwind CSS, TypeScript, Zustand |
| Backend | FastAPI, SQLAlchemy, Alembic, JWT, Celery |
| Database | PostgreSQL (Neon) |
| Cache / Queue | Redis (Upstash) |
| ML | DeepFace, XGBoost, LightGBM, Isolation Forest, LangChain, Llama 3 (Groq) |
| Payments | Stripe |
| Messaging | SendGrid/SMTP (email), Firebase Cloud Messaging (push) |
| Storage | AWS S3 |
| Testing | Pytest, Playwright, Vitest |
| Deployment | Vercel, Railway |

## Project Structure

```
neobank-lebanon/
├── frontend/    # Next.js app (auth, onboarding, dashboard, admin console)
├── backend/     # FastAPI app (API, models, services, ML integration, Celery tasks)
├── ml/          # ML training code and models (fraud, KYC, exchange forecasting)
├── tools/       # Supporting dev services (e.g. gateway_stub)
└── docs/        # Documentation and engineering rules
```

### Backend API surface (`backend/app/api/v1/endpoints`)
Auth, passcode, biometric, sessions, users, accounts, wallets, transfers, transactions, beneficiaries, bills, exchange, KYC, chatbot, notifications, and admin endpoints for fraud, KYC, and wallets.

### Frontend routes (`frontend/app`)
Auth flow (login, register, OTP, passcode, password reset, unlock), onboarding/KYC, and a dashboard covering wallet home, transfers, add money, beneficiaries, bills, exchange, transactions, notifications, devices, profile, and an admin section (users, KYC, flagged transactions, transactions).

## Team

7-person team | 6–8 week timeline

## Setup

1. Clone the repo:
   ```bash
   git clone https://github.com/malakfaour/neobank-lebanon.git
   cd neobank-lebanon
   ```
2. Install prerequisites: Git, Node.js 22, Python 3.12. PostgreSQL and Redis can be run locally via Docker Compose (`docker-compose.yml`).
3. Root `.env` (backend/ML — copy `.env.example` to `.env`): database, Redis, JWT/OTP, KYC thresholds, DeepFace/Groq, AWS S3, FCM, email provider, Stripe secret key, payment gateway/biller URLs, and app-level limits/thresholds.
4. Frontend `.env.local` (create under `frontend/`, not tracked in git): `NEXT_PUBLIC_API_URL` and `NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY` (Stripe **publishable** key — the secret key stays in the root `.env` only). See [`frontend/README.md`](frontend/README.md) for full frontend setup (dependencies in `frontend/package.json`).
5. See `backend/requirements.txt` and `ml/requirements.txt` for backend and ML Python dependencies.
6. For branching, commits, pull requests, and all engineering conventions, see [docs/ENGINEERING_RULES.md](docs/ENGINEERING_RULES.md) and [docs/TEAM_SETUP.md](docs/TEAM_SETUP.md).

> **Note:** keep `.env` and `frontend/.env.local` out of version control (both are git-ignored) — never commit real secrets. `.env.example` should be kept in sync whenever a new environment variable is introduced.

## Running the Celery Worker

Start Redis:
```bash
docker compose up redis -d
```

Start the worker (local, outside Docker):
```bash
cd backend
venv\Scripts\Activate.ps1   # Windows
source venv/bin/activate    # Mac/Linux
celery -A app.celery_app worker --loglevel=info --pool=solo   # Windows needs --pool=solo
```

Or via Docker:
```bash
docker compose up celery-worker -d
```

## Documentation

- [Engineering rules](docs/ENGINEERING_RULES.md) — branching, commits, PRs, and daily workflow (source of truth)
- [Team setup](docs/TEAM_SETUP.md) — onboarding steps for new contributors
- [Ops](docs/OPS.md)
- [Biometric login](docs/BIOMETRIC_LOGIN.md)
- [Chatbot confirm card](docs/DEVATTECH-110_CHATBOT_CONFIRM_CARD.md)
- [Notification delivery](docs/DEVATTECH-111_NOTIFICATION_DELIVERY.md)

## Data Retention

Previous avatar objects are deleted from storage when a user successfully replaces their avatar. KYC verification documents and bank statements are retained indefinitely for compliance and audit purposes and are never deleted by application code.

Chat conversation content is automatically deleted after the configurable `CHATBOT_SESSION_RETENTION_DAYS` window (30 days by default), based on the conversation's last activity. This default is an engineering placeholder and requires product/compliance sign-off before being treated as the final policy.
