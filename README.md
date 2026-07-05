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
3. See `/backend/README.md` and `/frontend/README.md` for setup instructions

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