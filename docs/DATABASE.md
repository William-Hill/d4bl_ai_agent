# Database Persistence

This document describes the Postgres database integration for storing research queries and results.

## Overview

All research queries and results are now persisted in a PostgreSQL database, allowing you to:
- **Retrieve past queries and results** even after server restarts
- **View query history** with pagination and filtering
- **Track job status** across sessions
- **Store logs** for debugging and auditing

## Database Schema

### `research_jobs` Table

| Column | Type | Description |
|--------|------|-------------|
| `job_id` | UUID | Primary key, unique job identifier |
| `query` | TEXT | The research query text |
| `summary_format` | VARCHAR(20) | Format: brief, detailed, or comprehensive |
| `status` | VARCHAR(20) | Job status: pending, running, completed, error |
| `progress` | TEXT | Current progress message |
| `result` | JSON | Full result dictionary (tasks_output, report, etc.) |
| `error` | TEXT | Error message if job failed |
| `logs` | JSON | Array of log messages |
| `created_at` | TIMESTAMP | When the job was created |
| `updated_at` | TIMESTAMP | Last update time |
| `completed_at` | TIMESTAMP | When the job completed (null if not completed) |

## Configuration

### Environment Variables

Set these in your `.env` file or docker-compose environment:

```bash
POSTGRES_HOST=localhost          # or 'postgres' in Docker
POSTGRES_PORT=5432
POSTGRES_USER=d4bl_user
POSTGRES_PASSWORD=d4bl_password
POSTGRES_DB=d4bl_db
```

### Docker Compose

The `docker-compose.yml` includes a Postgres service that:
- Automatically creates the database on first run
- Persists data in a Docker volume (`postgres_data`)
- Health checks ensure the database is ready before the API starts

## API Endpoints

### Get Job Status
```
GET /api/jobs/{job_id}
```
Returns the status and results for a specific job.

### Get Job History
```
GET /api/jobs?page=1&page_size=20&status=completed
```
Returns paginated job history with optional status filtering.

**Query Parameters:**
- `page` (int, default: 1): Page number
- `page_size` (int, default: 20): Number of results per page
- `status` (string, optional): Filter by status (pending, running, completed, error)

**Response:**
```json
{
  "jobs": [
    {
      "job_id": "uuid",
      "query": "Research question...",
      "status": "completed",
      "result": {...},
      "created_at": "2025-01-01T00:00:00",
      ...
    }
  ],
  "total": 100,
  "page": 1,
  "page_size": 20
}
```

## Initialization

### Automatic Initialization

The database tables are automatically created when the API starts (via the `startup` event).

### Manual Initialization

You can also initialize the database manually:

```bash
python scripts/init_db.py
```

Or in Docker:
```bash
docker-compose exec d4bl-api python scripts/init_db.py
```

## Data Persistence

### Docker Volume

Data is stored in a Docker volume named `postgres_data`. To backup:

```bash
docker-compose exec postgres pg_dump -U d4bl_user d4bl_db > backup.sql
```

To restore:
```bash
docker-compose exec -T postgres psql -U d4bl_user d4bl_db < backup.sql
```

### Local Development

If running locally (not in Docker), ensure Postgres is running and accessible at the configured host/port.

## Migration from In-Memory Storage

The previous in-memory storage (`jobs: dict[str, JobStatus] = {}`) has been replaced with database persistence. All existing functionality remains the same, but now:

- Jobs persist across server restarts
- You can query job history
- Data is stored in a production-ready database

## Troubleshooting

### Database Connection Errors

If you see connection errors:
1. Ensure Postgres is running: `docker-compose ps`
2. Check environment variables are set correctly
3. Verify network connectivity (in Docker, use service name `postgres`)

### Table Creation Errors

If tables don't exist:
1. Run the initialization script: `python scripts/init_db.py`
2. Check database logs: `docker-compose logs postgres`

### Performance

For large datasets:
- Add indexes on frequently queried columns (already indexed: `job_id`, `status`, `created_at`, `query`)
- Consider archiving old jobs periodically
- Use pagination when querying job history

