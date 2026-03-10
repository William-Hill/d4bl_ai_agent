# Data Ingestion Sprint 4: Deployment & Integration — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Deploy Dagster to Fly.io, extend CI/CD, connect lineage to the research pipeline, and add the remaining API endpoints (lineage queries, test connection).

**Architecture:** Two new Fly.io apps (dagster-web, dagster-daemon) on the private network. CI/CD extended with deploy steps. Research pipeline enhanced to surface data lineage in outputs.

**Tech Stack:** Fly.io, GitHub Actions, Dagster, FastAPI

**Prerequisite:** Sprint 3 complete

**Design doc:** `docs/plans/2026-03-08-data-ingestion-epic-design.md` (Infrastructure section)

---

## Sprint Overview

| Task | Description | Depends On |
|------|-------------|------------|
| 1 | Fly.io config for Dagster webserver | — |
| 2 | Fly.io config for Dagster daemon | Task 1 |
| 3 | CI/CD extension — deploy-staging.yml | Tasks 1-2 |
| 4 | Lineage API endpoints | — |
| 5 | Test connection endpoint | — |
| 6 | Research pipeline lineage integration | Task 4 |
| 7 | Bias Detection agent — data lineage awareness | Task 6 |
| 8 | Query engine — provenance in search results | Task 4 |
| 9 | Langfuse tracing for ingestion runs | — |
| 10 | CLAUDE.md and docs updates | All |
| 11 | End-to-end smoke test (full pipeline) | All |

---

### Task 1: Fly.io Config — Dagster Webserver

**Files:**
- Create: `fly.dagster-web.toml`

```toml
app = "d4bl-dagster-web"
primary_region = "iad"

[build]
  dockerfile = "dagster/Dockerfile"

[http_service]
  internal_port = 3003
  force_https = true
  auto_stop_machines = "stop"
  auto_start_machines = true
  min_machines_running = 0

[[vm]]
  size = "shared-cpu-1x"
  memory = "1gb"
```

Not publicly exposed — only accessible via Fly private network (`d4bl-dagster-web.internal:3003`).

---

### Task 2: Fly.io Config — Dagster Daemon

**Files:**
- Create: `fly.dagster-daemon.toml`

```toml
app = "d4bl-dagster-daemon"
primary_region = "iad"

[build]
  dockerfile = "dagster/Dockerfile"
  [build.args]
    CMD = "dagster-daemon run"

[[vm]]
  size = "shared-cpu-1x"
  memory = "512mb"
```

No HTTP service — background process only. Needs to stay running for schedule/sensor execution.

---

### Task 3: CI/CD Extension

**Files:**
- Modify: `.github/workflows/deploy-staging.yml`

Add two new deploy steps after `deploy-crawl4ai`:

```yaml
  - name: Deploy Dagster Webserver
    run: flyctl deploy --config fly.dagster-web.toml --remote-only

  - name: Deploy Dagster Daemon
    run: flyctl deploy --config fly.dagster-daemon.toml --remote-only
```

Update health check to verify Dagster webserver is accessible from API service.

---

### Task 4: Lineage API Endpoints

**Files:**
- Modify: `src/d4bl/app/data_routes.py`
- Modify: `src/d4bl/app/schemas.py`
- Test: `tests/test_lineage_api.py`

Add endpoints:
- `GET /api/data/lineage/{table}/{record_id}` — full provenance for a record
- `GET /api/data/lineage/graph` — asset dependency graph (proxied from Dagster GraphQL)

---

### Task 5: Test Connection Endpoint

**Files:**
- Modify: `src/d4bl/app/data_routes.py`
- Modify: `src/d4bl/services/dagster_client.py`
- Test: `tests/test_connection_test.py`

`POST /api/data/sources/{id}/test` — validates source config without ingesting:
- API: makes a HEAD/GET request to configured URL
- Database: tests connection string
- MCP: pings MCP server
- Web scrape: validates URL is reachable
- RSS: fetches feed and validates XML
- File upload: validates file exists

---

### Task 6: Research Pipeline Lineage Integration

**Files:**
- Modify: `src/d4bl/services/research_runner.py`
- Modify: `src/d4bl/query/structured.py`

When the query engine searches ingested data, attach lineage metadata to results:
- Source provenance (where did this data come from)
- Quality score (how reliable is this data)
- Coverage gaps (what's missing from this dataset)

---

### Task 7: Bias Detection Agent — Data Lineage Awareness

**Files:**
- Modify: `src/d4bl/agents/config/tasks.yaml` (bias_detection_task context)

Enhance the Bias Detection agent's task description to include data lineage context. When research draws on ingested data, the agent can flag:
- Conclusions based on low-quality-score data
- Geographic/demographic gaps in underlying datasets
- Single-source concentration risks

---

### Task 8: Query Engine — Provenance in Search Results

**Files:**
- Modify: `src/d4bl/query/fusion.py`
- Modify: `src/d4bl/app/schemas.py` (add provenance to QuerySourceItem)

When the NL query engine returns results from ingested data, include:
- `data_source_name` — which source produced this data
- `quality_score` — reliability indicator
- `last_updated` — freshness of the data
- `coverage_notes` — any known gaps

---

### Task 9: Langfuse Tracing for Ingestion Runs

**Files:**
- Modify: `dagster/d4bl_pipelines/resources/__init__.py` (add Langfuse resource)
- Modify: `dagster/d4bl_pipelines/assets/apis/census_acs.py` (add tracing)

Each Dagster asset run creates a Langfuse trace with:
- Span per lifecycle step (fetch, validate, score, transform, store)
- Token usage if LLM is involved (quality scoring)
- Metadata: records count, quality score, duration

---

### Task 10: Documentation Updates

**Files:**
- Modify: `CLAUDE.md` (add Dagster commands, ports, architecture)
- Modify: `docs/STAGING_SETUP.md` (add Dagster Fly.io setup)

Update:
- Architecture diagram to include Dagster
- Commands section with Dagster dev/deploy commands
- Service ports table (add 3003)
- Docker compose usage with dagster overlay
- Environment variables for Dagster

---

### Task 11: End-to-End Smoke Test

**Files:**
- Create: `tests/test_e2e_ingestion.py`

Full pipeline test:
1. Create a data source via API
2. Trigger ingestion via API
3. Verify Dagster run completes
4. Verify data appears in target table
5. Verify lineage record exists
6. Verify quality score and bias flags populated
7. Query the ingested data via NL query engine
8. Verify provenance metadata in query results

---

## Sprint 4 Completion Checklist

- [ ] Dagster webserver deployed to Fly.io (private network)
- [ ] Dagster daemon deployed to Fly.io
- [ ] CI/CD deploys all 5 services
- [ ] Lineage queryable via API
- [ ] Test connection validates source configs
- [ ] Research pipeline surfaces data provenance
- [ ] Bias Detection agent aware of data quality
- [ ] Query results include source lineage
- [ ] Ingestion runs traced in Langfuse
- [ ] CLAUDE.md and docs updated
- [ ] Full E2E test passing

---

## Epic Complete

After Sprint 4, the data ingestion epic delivers:
- 6 configurable source types (API, file, web scrape, RSS, database, MCP)
- Full DAG orchestration with cron scheduling via Dagster
- D4BL methodology-aligned data lineage with quality scoring and bias detection
- Admin UI at `/data` for source management, monitoring, and lineage exploration
- Deployed to Fly.io at ~$13/mo additional cost
- Integrated with research pipeline, evaluation framework, and observability
