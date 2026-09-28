# Offline-First Data Synchronization System

Full-stack offline-first sample using FastAPI, SQLAlchemy, Alembic, JWT auth, Redis, React, Vite, TypeScript, Material UI, Axios, React Router, IndexedDB, MySQL 8, and Docker Compose.

## Features

- User registration, login, JWT authentication, profile update, and admin-only user listing.
- Records can be created and deleted while offline in the browser.
- IndexedDB stores records, conflicts, local sync history, and a durable change queue.
- Automatic sync starts when the browser comes back online.
- Backend sync is idempotent by `operation_id` to prevent duplicate synchronization.
- Optimistic concurrency uses record `version`.
- Conflict strategies: `manual`, `server_wins`, `client_wins`, and `last_write_wins`.
- Sync history captures sync id, record/client id, operation, status, timestamp, errors, and conflict status.
- Dashboard metrics show pending changes, synced records, failed syncs, conflicts, and record counts.
- Search, status filtering, pagination-ready backend endpoints, sorting, and date filtering.
- Redis is used for per-user sync locking when configured.

## Run With Docker

```bash
cp .env.example .env
docker compose up --build
```

- Frontend: http://localhost:5173
- Backend API: http://localhost:8000
- Swagger/OpenAPI: http://localhost:8000/docs
- MySQL: localhost:3306
- Redis: localhost:6379

## Run Locally

Backend:

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
pip install -r requirements-dev.txt
uvicorn app.main:app --reload
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

## Database

Apply migrations:

```bash
alembic upgrade head
```

The backend also calls `Base.metadata.create_all` for local development convenience.

## Tests

```bash
cd backend
pip install -r requirements-dev.txt
pytest
```

## Important API Endpoints

- `POST /auth/register`
- `POST /auth/login`
- `GET /auth/me`
- `PATCH /auth/me`
- `GET /records`
- `POST /records`
- `PUT /records/{client_id}`
- `DELETE /records/{client_id}?version=1`
- `POST /sync`
- `GET /sync/history`
- `GET /conflicts`
- `POST /conflicts/{conflict_id}/resolve`
- `GET /dashboard`

## Sync Request Example

```json
{
  "strategy": "manual",
  "changes": [
    {
      "operation_id": "op-123",
      "client_id": "record-123",
      "operation": "create",
      "title": "Offline note",
      "content": "Created while offline",
      "version": 0,
      "updated_at": "2026-09-25T10:00:00Z"
    }
  ]
}
```
