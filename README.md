# NeoBank Lebanon 🏦

An AI-enhanced digital banking platform inspired by Neo by Bank Audi, built as a full-stack fintech project with real ML integration.

## Features
- Dual-currency wallets (USD, LBP, USDT)
- AI-powered KYC verification (DeepFace)
- Real-time fraud detection (XGBoost)
- Automatic spending categorization
- AI financial assistant chatbot (Llama 3 via Groq)
- Smart financial insights

## Tech Stack
| Layer | Technology |
|-------|-----------|
| Frontend | Next.js, React, Tailwind CSS, TypeScript |
| Backend | FastAPI, SQLAlchemy, Alembic, JWT |
| Database | PostgreSQL (Neon) |
| Cache | Redis (Upstash) |
| ML | DeepFace, XGBoost, LangChain, Llama 3 |
| Deployment | Vercel, Railway |

## Project Structure
neobank-lebanon/

├── frontend/      # Next.js app

├── backend/       # FastAPI app

├── ml/            # ML models and services

└── docs/          # Documentation

## Team
7-person team | 6–8 week timeline

## Setup
1. Clone the repo
2. Copy `.env.example` to `.env` and fill in your keys
3. See `/frontend/README.md` for frontend setup. For branching, commits, pull requests, and all engineering conventions, see [docs/ENGINEERING_RULES.md](docs/ENGINEERING_RULES.md).

## Running the Celery Worker

Start Redis:
docker compose up redis -d

Start the worker (local, outside Docker):
cd backend
venv\Scripts\Activate.ps1   # Windows
source venv/bin/activate    # Mac/Linux
celery -A app.celery_app worker --loglevel=info --pool=solo   # Windows needs --pool=solo

Or via Docker:
docker compose up celery-worker -d

## Data Retention

Previous avatar objects are deleted from storage when a user successfully replaces
their avatar. KYC verification documents and bank statements are retained
indefinitely for compliance and audit purposes and are never deleted by application
code.

Chat conversation content is automatically deleted after the configurable
`CHATBOT_SESSION_RETENTION_DAYS` window (30 days by default), based on the
conversation's last activity. This default is an engineering placeholder and
requires product/compliance sign-off before being treated as the final policy.
