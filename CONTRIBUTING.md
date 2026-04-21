# Contributing to Multando Backend

Welcome! We appreciate your interest in contributing to Multando. This document provides guidelines for contributing to the project.

## Development Environment Setup

### Prerequisites

- Python 3.11+
- PostgreSQL 16+ (with PostGIS)
- Redis 7+
- MinIO (or S3-compatible storage)

### Quick Setup with Docker

```bash
docker compose up -d postgres redis minio
```

### Manual Setup

1. Clone the repository and create a virtual environment:

```bash
git clone https://github.com/multando/multando-backend.git
cd multando-backend
python -m venv .venv
source .venv/bin/activate
```

2. Install dependencies:

```bash
pip install -e ".[dev]"
```

3. Copy and configure environment variables:

```bash
cp .env.example .env
# Edit .env with your local settings
```

4. Run database migrations:

```bash
alembic upgrade head
```

5. Start the development server:

```bash
uvicorn app.main:app --reload
```

## Running Tests

```bash
pytest tests/ -v
```

## Code Style

- **Formatter:** [Black](https://github.com/psf/black) (default config)
- **Linter:** [Ruff](https://github.com/astral-sh/ruff)
- **Type hints:** Required on all function signatures

Run formatting and linting before submitting:

```bash
black .
ruff check . --fix
```

## License Headers

All new source files should include the following header:

```python
# SPDX-License-Identifier: BSL-1.1
# Copyright (c) 2026 Jerónimo SAS
```

## Pull Request Process

1. **Fork** the repository
2. **Create a branch** from `main` (e.g., `feat/my-feature` or `fix/issue-123`)
3. **Make your changes** with clear, atomic commits
4. **Add tests** for new functionality
5. **Run the test suite** and ensure all tests pass
6. **Open a Pull Request** against `main`
7. **Wait for review** — a maintainer will review your PR

### PR Guidelines

- Keep PRs focused on a single concern
- Update documentation if you change behavior
- Add a description explaining *why* the change is needed

## Contributor License Agreement (CLA)

By submitting a pull request, you agree that your contributions are licensed under the same BSL 1.1 license that covers this project. You certify that you have the right to submit the work under this license.

## Code of Conduct

This project follows the [Contributor Covenant Code of Conduct](https://www.contributor-covenant.org/version/2/1/code_of_conduct/). By participating, you are expected to uphold this code. Please report unacceptable behavior to conduct@multando.com.

## Reporting Issues

- Use GitHub Issues for bug reports and feature requests
- Include steps to reproduce for bugs
- Include your environment details (OS, Python version, etc.)
- Check existing issues before creating a new one

## Questions?

Open a Discussion on GitHub or reach out at dev@multando.com.
