# Multando Backend API

![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![Python](https://img.shields.io/badge/Python_3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-4169E1?style=for-the-badge&logo=postgresql&logoColor=white)
![Redis](https://img.shields.io/badge/Redis-DC382D?style=for-the-badge&logo=redis&logoColor=white)
![Solana](https://img.shields.io/badge/Solana-9945FF?style=for-the-badge&logo=solana&logoColor=white)

> Traffic violation reporting platform backend with blockchain rewards. Citizens report violations, earn **MULTA** tokens on Solana, and authorities access verified data through a unified API.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Framework | FastAPI (async) |
| ORM | SQLAlchemy 2.0 (async) |
| Database | PostgreSQL + PostGIS |
| Cache / Queue | Redis |
| Task Runner | Celery + Beat |
| Blockchain | Solana (solana-py, anchorpy) |
| Auth | JWT (access + refresh) + API keys |
| Deployment | Railway (Docker) |

## Key Features

- **74 REST endpoints** across 12 route groups
- **JWT + API key authentication** with role-based access control
- **Custodial wallets** -- automatic Solana keypair creation per user
- **Rate limiting** -- per-IP and per-user with Redis-backed sliding windows
- **RECORD integration** -- government traffic authority data sync
- **PostGIS geospatial** queries for location-based reports
- **Celery workers** for async reward distribution, media processing, and notifications
- **Alembic migrations** for schema versioning

## Quick Start

### With Docker (recommended)

```bash
docker compose up --build
```

The API will be available at `http://localhost:8000`. Swagger docs at `/docs`.

### Without Docker

```bash
# Install dependencies
pip install -e ".[dev]"

# Run migrations
alembic upgrade head

# Start the server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Start the Celery worker and beat scheduler separately:

```bash
celery -A app.worker worker --loglevel=info
celery -A app.worker beat --loglevel=info
```

## Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql+asyncpg://user:pass@localhost/multando` |
| `REDIS_URL` | Redis connection string | `redis://localhost:6379/0` |
| `JWT_SECRET_KEY` | Secret for signing JWT tokens | `your-secret-key` |
| `JWT_ALGORITHM` | JWT signing algorithm | `HS256` |
| `SOLANA_RPC_URL` | Solana RPC endpoint | `https://api.devnet.solana.com` |
| `MULTA_MINT_ADDRESS` | SPL token mint address | `MULTA...` |
| `AUTHORITY_KEYPAIR` | Base58 encoded authority keypair | `[...]` |
| `WHATSAPP_VERIFY_TOKEN` | WhatsApp webhook verification | `your-verify-token` |
| `ANTHROPIC_API_KEY` | Claude API key (chatbot features) | `sk-ant-...` |
| `S3_BUCKET` | Media storage bucket | `multando-uploads` |
| `ALLOWED_ORIGINS` | CORS origins (comma-separated) | `https://multando.com` |

## API Endpoint Groups

| Group | Prefix | Endpoints | Description |
|-------|--------|-----------|-------------|
| Auth | `/api/v1/auth` | 8 | Register, login, refresh, password reset |
| Reports | `/api/v1/reports` | 12 | Create, list, update, verify violations |
| Wallet | `/api/v1/wallet` | 7 | Balance, transactions, custodial management |
| Blockchain | `/api/v1/blockchain` | 6 | Rewards, staking, token distribution |
| Users | `/api/v1/users` | 8 | Profile, preferences, achievements |
| Cities | `/api/v1/cities` | 5 | Supported cities and jurisdictions |
| Admin | `/api/v1/admin` | 10 | User management, analytics, moderation |
| Authority | `/api/v1/authority` | 6 | Government portal, bulk data access |
| Developers | `/api/v1/developers` | 4 | API key management, SDK config |
| Achievements | `/api/v1/achievements` | 4 | Badges, streaks, leaderboard |
| Notifications | `/api/v1/notifications` | 3 | Push, email, in-app |
| Health | `/api/v1/health` | 1 | Readiness and liveness probe |

## Architecture

```
Client Request
     |
     v
  FastAPI (uvicorn)
     |
     +---> Routes ---> Services ---> Models ---> PostgreSQL + PostGIS
     |                    |
     |                    +---> Solana RPC (rewards, staking)
     |                    +---> S3 (media uploads)
     |
     +---> Celery Worker ---> Redis (broker)
              |
              +---> Reward distribution
              +---> Media processing
              +---> Notification dispatch
              +---> RECORD data sync
```

## Database Migrations

```bash
# Create a new migration
alembic revision --autogenerate -m "description"

# Apply all pending migrations
alembic upgrade head

# Rollback one migration
alembic downgrade -1
```

## Testing

```bash
pytest tests/ -v
```

## Deployment

Railway configuration is included via `railway.toml`, `railway.worker.toml`, and `railway.beat.toml`. The project deploys as three services:

1. **API** -- the main FastAPI server
2. **Worker** -- Celery task worker
3. **Beat** -- Celery periodic task scheduler

## License

All rights reserved. Proprietary software.
