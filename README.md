# LinkedOps

FastAPI backend for scheduling, publishing, and managing LinkedIn content. It provides JWT authentication, LinkedIn OAuth, AI-assisted post generation, background publishing, analytics, and Docker-based deployment.

## Technology Stack

- Python 3.11+
- FastAPI and Uvicorn
- SQLAlchemy 2.0 with async PostgreSQL support
- Alembic database migrations
- PostgreSQL and AsyncPG
- JWT authentication with Python-JOSE and bcrypt
- Fernet-encrypted LinkedIn OAuth tokens
- APScheduler background jobs
- OpenRouter/OpenAI-compatible AI client
- Pydantic settings and environment-based configuration

## Requirements

- Python 3.11 or newer
- PostgreSQL 16 or compatible
- Docker and Docker Compose for containerized deployment
- A LinkedIn Developer App with OAuth credentials
- An OpenRouter API key for AI features

## Local Development

### 1. Create and activate a virtual environment

```bash
python -m venv .venv

# Linux/macOS
source .venv/bin/activate

# Windows PowerShell
.venv\Scripts\Activate.ps1
```

### 2. Install dependencies

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

The project also defines an optional test dependency group in `pyproject.toml`.

### 3. Configure environment variables

Copy the example file and update the values:

```bash
Copy-Item .env.example .env
```

The required settings are:

```env
APP_NAME=LinkedOps
APP_ENV=development
DEBUG=true
FRONTEND_URL=http://localhost:5173

DATABASE_URL=postgresql+asyncpg://postgres:password@localhost:5432/linkedops

JWT_SECRET_KEY=replace-with-a-long-random-secret
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7

LINKEDIN_CLIENT_ID=your_linkedin_client_id
LINKEDIN_CLIENT_SECRET=your_linkedin_client_secret
LINKEDIN_REDIRECT_URI=http://localhost:8000/api/v1/linkedin/callback

OPENROUTER_API_KEY=your_openrouter_api_key
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
AI_MODEL=mistralai/mistral-7b-instruct

FERNET_KEY=your_fernet_key
```

Generate a Fernet key with:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### 4. Prepare PostgreSQL

Create the database referenced by `DATABASE_URL`:

```sql
CREATE DATABASE linkedops;
```

The application creates database tables automatically during startup in development. For a managed migration workflow, use Alembic commands such as:

```bash
alembic revision --autogenerate -m "initial tables"
alembic upgrade head
```

### 5. Start the API

```bash
uvicorn app.main:app --reload --port 8000
```

- API: http://localhost:8000
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- Health check: http://localhost:8000/health

## Docker

Build and run the image with Docker Compose:

```bash
Copy-Item .env.example .env

docker compose build
docker compose up -d
```

The Compose service maps port `8000` and loads environment variables from `.env`.

Build the image directly:

```bash
docker build -t linkedops:latest .
```

The production Docker image uses Python 3.11, runs as a non-root user, exposes port 8000, and includes a health check against `/health`.

## API Endpoints

### Authentication

| Method | Endpoint                | Authentication | Description                                           |
| ------ | ----------------------- | -------------- | ----------------------------------------------------- |
| POST   | `/api/v1/auth/register` | No             | Register a user and receive access and refresh tokens |
| POST   | `/api/v1/auth/login`    | No             | Log in with JSON or OAuth2-style form data            |
| POST   | `/api/v1/auth/refresh`  | No             | Exchange a refresh token for a new token pair         |
| GET    | `/api/v1/auth/me`       | Bearer token   | Return the current authenticated user                 |

### Posts

| Method | Endpoint                  | Authentication | Description                               |
| ------ | ------------------------- | -------------- | ----------------------------------------- |
| POST   | `/api/v1/posts/`          | Bearer token   | Create a draft or scheduled post          |
| GET    | `/api/v1/posts/`          | Bearer token   | List posts, optionally filtered by status |
| GET    | `/api/v1/posts/{post_id}` | Bearer token   | Get one post                              |
| PATCH  | `/api/v1/posts/{post_id}` | Bearer token   | Update a draft or scheduled post          |
| DELETE | `/api/v1/posts/{post_id}` | Bearer token   | Delete a non-published post               |

Post creation accepts `content`, optional `scheduled_at`, optional `linkedin_account_id`, and an `ai_enhanced` flag. If `scheduled_at` is provided, the post is created as `scheduled`; otherwise it is created as `draft`.

### LinkedIn

| Method | Endpoint                                         | Authentication | Description                            |
| ------ | ------------------------------------------------ | -------------- | -------------------------------------- |
| GET    | `/api/v1/linkedin/connect`                       | Bearer token   | Return a LinkedIn authorization URL    |
| GET    | `/api/v1/linkedin/callback`                      | No             | Finish OAuth and redirect the frontend |
| GET    | `/api/v1/linkedin/accounts`                      | Bearer token   | List the user's connected accounts     |
| DELETE | `/api/v1/linkedin/accounts/{account_id}`         | Bearer token   | Disconnect an account                  |
| PATCH  | `/api/v1/linkedin/accounts/{account_id}/default` | Bearer token   | Set the default posting account        |

The callback validates the OAuth state, exchanges the authorization code for tokens, fetches the LinkedIn profile, encrypts the stored tokens, and redirects to `FRONTEND_URL` with a connection result.

