# Docker Compose Guide

This project uses **composable Docker Compose files** to allow you to run only the services you need. This makes it easier to:
- Start with minimal services for development
- Add optional services (observability, crawling) as needed
- Reduce resource usage when not all features are needed

## File Structure

The project has multiple compose files:

1. **`docker-compose.base.yml`** - Core application services
   - `d4bl-api` - FastAPI backend
   - `d4bl-frontend` - Next.js frontend
   - `postgres` - PostgreSQL database

2. **`docker-compose.observability.yml`** - Observability and tracing
   - `langfuse-web` - Langfuse web UI
   - `langfuse-worker` - Langfuse background worker
   - `clickhouse` - ClickHouse for analytics
   - `minio` - S3-compatible storage
   - `redis` - Redis for caching/queues

3. **`docker-compose.crawl.yml`** - Crawl4AI service
   - `crawl4ai` - Self-hosted Crawl4AI service

4. **`docker-compose.firecrawl.yml`** - Firecrawl self-hosted services
   - `firecrawl-api` - Firecrawl API server
   - `firecrawl-playwright` - Playwright microservice for web scraping
   - `firecrawl-redis` - Redis instance for Firecrawl (no password)
   - `rabbitmq` - RabbitMQ message queue for Firecrawl
   - `nuq-postgres` - PostgreSQL database for Firecrawl job queue

5. **`docker-compose.yml`** - Full stack (all services merged)
   - Contains all services from base + observability + Crawl4AI
   - Note: Firecrawl services are now in a separate file

## Usage Patterns

### Pattern 1: Minimal Setup (Base Only)

Run just the core application without observability or crawling:

```bash
docker compose -f docker-compose.base.yml up --build
```

**Services started:**
- API: http://localhost:8000
- Frontend: http://localhost:3000
- Postgres: localhost:5432

**Use case:** Quick development, testing without tracing

---

### Pattern 2: Base + Observability

Add Langfuse for tracing and observability:

```bash
docker compose \
  -f docker-compose.base.yml \
  -f docker-compose.observability.yml \
  up --build
```

**Additional services:**
- Langfuse UI: http://localhost:3002
- ClickHouse: localhost:8123
- MinIO: http://localhost:9090
- Redis: localhost:6380

**Use case:** Development with tracing and evaluation capabilities

---

### Pattern 3: Base + Crawl4AI

Add Crawl4AI for web crawling:

```bash
docker compose \
  -f docker-compose.base.yml \
  -f docker-compose.crawl.yml \
  up --build
```

**Additional services:**
- Crawl4AI: http://localhost:3100

**Note:** You'll need to set `CRAWL_PROVIDER=crawl4ai` in your `.env` file.

**Use case:** Using Crawl4AI for web crawling

---

### Pattern 4: Base + Firecrawl

Add Firecrawl for web crawling and search:

```bash
docker compose \
  -f docker-compose.base.yml \
  -f docker-compose.firecrawl.yml \
  up --build
```

**Additional services:**
- Firecrawl API: http://localhost:3003
- Firecrawl Playwright: Internal service
- Firecrawl Redis: Internal service
- RabbitMQ: Internal service
- nuq-postgres: localhost:5434

**Note:** You'll need to set `CRAWL_PROVIDER=firecrawl` in your `.env` file.

**Use case:** Using Firecrawl for web crawling and search

---

### Pattern 5: Base + Observability + Crawl4AI

Full stack with Crawl4AI and observability:

```bash
docker compose \
  -f docker-compose.base.yml \
  -f docker-compose.observability.yml \
  -f docker-compose.crawl.yml \
  up --build
```

**Use case:** Complete development environment with Crawl4AI and tracing

---

### Pattern 6: Base + Observability + Firecrawl

Full stack with Firecrawl and observability:

```bash
docker compose \
  -f docker-compose.base.yml \
  -f docker-compose.observability.yml \
  -f docker-compose.firecrawl.yml \
  up --build
```

**Use case:** Complete development environment with Firecrawl and tracing

---

### Pattern 7: Full Stack (Single File)

Use the merged `docker-compose.yml` which includes base + observability + Crawl4AI:

```bash
docker compose up --build
```

**Note:** This does NOT include Firecrawl services. Add `-f docker-compose.firecrawl.yml` to include Firecrawl.

**Use case:** Quick start with most common services

---

## How Multiple Files Work

When you specify multiple `-f` flags, Docker Compose **merges** the files in order:

1. Services are merged (later files override earlier ones)
2. Networks are merged
3. Volumes are merged
4. Environment variables are merged

**Example:**
```bash
docker compose -f docker-compose.base.yml -f docker-compose.observability.yml up
```

This merges:
- All services from `base.yml`
- All services from `observability.yml`
- Networks and volumes from both files

---

## Common Commands

