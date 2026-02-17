# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

D4BL Research and Analysis Tool - A multi-agent AI system for web research, data analysis, and report generation focused on data justice and racial equity issues. Built with CrewAI, FastAPI, Next.js, and local Ollama LLM.

## Commands

### Running the Application

```bash
# Backend (FastAPI on port 8000)
source .venv/bin/activate
python -m uvicorn d4bl.app.api:app --host 0.0.0.0 --port 8000
# Or: python run_ui.py

# Frontend (Next.js on port 3000)
cd ui-nextjs && npm run dev

# CLI mode
python src/d4bl/main.py "your research question" --summary detailed
python src/d4bl/main.py "query" --agents researcher writer  # Select specific agents
```

### Docker

```bash
# Core stack (API + frontend + Postgres)
docker compose -f docker-compose.base.yml up --build

# Add Langfuse observability
docker compose -f docker-compose.base.yml -f docker-compose.observability.yml up --build

# Add Crawl4AI or Firecrawl
docker compose -f docker-compose.base.yml -f docker-compose.crawl.yml up --build
docker compose -f docker-compose.base.yml -f docker-compose.firecrawl.yml up --build

# Full stack
docker compose up --build
```

### Frontend

```bash
cd ui-nextjs
npm run dev      # Development
npm run build    # Production build
npm run lint     # ESLint
```

### Database Scripts

```bash
python scripts/init_db.py                    # Initialize database
python scripts/test_db_connection.py         # Test DB connection
python scripts/test_supabase_connection.py   # Test vector store
python scripts/run_vector_migration.py       # Run migrations
```

## Architecture

```
User Browser → Next.js Frontend (3000)
              ↓
         FastAPI Backend (8000)
              ↓
         CrewAI Framework
              ↓
    AI Agents (Researcher, Analyst, Writer, Fact Checker, Editor, etc.)
              ↓
    External Services:
    - Ollama LLM (localhost:11434)
    - Firecrawl/Crawl4AI (web crawling)
    - PostgreSQL (job storage)
    - Supabase (vector storage)
    - Langfuse (observability)
```

### Key Modules

- **`src/d4bl/app/`** - FastAPI application: `api.py` (REST/WebSocket endpoints), `schemas.py` (Pydantic models), `websocket_manager.py` (connection state)
- **`src/d4bl/agents/`** - CrewAI agents: `crew.py` (8 agent definitions), `tools/crawl_tools/` (modular crawl providers)
- **`src/d4bl/infra/`** - Database layer: `database.py` (SQLAlchemy models), `vector_store.py` (Supabase)
- **`src/d4bl/services/`** - Business logic: `research_runner.py` (job execution), `error_handling.py` (retry logic), `langfuse/` (evaluations)
- **`src/d4bl/llm/`** - LLM config: `ollama.py` (lazy-loaded singleton via LiteLLM)
- **`src/d4bl/observability/`** - Tracing: `langfuse.py` (CrewAI instrumentation, OpenTelemetry)
- **`src/d4bl/settings.py`** - Centralized environment configuration via `@dataclass(frozen=True)`

### Frontend (`ui-nextjs/`)

- Next.js App Router with React 19
- Components: `ResearchForm`, `ProgressCard`, `ResultsCard`, `ErrorCard`, `LiveLogs`, `JobHistory`
- Custom hooks: `useWebSocket` for real-time updates
- Tailwind CSS 4 for styling

## Configuration

All configuration via environment variables. Key settings in `src/d4bl/settings.py`:

```
OLLAMA_BASE_URL=http://localhost:11434
CRAWL_PROVIDER=firecrawl|crawl4ai
FIRECRAWL_API_KEY=...
FIRECRAWL_BASE_URL=http://firecrawl-api:3002
CRAWL4AI_BASE_URL=http://crawl4ai:11235
LANGFUSE_HOST=http://localhost:3002
POSTGRES_HOST=localhost|postgres
```

## Code Style

- **Python**: PEP 8, type hints, 100 char max line length, docstrings for public APIs
- **TypeScript**: Strict mode, functional components with hooks, Tailwind CSS
- **Commits**: Conventional Commits (`feat:`, `fix:`, `docs:`, `refactor:`, `chore:`)
- **No AI attribution**: Never include "Co-Authored-By" lines in commits or "Generated with Claude Code" in PRs

## Service Ports

| Service | Port |
|---------|------|
| Frontend | 3000 |
| Backend API | 8000 |
| Ollama | 11434 |
| PostgreSQL | 5432 |
| Langfuse Web | 3001 |
| ClickHouse | 8123 |
