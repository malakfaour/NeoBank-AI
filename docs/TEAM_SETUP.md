# NeoBank Lebanon Team Setup

This guide covers the basics needed to clone the repository and find the current development setup instructions.

## 1. Install these tools first

Everyone should install:

- Git
- Node.js 22
- Python 3.12
- VS Code or another code editor

PostgreSQL and Redis are optional local installs. The repository's Docker Compose setup can run both services for you.

## 2. Clone the repository

Run:

```bash
git clone https://github.com/malakfaour/neobank-lebanon.git
cd neobank-lebanon
```

## 3. Create a task branch

Create a fresh ticket-based branch from the latest `develop` when you start a task. Do not reuse long-lived, per-domain feature branches.

The sources of truth for branch names, commits, pull requests, and the daily workflow are:

- [CONTRIBUTING.md](../CONTRIBUTING.md)
- [Engineering rules](ENGINEERING_RULES.md), especially section 1

## 4. Set up the development environment

Use these tracked files for the current setup:

- [`docker-compose.yml`](../docker-compose.yml) defines the application services and local PostgreSQL and Redis dependencies.
- [`.env.example`](../.env.example) lists the environment variables to configure.
- [`frontend/README.md`](../frontend/README.md) contains the frontend setup instructions; its dependencies are defined in [`frontend/package.json`](../frontend/package.json).
- [`backend/requirements.txt`](../backend/requirements.txt) contains the backend Python dependencies.
- [`ml/requirements.txt`](../ml/requirements.txt) contains the machine-learning Python dependencies.

A dedicated `backend/README.md` is still pending. Until it is added, use the backend requirements, environment example, and Docker Compose configuration above.

## 5. Team rules

- Do not work directly on `main` or `develop`.
- Do not delete branches.
- Do not push to someone else's branch.
- Fetch the latest `develop` before creating a task branch.

For the complete and authoritative rules, read the [engineering rules](ENGINEERING_RULES.md).

## 6. Current project folders

The repository currently includes:

- `frontend/` for the Next.js frontend
- `backend/` for the FastAPI backend
- `ml/` for machine-learning code
- `tools/` for supporting development services, including `gateway_stub`
- `docs/` for project documentation