### Start Services
```bash
# Base only
docker compose -f docker-compose.base.yml up -d

# With observability
docker compose -f docker-compose.base.yml -f docker-compose.observability.yml up -d

# Full stack
docker compose up -d
```

### Stop Services
```bash
# Stop all services from the files you started
docker compose -f docker-compose.base.yml down

# Or if you used multiple files, use the same files to stop
docker compose -f docker-compose.base.yml -f docker-compose.observability.yml down
```

### View Logs
```bash
# All services
docker compose -f docker-compose.base.yml logs -f

# Specific service
docker compose -f docker-compose.base.yml logs -f d4bl-api
```

### Rebuild Services
```bash
docker compose -f docker-compose.base.yml build --no-cache d4bl-api
```

### Check Status
```bash
docker compose -f docker-compose.base.yml ps
```

---

## Environment Variables

Create a `.env` file in the project root to configure services:

```bash
# Ollama (required)
OLLAMA_BASE_URL=http://localhost:11434

# Crawl Provider (choose one)
CRAWL_PROVIDER=firecrawl  # or crawl4ai
FIRECRAWL_BASE_URL=http://firecrawl-api:3002
FIRECRAWL_API_KEY=  # Optional for self-hosted

# Langfuse (optional)
LANGFUSE_PUBLIC_KEY=pk-lf-dev
LANGFUSE_SECRET_KEY=sk-lf-dev

# Database (optional - defaults to Docker Postgres)
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_DB=postgres
```

---

## Service Dependencies

Services have dependencies that are automatically handled:

- **d4bl-api** depends on: `postgres`
- **d4bl-frontend** depends on: `d4bl-api`
- **langfuse-web** depends on: `postgres`, `clickhouse`, `redis`, `minio`
- **firecrawl-api** depends on: `firecrawl-redis`, `firecrawl-playwright`, `rabbitmq`, `nuq-postgres`

Docker Compose will start services in the correct order based on `depends_on` declarations.

---

## Network Isolation

All services use the `d4bl-network` bridge network (except Crawl4AI which uses `crawl4ai` network).

Services can communicate using their container names:
- `http://d4bl-api:8000` (from within Docker)
- `http://langfuse-web:3000` (from within Docker)
- `http://firecrawl-api:3002` (from within Docker)

---

## Port Mappings

| Service | Internal Port | External Port | URL |
|---------|--------------|---------------|-----|
| d4bl-api | 8000 | 8000 | http://localhost:8000 |
| d4bl-frontend | 3000 | 3000 | http://localhost:3000 |
| langfuse-web | 3000 | 3002 | http://localhost:3002 |
| crawl4ai | 11235 | 3100 | http://localhost:3100 |
| firecrawl-api | 3002 | 3003 | http://localhost:3003 |
| nuq-postgres | 5432 | 5434 | localhost:5434 |
| postgres | 5432 | 5432 | localhost:5432 |
| clickhouse | 8123 | 8123 | localhost:8123 |
| redis | 6379 | 6380 | localhost:6380 |
| minio | 9000 | 9090 | http://localhost:9090 |

---

## Troubleshooting

### Port Conflicts

If you get "port already allocated" errors:

1. Check what's using the port:
   ```bash
   lsof -i :8000  # Replace with your port
   ```

2. Stop conflicting services or change ports in compose files

### Service Won't Start

1. Check logs:
   ```bash
   docker compose -f docker-compose.base.yml logs d4bl-api
   ```

2. Verify dependencies are running:
   ```bash
   docker compose -f docker-compose.base.yml ps
   ```

3. Check health status:
   ```bash
   docker compose -f docker-compose.base.yml ps --format json | jq '.[] | {name: .Name, health: .Health}'
   ```

### Network Issues

If services can't communicate:

1. Verify they're on the same network:
   ```bash
   docker network inspect d4bl-network
   ```

2. Check service names match exactly (case-sensitive)

---

## Best Practices

1. **Start minimal for development**: Use `docker-compose.base.yml` for quick iteration
2. **Add services incrementally**: Add observability or crawling only when needed
3. **Use `.env` file**: Keep sensitive config out of compose files
4. **Use `-d` flag**: Run in detached mode for long-running services
5. **Clean up volumes**: Use `docker compose down -v` to remove volumes when resetting

---

## Quick Reference

```bash
# Minimal setup
docker compose -f docker-compose.base.yml up -d

# With observability
docker compose -f docker-compose.base.yml -f docker-compose.observability.yml up -d

# With Firecrawl
docker compose -f docker-compose.base.yml -f docker-compose.firecrawl.yml up -d

# Full stack (base + observability + Crawl4AI)
docker compose up -d

# Full stack with Firecrawl
docker compose -f docker-compose.base.yml -f docker-compose.observability.yml -f docker-compose.firecrawl.yml up -d

# Stop
docker compose down

# View logs
docker compose logs -f

# Rebuild
docker compose build --no-cache
```

