# Core-Auth — Advanced Async Authentication System

A production-ready, fully asynchronous backend authentication engine built with **FastAPI**. It implements a dual-token OAuth2 strategy with instant logout via a Redis blacklist, verified through a strict automated CI/CD pipeline.

---

## The Problem It Solves

Standard authentication systems have two critical weaknesses:

- **Single token = single point of failure.** If one secret key is compromised, all tokens — access and refresh — are exposed.
- **Logout is not real logout.** With stateless JWTs, a token stays valid until it expires even after the user logs out. An attacker who steals the token can still use it.

This project solves both.

---

## Solution Architecture

```
Client Request
      │
      ▼
FastAPI Router  ──────────────────────────────┐
  /register                                   │
  /login          ◄──── PostgreSQL            │
  /me                    (Users table)        │
  /refresh                                    │
  /logout         ◄──── Redis                 │
      │                  (Token blacklist)    │
      ▼                                       │
Dual-Token Engine ◄─────────────────────────--┘
  Access Token  → HS256, 15 min, secret_A
  Refresh Token → HS256, 7 days, secret_B (different key)
      │
      ▼
GitHub Actions Pipeline
  Ruff → Bandit → pytest (10 tests)
```

### Key Design Decisions

| Decision | Why |
|---|---|
| Dual secret keys | Access and refresh tokens signed with **different secrets** — compromising one does not affect the other |
| Redis blacklist | Logout **instantly invalidates** the token for its remaining lifespan — zero-trust enforcement |
| `NullPool` in tests | Each test gets a fresh DB connection — no async interference between test cases |
| `asynccontextmanager` lifespan | Replaces deprecated `on_event` — proper startup/shutdown for DB and Redis |
| In-memory fallback | If Redis is unavailable, blacklist falls back to in-process dict — system stays running |

---

## Endpoints

| Method | Route | Description | Auth Required |
|---|---|---|---|
| `POST` | `/auth/register` | Create new user account | No |
| `POST` | `/auth/login` | Login and receive token pair | No |
| `GET` | `/auth/me` | Get current user profile | Yes |
| `POST` | `/auth/refresh` | Rotate access token using refresh token | No |
| `POST` | `/auth/logout` | Invalidate current access token | Yes |

---

## Response Schemas

**Registration** — `UserRegistrationResponse`
```json
{
  "id": 1,
  "email": "user@example.com",
  "is_active": true,
  "is_superuser": false,
  "created_at": "2025-01-01T00:00:00Z"
}
```

**Login / Refresh** — `TokenExchangeResponse`
```json
{
  "access_token": "<jwt>",
  "refresh_token": "<jwt>",
  "token_type": "bearer"
}
```

**Logout** — `StandardActionResponse`
```json
{
  "detail": "Successfully logged out"
}
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Framework | FastAPI (async) |
| Database | PostgreSQL + SQLAlchemy 2.0 (asyncpg) |
| Cache / Blacklist | Redis |
| Auth | python-jose (JWT HS256), passlib + bcrypt |
| Testing | pytest-asyncio, httpx |
| Linting | Ruff |
| Security Scan | Bandit (SAST) |
| CI/CD | GitHub Actions |

---

## Project Structure

```
core-auth/
├── app/
│   ├── __init__.py
│   ├── main.py          # FastAPI app, routes, lifespan
│   ├── database.py      # SQLAlchemy engine, User model, session
│   ├── auth_utils.py    # JWT create/decode, password hashing
│   ├── redis_client.py  # Blacklist logic with in-memory fallback
│   └── schemas.py       # Pydantic request/response models
├── tests/
│   ├── __init__.py
│   ├── conftest.py      # Test DB setup, async client fixture
│   └── test_auth.py     # 10 end-to-end tests (all 6 spec scenarios)
├── .github/
│   └── workflows/
│       └── ci-cd.yml    # Automated pipeline
├── .env.example
├── pytest.ini
└── requirements.txt
```

---

## CI/CD Pipeline

Every push to `main` triggers:

```
1. Spin up PostgreSQL 15 + Redis 7 (health-checked)
2. Create virtualenv and install dependencies
3. Ruff — lint check (PEP8, unused imports)
4. Bandit — SAST security scan (hardcoded secrets, weak crypto)
5. pytest — 10 async integration tests
```

All stages must pass before merge is allowed.

---

## Test Coverage

| # | Test | Spec Scenario |
|---|---|---|
| 1 | `test_register_success` | Registration — correct schema, no plaintext password |
| 2 | `test_register_duplicate_email` | Registration — duplicate rejected with 400 |
| 3 | `test_login_success` | Authentication — dual tokens issued, tokens differ |
| 4 | `test_login_wrong_password` | Authentication — wrong credentials rejected |
| 5 | `test_protected_route_with_valid_token` | Security access — valid token passes |
| 6 | `test_protected_route_without_token` | Security access — no token rejected |
| 7 | `test_token_refresh` | Token rotation — new access token issued |
| 8 | `test_refresh_with_access_token_fails` | Token rotation — wrong token type rejected |
| 9 | `test_logout_success` | Session revocation — logout returns confirmation |
| 10 | `test_blacklisted_token_is_rejected` | Zero-trust — blacklisted token returns 401 |

---

## Local Setup

```bash
# 1. Clone and enter project
git clone https://github.com/Tahaahmed09/core-auth-system.git
cd core-auth

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate      # Mac/Linux
venv\Scripts\activate         # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set environment variables
cp .env.example .env
# Edit .env with your DB credentials

# 5. Start PostgreSQL and Redis (Docker)
docker run -d -p 5432:5432 -e POSTGRES_PASSWORD=postgres postgres:15
docker run -d -p 6379:6379 redis:7-alpine

# 6. Run the server
uvicorn app.main:app --reload

# 7. Run tests
pytest tests/ -v
```

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `PG_USER` | `postgres` | PostgreSQL username |
| `PG_PASS` | `postgres` | PostgreSQL password |
| `PG_HOST` | `localhost` | PostgreSQL host |
| `PG_NAME` | `auth_db` | Database name |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection URL |
| `ACCESS_SECRET_KEY` | — | JWT signing secret for access tokens |
| `REFRESH_SECRET_KEY` | — | JWT signing secret for refresh tokens (must differ) |

> **Note:** Never commit real secret keys. Change both secret keys before any production deployment.

---

## API Documentation

Interactive Swagger UI is available at `http://localhost:8000/docs` when the server is running.

Regards
Taha Ahmed
