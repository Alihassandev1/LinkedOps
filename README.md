# LinkedOps — Backend

FastAPI + PostgreSQL backend for the LinkedIn automation platform.

---

## Stack
- **FastAPI** — async web framework
- **SQLAlchemy 2.0** — async ORM
- **PostgreSQL** — primary database (via asyncpg)
- **Alembic** — database migrations
- **python-jose** — JWT auth
- **passlib[bcrypt]** — password hashing
- **cryptography (Fernet)** — LinkedIn token encryption
- **APScheduler** — background post scheduler (next phase)
- **httpx** — async LinkedIn API calls (next phase)

---

## Local Setup

### 1. Prerequisites
```bash
# Install PostgreSQL (macOS)
brew install postgresql@16 && brew services start postgresql@16

# Install PostgreSQL (Ubuntu/WSL)
sudo apt install postgresql postgresql-contrib -y
sudo service postgresql start
```

### 2. Create the database
```bash
psql -U postgres
CREATE DATABASE linkedops;
\q
```

### 3. Clone & set up Python environment
```bash
cd linkedops-backend
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 4. Configure environment
```bash
cp .env.example .env
# Edit .env and fill in:
#   DATABASE_URL, JWT_SECRET_KEY, FERNET_KEY
#   (LinkedIn + OpenRouter keys can be added later)
```

#### Generate required secret keys:
```bash
# JWT secret (just a long random string)
python -c "import secrets; print(secrets.token_hex(32))"

# Fernet key (for encrypting LinkedIn tokens)
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### 5. Run database migrations
```bash
# For local dev, tables auto-create on startup via SQLAlchemy.
# When you want proper migrations:
alembic revision --autogenerate -m "initial tables"
alembic upgrade head
```

### 6. Start the server
```bash
uvicorn app.main:app --reload --port 8000
```

Server runs at: http://localhost:8000  
API docs at:    http://localhost:8000/docs

---

## Project Structure
```
linkedops/
├── app/
│   ├── main.py                  # FastAPI app factory
│   ├── api/
│   │   └── v1/
│   │       ├── router.py        # Aggregates all routers
│   │       └── endpoints/
│   │           ├── auth.py      # /api/v1/auth/*
│   │           └── posts.py     # /api/v1/posts/*
│   ├── core/
│   │   ├── config.py            # Settings from .env
│   │   ├── security.py          # JWT, bcrypt, Fernet
│   │   └── deps.py              # FastAPI dependencies
│   ├── db/
│   │   └── session.py           # Async engine + Base
│   ├── models/
│   │   ├── user.py              # User table
│   │   ├── linkedin_account.py  # LinkedIn OAuth accounts
│   │   └── post.py              # Scheduled/published posts
│   ├── schemas/
│   │   ├── auth.py              # Register/login/token schemas
│   │   └── post.py              # Post CRUD + AI schemas
│   └── services/
│       ├── user_service.py      # User DB queries
│       └── auth_service.py      # Register/login/refresh logic
├── alembic/                     # DB migrations
├── tests/
│   └── test_auth.py
├── .env.example
├── requirements.txt
└── README.md
```

---

## API Endpoints

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/api/v1/auth/register` | ❌ | Create account |
| POST | `/api/v1/auth/login` | ❌ | Login, get tokens |
| POST | `/api/v1/auth/refresh` | ❌ | Refresh access token |
| GET | `/api/v1/auth/me` | ✅ | Get current user |
| POST | `/api/v1/posts/` | ✅ | Create post |
| GET | `/api/v1/posts/` | ✅ | List all posts |
| GET | `/api/v1/posts/{id}` | ✅ | Get single post |
| PATCH | `/api/v1/posts/{id}` | ✅ | Update post |
| DELETE | `/api/v1/posts/{id}` | ✅ | Delete post |
| GET | `/api/v1/linkedin/connect` | ✅ | Get LinkedIn OAuth URL |
| GET | `/api/v1/linkedin/callback` | ❌ | OAuth callback (LinkedIn redirects here) |
| GET | `/api/v1/linkedin/accounts` | ✅ | List connected accounts |
| DELETE | `/api/v1/linkedin/accounts/{id}` | ✅ | Disconnect an account |
| PATCH | `/api/v1/linkedin/accounts/{id}/default` | ✅ | Set default account |
| POST | `/api/v1/ai/generate` | ✅ | Generate new post from topic |
| POST | `/api/v1/ai/enhance` | ✅ | Polish an existing draft |
| POST | `/api/v1/ai/regenerate` | ✅ | New variation of a topic |
| GET | `/api/v1/scheduler/status` | ✅ | View background job status |
| POST | `/api/v1/scheduler/trigger/{job_id}` | ✅ | Manually fire a job (dev/debug) |
| GET | `/health` | ❌ | Health check |

---

## Background Jobs (Phase 4)

LinkedOps runs two scheduled jobs via APScheduler, in the same process as FastAPI:

| Job | Frequency | What it does |
|-----|-----------|---------------|
| `publish_due_posts` | Every 1 minute | Finds posts where `status=scheduled` and `scheduled_at <= now`, publishes them to LinkedIn via the UGC Posts API. Retries up to 3 times on failure before marking `failed`. |
| `refresh_expiring_tokens` | Daily at 3:00 AM UTC | Finds LinkedIn accounts whose tokens expire within 7 days, refreshes them silently using the stored refresh token. |

**Testing the publisher without waiting:**
```bash
# After scheduling a test post, trigger the job immediately instead of waiting up to 60s:
curl -X POST http://localhost:8000/api/v1/scheduler/trigger/publish_due_posts \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

**Important:** when running tests, set `APP_ENV=test` — this disables the scheduler
so background jobs don't fire against your test database mid-suite.

```bash
APP_ENV=test pytest tests/ -v
```

---

## Next Phases
- **Phase 5:** Analytics endpoints (impressions, engagement, top posts)
- **Phase 6:** Subscription & billing (Paddle integration, plan limits)
- **Phase 7:** Email notifications (Resend — post published, post failed, weekly digest)