### AI Content

| Method | Endpoint                | Authentication | Description                            |
| ------ | ----------------------- | -------------- | -------------------------------------- |
| POST   | `/api/v1/ai/generate`   | Bearer token   | Generate a post from a topic           |
| POST   | `/api/v1/ai/enhance`    | Bearer token   | Improve an existing draft              |
| POST   | `/api/v1/ai/regenerate` | Bearer token   | Create a variation of a previous topic |

The AI endpoints consume one AI credit per call. The current service implementation expects an OpenRouter-compatible API and returns the generated content, tone, and character count.

### Scheduler

| Method | Endpoint                             | Authentication | Description                                    |
| ------ | ------------------------------------ | -------------- | ---------------------------------------------- |
| GET    | `/api/v1/scheduler/status`           | Bearer token   | Return registered jobs and their next run time |
| POST   | `/api/v1/scheduler/trigger/{job_id}` | Bearer token   | Manually run a scheduler job immediately       |

Available job IDs are `publish_due_posts` and `refresh_expiring_tokens`.

### Analytics

| Method | Endpoint                     | Authentication | Description                                             |
| ------ | ---------------------------- | -------------- | ------------------------------------------------------- |
| GET    | `/api/v1/analytics/overview` | Bearer token   | Return post performance, growth, and AI usage summaries |
| GET    | `/api/v1/analytics/posts`    | Bearer token   | Return post performance records                         |
| GET    | `/api/v1/analytics/growth`   | Bearer token   | Return account growth snapshots                         |
| GET    | `/api/v1/analytics/ai-usage` | Bearer token   | Return AI generation statistics                         |

### Health

| Method | Endpoint  | Authentication | Description                          |
| ------ | --------- | -------------- | ------------------------------------ |
| GET    | `/health` | No             | Return the application health status |

## Background Jobs

The application starts two APScheduler jobs when `APP_ENV` is not `test`:

| Job                       | Schedule             | Behavior                                                                                                                                                                |
| ------------------------- | -------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `publish_due_posts`       | Every minute         | Finds `scheduled` posts whose `scheduled_at` has arrived, publishes them through LinkedIn, retries up to three times, and marks failed posts when retries are exhausted |
| `refresh_expiring_tokens` | Daily at 3:00 AM UTC | Refreshes LinkedIn accounts whose tokens expire within seven days                                                                                                       |

To trigger a job without waiting for its schedule:

```bash
curl -X POST http://localhost:8000/api/v1/scheduler/trigger/publish_due_posts \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

During tests, set `APP_ENV=test` to disable scheduler startup.

## Testing

Install the optional test dependencies and run the suite:

```bash
pip install -e ".[test]"
APP_ENV=test pytest tests/ -v
```

The test environment uses an in-memory SQLite database and applies the SQLAlchemy metadata before each test. The included health tests verify that the Swagger documentation is available and that unknown routes return HTTP 404.

## CI and Publishing

The GitHub Actions workflow runs on pushes and pull requests to `main` and uses Python 3.11. It:

1. Installs dependencies.
2. Starts the FastAPI application.
3. Waits for `/docs` to become available.
4. Builds and pushes Docker images to Docker Hub and GitHub Container Registry.

Required repository secrets include:

- `DATABASE_URL`
- `DEBUG`
- `JWT_SECRET_KEY`
- `JWT_ALGORITHM`
- `ACCESS_TOKEN_EXPIRE_MINUTES`
- `REFRESH_TOKEN_EXPIRE_DAYS`
- `LINKEDIN_CLIENT_ID`
- `LINKEDIN_CLIENT_SECRET`
- `LINKEDIN_REDIRECT_URI`
- `OPENROUTER_API_KEY`
- `FERNET_KEY`
- `DOCKER_USERNAME`
- `DOCKER_PASSWORD`
- `GITHUB_TOKEN`

The workflow does not require a secret named `SECRET_KEY`; configuration uses `JWT_SECRET_KEY` and the `FERNET_KEY` is supplied separately.

## Project Structure

```text
.
├── app/
│   ├── api/v1/
│   │   ├── endpoints/
│   │   │   ├── ai.py
│   │   │   ├── analytics.py
│   │   │   ├── auth.py
│   │   │   ├── linkedin.py
│   │   │   ├── posts.py
│   │   │   └── scheduler.py
│   │   └── router.py
│   ├── core/
│   │   ├── config.py
│   │   ├── deps.py
│   │   ├── scheduler.py
│   │   └── security.py
│   ├── db/session.py
│   ├── models/
│   ├── schemas/
│   └── services/
├── alembic/
├── tests/
├── .env.example
├── .dockerignore
├── .github/workflows/ci.yaml
├── alembic.ini
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
├── requirements.txt
└── README.md
```

## Notes

- The application uses `create_all()` during startup for local development convenience. For production, prefer running Alembic migrations explicitly.
- The `APP_ENV=test` setting disables scheduler startup and uses the in-memory SQLite test database.
- API documentation is enabled only when `DEBUG=true`.
- OAuth callback URLs must be registered in the LinkedIn Developer App and must match the configured `LINKEDIN_REDIRECT_URI`.
