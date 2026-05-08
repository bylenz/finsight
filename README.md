# FinSight 💸

> **AI-powered personal finance tracker for LATAM.** Privacy-first, multi-currency, conversational AI in Spanish — no banking credentials required.

[![CI](https://github.com/bylenz/finsight/actions/workflows/ci.yml/badge.svg)](https://github.com/bylenz/finsight/actions/workflows/ci.yml)

## Why FinSight

Mint, YNAB, and Fintonic don't speak the local language: Yape, Plin, soles, RHP, freelancers under SUNAT. **FinSight is built for that reality** — Spanish-first, multi-currency (PEN/USD), and household-aware.

## Stack

| Layer       | Choice                                    |
| ----------- | ----------------------------------------- |
| Backend     | FastAPI + SQLAlchemy 2.x async + Alembic  |
| Frontend    | Streamlit                                 |
| DB          | PostgreSQL 16                             |
| LLM         | Anthropic Claude API                      |
| Auth        | JWT (`python-jose` + `passlib[bcrypt]`)   |
| Pkg manager | `uv` (workspace)                          |
| Container   | Docker Compose                            |
| CI          | GitHub Actions (ruff, black, pytest, cov) |

## Quickstart

```bash
git clone https://github.com/bylenz/finsight.git
cd finsight
cp env.example .env       # fill ANTHROPIC_API_KEY and JWT_SECRET
docker compose up --build
```

Services:

- Backend API → http://localhost:8000/docs
- Streamlit UI → http://localhost:8501
- Adminer (DB) → http://localhost:8080

## Local development

```bash
uv sync                              # resolve workspace
uv run pytest --cov                  # run tests
uv run ruff check . && uv run black --check .
pre-commit install                   # enable hooks
```

## Repo layout

```
finsight/
  backend/                # FastAPI service
    src/finsight/         # auth, expenses, budgets, insights, ...
    tests/
    migrations/           # Alembic
    Dockerfile
  frontend/               # Streamlit UI
    src/finsight_ui/
    Dockerfile
  docs/
    PRD.md
    BRANCHING.md
    ARCHITECTURE.md
  scripts/
  docker-compose.yml
  pyproject.toml          # uv workspace
```

## Branching

We follow **GitFlow**:

- `main` — production, protected. PR-only.
- `develop` — integration. PR-only.
- `feature/<name>` — branch from `develop`, merge back via PR.
- `release/x.y` — hardening before tagging `main`.
- `hotfix/x.y.z` — emergency fix on top of `main`.

Commit messages follow **Conventional Commits**: `feat(auth): add JWT login`. PR titles are linted.

See [`docs/BRANCHING.md`](docs/BRANCHING.md) for the full flow.

## Contributors

| Member                        | GitHub             |
| ----------------------------- | ------------------ |
| Lenin Chavez (Tech Lead)      | [@bylenz](https://github.com/bylenz)                   |
| Jerimy Sandoval               | [@Jerimy2021](https://github.com/Jerimy2021)           |
| Adrian Cespedes               | [@Adrian-Cespedes](https://github.com/Adrian-Cespedes) |

## License

MIT — see [LICENSE](LICENSE).
