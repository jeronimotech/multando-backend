# Multando API

FastAPI backend service for the Multando platform.

## Features

- User authentication (JWT)
- Report management
- Verification system
- Gamification (points, levels, badges)
- Blockchain integration (MULTA token)

## Development

```bash
# Install dependencies
pip install -e ".[dev]"

# Run migrations
alembic upgrade head

# Seed database
python -m app.scripts.seed

# Start server
uvicorn app.main:app --reload
```

## API Documentation

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
