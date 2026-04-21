# Multando Backend

<!-- TODO: Add logo/banner image -->

**Open-source platform for citizen documentation of traffic infractions.**

[![License: BSL 1.1](https://img.shields.io/badge/License-BSL_1.1-blue.svg)](./LICENSE)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-3776AB.svg?logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)

---

## Features

- **AI Chatbot** -- Claude-powered assistant guides users through reporting
- **Secure Evidence Capture** -- Encrypted photo/video storage with chain-of-custody metadata
- **Community Verification** -- Peer review system for report validation
- **Authority Integration** -- Direct data sync with government traffic agencies
- **Blockchain Rewards** -- MULTA token incentives on Solana for verified reports
- **Rate-Limit Safeguards** -- Anti-spam via Redis-backed sliding windows (per-IP and per-user)
- **Reporter Anonymity** -- Identity protection for citizen reporters

## Quick Start (Self-Hosting)

```bash
# 1. Clone and configure
git clone https://github.com/multando/multando-backend.git
cd multando-backend
cp .env.example .env   # Edit with your secrets

# 2. Start all services
docker compose -f docker-compose.self-host.yml up -d

# 3. Verify
curl http://localhost:8000/health
```

The API will be running at `http://localhost:8000`. Swagger docs at `/docs`.

## Architecture

| Layer | Technology |
|-------|-----------|
| Framework | FastAPI (async) |
| ORM | SQLAlchemy 2.0 (async) |
| Database | PostgreSQL + PostGIS |
| Migrations | Alembic |
| Cache / Queue | Redis |
| Task Runner | Celery + Beat |
| Object Storage | MinIO / S3-compatible |
| AI | Anthropic Claude |
| Blockchain | Solana (MULTA token) |
| Auth | JWT + API keys |

```
Client Request
     |
     v
  FastAPI (uvicorn)
     |
     +---> Routes ---> Services ---> Models ---> PostgreSQL + PostGIS
     |                    |
     |                    +---> Anthropic Claude (AI chatbot)
     |                    +---> MinIO / S3 (evidence storage)
     |                    +---> Solana RPC (rewards, staking)
     |
     +---> Celery Worker ---> Redis (broker)
              |
              +---> Reward distribution
              +---> Media processing
              +---> Notification dispatch
```

## Self-Hosting Guide

### Prerequisites

- Docker and Docker Compose
- A domain with HTTPS (for production)
- Anthropic API key (optional, for AI chatbot features)

### Configuration

1. Copy `.env.example` to `.env` and set all required values (especially `SECRET_KEY`)
2. Start services: `docker compose -f docker-compose.self-host.yml up -d`
3. Migrations run automatically on startup via the Dockerfile entrypoint
4. Create the MinIO bucket if needed (the default bucket name is `multando-evidence`)

See [.env.example](./.env.example) for all available environment variables.

### Database Migrations

```bash
# Run inside the container
docker compose -f docker-compose.self-host.yml exec multando-api alembic upgrade head

# Create a new migration
alembic revision --autogenerate -m "description"
```

## API Documentation

After starting the server, visit:

- **Swagger UI:** http://localhost:8000/docs
- **ReDoc:** http://localhost:8000/redoc

The API exposes 74 endpoints across 12 route groups including auth, reports, wallets, blockchain, admin, and authority portals.

## Contributing

We welcome contributions! See [CONTRIBUTING.md](./CONTRIBUTING.md) for:

- Development environment setup
- Code style guidelines (Black, Ruff, type hints)
- Pull request process
- CLA information

## License

This project is licensed under the [Business Source License 1.1](./LICENSE).

**What this means:**
- You are free to self-host, audit, modify, and contribute
- Governments and organizations can use it for internal/non-commercial production
- You may NOT offer it (or a derivative) as a competing commercial SaaS to third parties
- On 2030-04-20, the license automatically converts to Apache 2.0

For commercial licensing inquiries, contact licensing@multando.com.

## Hosted Version

Don't want to self-host? Use the fully managed platform at **[multando.com](https://multando.com)** which includes:

- MULTA token rewards and staking
- Partner marketplace
- Cross-city reporting network
- Priority support and SLA
- Automatic updates and scaling

---

Built by [Jerónimo SAS](https://jeronimo.co)
