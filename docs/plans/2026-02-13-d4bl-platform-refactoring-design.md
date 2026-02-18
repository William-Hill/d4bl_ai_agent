# D4BL Platform Refactoring Design

## Context

The D4BL Research and Analysis Tool is a multi-agent AI system for web research, data analysis, and report generation focused on data justice and racial equity. This refactoring aligns the platform with the D4BL methodology cycle and adds capabilities for natural language querying, public data integration, and human-in-the-loop decision making.

### D4BL Methodology Cycle

The platform's user experience follows the D4BL methodology, a circular workflow:

**Community Engagement → Problem Identification → Data Collection + Analysis → Policy Innovation → Power Building → (repeat)**

Core principles: "Data as Protest", "Data as Accountability", "Data as Collective Action".

### Driving Test Case

**Mississippi NIL Policy**: Apply the D4BL methodology to analyze how Name, Image, and Likeness (NIL) policies affect Black athletes in Mississippi. This concrete scenario drives feature prioritization and validates each iteration.

## Approach: Test-Case-Driven Vertical Slices

Each iteration delivers a working end-to-end feature validated against the Mississippi NIL case. This ensures concrete, testable progress while building incrementally on existing working code.

## Architecture

```
                    ┌─────────────────────────────┐
                    │     Frontend (Next.js)       │
                    │  Quick Research │ Methodology │
                    │     Mode       │    Mode     │
                    └────────┬───────┴──────┬──────┘
                             │              │
                    ┌────────▼──────────────▼──────┐
                    │      FastAPI Backend          │
                    │  ┌──────────────────────────┐ │
                    │  │   NL Query Engine API     │ │
                    │  ├──────────────────────────┤ │
                    │  │   Methodology Controller  │ │
                    │  │   (stage transitions,     │ │
                    │  │    HITL checkpoints)      │ │
                    │  ├──────────────────────────┤ │
                    │  │   Research Runner          │ │
                    │  │   (existing, enhanced)     │ │
                    │  └──────────────────────────┘ │
                    └────────┬──────────────────────┘
                             │
        ┌────────────────────┼────────────────────┐
        │                    │                    │
  ┌─────▼──────┐   ┌────────▼────────┐   ┌──────▼───────┐
  │ Dagster     │   │ CrewAI Agents   │   │ HITL         │
  │ Orchestrator│   │ (realigned to   │   │ Framework    │
  │ (pipelines, │   │  D4BL stages)   │   │ (approvals,  │
  │  scheduling)│   └─────────────────┘   │  reviews)    │
  └─────┬───────┘                         └──────────────┘
        │
  ┌─────▼───────────────────────────────────────────────────┐
  │                   Unified Data Layer                     │
  │                                                         │
  │  Supabase (PostgreSQL + pgvector)    Snowflake (DW)     │
  │  ┌─────────────────────────────┐  ┌─────────────────┐  │
  │  │ Vector Store (pgvector)     │  │ D4BL_RAW        │  │
  │  │  - scraped_content_vectors  │  │  - research_jobs │  │
  │  │  - semantic similarity      │  │  - scraped_cont. │  │
  │  ├─────────────────────────────┤  │  - census_demo.  │  │
  │  │ Operational DB              │  │  - bls_employ.   │  │
  │  │  - research_jobs (state)    │  │  - state_legis.  │  │
  │  │  - evaluation_results       │  ├─────────────────┤  │
  │  │  - hitl_checkpoints         │  │ D4BL_ANALYTICS  │  │
  │  └─────────────────────────────┘  │  (dbt marts)    │  │
  │                                   └─────────────────┘  │
  │         Dagster syncs completed                        │
  │         jobs + content ──────────►                     │
  └────────────────────────────────────────────────────────┘
```

### Supabase vs Snowflake: Role Separation

The platform uses two database systems, each optimized for different workloads:

**Supabase (PostgreSQL + pgvector) — Operational & Vector Store:**
- **Vector search** — pgvector cosine similarity over scraped content embeddings (1024-dim, `mxbai-embed-large`). Snowflake has no native vector similarity search, so Supabase owns all semantic search.
- **Operational state** — real-time job status, progress, logs, WebSocket coordination. Requires low-latency transactional reads/writes that Snowflake isn't designed for.
- **HITL checkpoints** — checkpoint persistence for approval workflows (must survive browser refresh, needs fast writes).
- **Evaluation results** — Langfuse evaluation scores stored alongside job data.

**Snowflake — Analytics Data Warehouse:**
- **Public datasets** — Census demographics, BLS employment, state legislature data. Bulk-loaded and transformed via dbt.
- **Research analytics** — completed research job results and scraped content (text + metadata, not embeddings) synced from Supabase for analytical joins.
- **dbt marts** — pre-computed analytical models (e.g., NIL policy analysis joined with demographics, research effectiveness metrics, geographic equity indicators).
- **Complex analytical queries** — aggregations, joins across data sources, time series, KPI computation. Queries the NL query engine can't efficiently run against PostgreSQL.

**Data flow between them:**
- **Supabase → Snowflake:** Dagster sensor detects completed research jobs in Supabase, then a Dagster asset copies job results and scraped content (text + metadata, not embeddings) into Snowflake's `D4BL_RAW` layer. dbt transforms from there.
- **Snowflake is never written to by the app directly** — only Dagster pipelines land data there.
- **Supabase is the system of record** for operational data. Snowflake is a derived analytical copy.

**NL query engine queries both:**
- Semantic similarity → Supabase/pgvector
- Analytical/structured queries → Snowflake dbt marts
- Operational lookups (job status, logs) → Supabase/PostgreSQL

### New Modules

- **`src/d4bl/query/`** — NL query engine (vector search + Snowflake SQL + result fusion)
- **`src/d4bl/methodology/`** — D4BL cycle state machine and stage management
- **`src/d4bl/hitl/`** — Human-in-the-loop checkpoint system
- **`src/d4bl/data/`** — Public dataset connectors and importers
- **`src/d4bl/orchestration/`** — Dagster asset definitions, jobs, and schedules
- **`dbt_project/`** — dbt project root (models, sources, tests, macros)

### Enhanced Existing Modules

- **`src/d4bl/infra/vector_store.py`** — Fully integrated into the research pipeline
- **`src/d4bl/services/research_runner.py`** — Dagster-aware, HITL hooks, methodology stage awareness
- **`src/d4bl/agents/`** — Agents mapped to methodology stages
- **`src/d4bl/app/api.py`** — New endpoints for query, methodology, HITL
- **`src/d4bl/settings.py`** — Snowflake credentials, Dagster config

## Iteration Plan

### Iteration 1: Vector Store Integration + NL Query Engine

**Goal:** Make previously collected research queryable via natural language, and ensure new research is automatically stored for future queries.

**Scope:**
- Wire up existing `vector_store.py` into the research pipeline (auto-store crawled content)
- Create `src/d4bl/query/` module:
  - Query parser: extract intent and entities using Ollama/Mistral
  - Vector similarity search over scraped content (Supabase/pgvector)
  - SQL query generation for structured data (research jobs, results)
  - Result fusion: combine vector and structured results with relevance ranking
- New API endpoint: `POST /api/query` accepting natural language questions
- Basic query UI component in the frontend

**Validation:** Run a Mississippi NIL research job, then query "What are the NIL policies affecting Black athletes in Mississippi?" and get a synthesized answer with source citations.

### Iteration 2: Dagster Orchestration + Snowflake Data Warehouse

**Goal:** Replace ad-hoc job execution with Dagster-orchestrated pipelines and land public + research data into Snowflake for analytics-ready querying via dbt.

**Scope:**

**Dagster orchestration (`src/d4bl/orchestration/`):**
- Define Dagster assets for: research job execution, crawl result storage, vector embedding generation
- Define Dagster jobs wrapping the existing `run_research_job()` flow
- Add Dagster schedules for recurring data ingestion (Census, BLS)
- Dagster sensors to trigger downstream assets when new research completes
- Dagster UI (dagit) running alongside the existing FastAPI app for pipeline observability

**Snowflake data warehouse:**
- Provision Snowflake account with `D4BL_RAW`, `D4BL_STAGING`, `D4BL_ANALYTICS` databases
- Dagster assets to ingest into Snowflake raw layer:
  - Research job results → `D4BL_RAW.research_jobs`
  - Scraped content (text, metadata) → `D4BL_RAW.scraped_content`
  - Census API demographics → `D4BL_RAW.census_demographics`
  - BLS employment data → `D4BL_RAW.bls_employment`
  - State legislature data → `D4BL_RAW.state_legislation`

**dbt transformation (`dbt_project/`):**
- **Staging models** (`models/staging/`):
  - `stg_research_jobs` — cleaned research jobs with parsed metadata
  - `stg_scraped_content` — normalized scraped content with source tracking
  - `stg_census_demographics` — demographics by geography (state, county, MSA)
  - `stg_bls_employment` — employment statistics by industry and demographics
  - `stg_state_legislation` — bill status, sponsors, topics
- **Intermediate models** (`models/intermediate/`):
  - `int_research_with_sources` — research jobs joined with their scraped sources
  - `int_demographic_profiles` — combined Census + BLS demographic profiles by geography
- **Mart models** (`models/marts/`):
  - `mart_nil_policy_analysis` — NIL policies joined with demographic and employment data
  - `mart_research_effectiveness` — metrics on research quality (source count, diversity, evaluation scores)
  - `mart_geographic_equity_indicators` — equity indicators by geography combining all data sources
- **dbt tests** for data quality: uniqueness, not-null, accepted values, relationships
- **dbt metrics** definitions for KPIs: research_success_rate, source_diversity_score, geographic_coverage

**NL query engine extension:**
- Extend `src/d4bl/query/` to query Snowflake analytics marts alongside vector store
- Add Snowflake connector using `snowflake-connector-python`
- LLM-generated SQL queries against dbt mart schemas

**Validation:**
- Dagster pipeline ingests Census demographic data for Mississippi into Snowflake
- dbt builds `mart_nil_policy_analysis` combining NIL research with MS demographics
- Query "What is the racial demographic breakdown of NCAA athletes in Mississippi?" returns results from Snowflake mart + vector store

### Iteration 3: Human-in-the-Loop Checkpoints

**Goal:** Allow human review and approval at methodology stage transitions and between agent tasks.

**Scope:**
- Create `src/d4bl/hitl/` module:
  - Checkpoint type definitions (methodology-stage and agent-task levels)
  - WebSocket-based approval flow: pause → notify → wait for response
  - Checkpoint state persistence in Supabase/PostgreSQL (survives browser refresh, low-latency writes)
  - Configurable checkpoint placement
- Integrate into Dagster jobs as Dagster hooks/sensors for pipeline-level HITL
- Integrate into `research_runner.py` with hooks at configurable points
- Frontend: Approval UI component showing context, agent output, and approve/reject/edit options

**Checkpoint Flow:**
1. Execution reaches checkpoint → pauses (Dagster run pauses or agent task pauses)
2. WebSocket sends checkpoint event with: stage, agent output, context
3. User reviews and chooses: Approve / Reject with feedback / Edit output
4. Approve → continue; Reject → re-run with user feedback injected
5. State persisted to DB for recovery

**Validation:** Run Mississippi NIL research with HITL enabled, approve problem identification, reject and refine data collection parameters, then approve the rest.

### Iteration 4: Methodology-Aligned Agent Refactoring

**Goal:** Reorganize agent execution to follow the D4BL methodology cycle instead of a flat sequential pipeline.

**Scope:**
- Create `src/d4bl/methodology/` module:
  - Stage enum: `COMMUNITY_ENGAGEMENT`, `PROBLEM_IDENTIFICATION`, `DATA_COLLECTION_ANALYSIS`, `POLICY_INNOVATION`, `POWER_BUILDING`
  - State machine managing transitions with persistence
  - Stage-specific agent configurations and task templates
- Map existing agents to methodology stages:
  - Community Engagement: survey/input collection agents
  - Problem Identification: researcher, bias detection
  - Data Collection + Analysis: researcher, data analyst, fact checker, citation
  - Policy Innovation: writer, editor
  - Power Building: data visualization, communication agents
- Model methodology stages as Dagster asset groups with cross-stage lineage
- New endpoints: `POST /api/methodology/start`, `POST /api/methodology/{id}/advance`, `GET /api/methodology/{id}/status`

**Validation:** Run the full Mississippi NIL case through all 5 methodology stages with stage-appropriate agents executing at each step.

### Iteration 5: Frontend Hybrid Mode

**Goal:** Add a "Methodology Mode" alongside the existing quick research form.

**Scope:**
- Keep "Quick Research" mode (current form) as-is
- Add "Methodology Mode" view:
  - Circular D4BL methodology diagram as primary navigation
  - Stage detail panels showing progress, agent outputs, HITL checkpoints
  - NL query bar integrated into each stage for contextual questions
  - Progress visualization across the full cycle
  - Data lineage view powered by Dagster asset graph
- Design inspired by blackwealthdata.org patterns

**Validation:** Complete the Mississippi NIL case entirely through the Methodology Mode UI, from community engagement input through power building outputs.

### Iteration 6: Communication + Distribution

**Goal:** Generate stakeholder-specific outputs and support multiple distribution formats.

**Scope:**
- Output templating system for different audiences:
  - Policy brief (for legislators)
  - Community report (for affected communities)
  - Academic summary (for researchers)
  - Data dashboard (for analysts) — powered by Snowflake mart queries
- Export formats: PDF, presentation slides, structured data
- Communication channel suggestions based on audience analysis
- dbt exposure definitions linking mart models to their downstream dashboard/report consumers

**Validation:** Generate a policy brief about Mississippi NIL for state legislators AND a community summary for affected athletes from the same research run.

## NL Query Engine Data Flow

```
User: "What NIL policies affect Black athletes in Mississippi?"
                    │
                    ▼
         ┌─────────────────┐
         │  Query Parser    │ ← Ollama/Mistral
         │  (intent +       │
         │   entities)      │
         └────────┬────────┘
                  │
         ┌────────▼────────┐
         │  Query Router    │
         │  (decides which  │
         │   data sources)  │
         └──┬────┬────┬──┬─┘
            │    │    │  │
   ┌────────▼┐ ┌─▼──┐ ┌▼────────┐ ┌▼──────────┐
   │Vector   │ │SQL │ │Snowflake│ │Public API  │
   │Search   │ │(PG)│ │(dbt     │ │Connector   │
   │(Supabase│ │    │ │ marts)  │ │(Census etc)│
   └────┬────┘ └─┬──┘ └───┬────┘ └─────┬─────┘
        │        │        │            │
        └────────┴────────┴────────────┘
                  │
         ┌────────▼────────┐
         │  Result Fusion   │
         │  (rank, dedupe,  │
         │   synthesize)    │
         └────────┬────────┘
                  │
                  ▼
         Synthesized Answer + Sources
```

## Dagster Pipeline Architecture

```
                    ┌──────────────────────────┐
                    │     Dagster Orchestrator   │
                    │     (dagit on :3100)       │
                    └────────────┬──────────────┘
                                 │
         ┌───────────────────────┼───────────────────────┐
         │                       │                       │
   ┌─────▼──────┐        ┌──────▼──────┐        ┌──────▼──────┐
   │ Research    │        │ Data        │        │ dbt         │
   │ Pipeline    │        │ Ingestion   │        │ Transform   │
   │ ┌────────┐  │        │ ┌────────┐  │        │ ┌────────┐  │
   │ │Run crew│  │        │ │Census  │  │        │ │staging │  │
   │ │agents  │  │        │ │API     │  │        │ │models  │  │
   │ ├────────┤  │        │ ├────────┤  │        │ ├────────┤  │
   │ │Store   │  │        │ │BLS API │  │        │ │intermed│  │
   │ │vectors │  │        │ ├────────┤  │        │ │models  │  │
   │ ├────────┤  │        │ │State   │  │        │ ├────────┤  │
   │ │Land in │  │        │ │legis.  │  │        │ │mart    │  │
   │ │Snowflake│ │        │ └───┬────┘  │        │ │models  │  │
   │ └────────┘  │        │     │       │        │ ├────────┤  │
   └─────────────┘        │  Snowflake  │        │ │metrics │  │
                          │  Raw Layer  │        │ │& tests │  │
                          └─────────────┘        │ └────────┘  │
                                                 └─────────────┘
                          Sensor: on new raw data → trigger dbt run
```

## HITL Checkpoint Model

### Methodology-Stage Checkpoints

Between the 5 D4BL methodology stages:
- After Community Engagement → before Problem Identification
- After Problem Identification → before Data Collection + Analysis
- After Data Collection + Analysis → before Policy Innovation
- After Policy Innovation → before Power Building

### Agent-Task Checkpoints (Optional, Configurable)

Within a methodology stage, between individual agent executions:
- After researcher → before analyst
- After analyst → before writer
- After writer → before editor

### Pipeline Checkpoints (Dagster-Level)

- After data ingestion completes → before dbt transformation
- After dbt model builds → before exposing to NL query engine
- Implemented as Dagster run status sensors with WebSocket notification

### User Actions at Checkpoints

- **Approve** — continue execution
- **Reject with feedback** — re-run the preceding stage/task with feedback injected into the prompt
- **Edit output** — modify the agent's output directly, then continue

## dbt Project Structure

```
dbt_project/
├── dbt_project.yml
├── profiles.yml           (Snowflake connection)
├── models/
│   ├── staging/
│   │   ├── stg_research_jobs.sql
│   │   ├── stg_scraped_content.sql
│   │   ├── stg_census_demographics.sql
│   │   ├── stg_bls_employment.sql
│   │   └── stg_state_legislation.sql
│   ├── intermediate/
│   │   ├── int_research_with_sources.sql
│   │   └── int_demographic_profiles.sql
│   └── marts/
│       ├── mart_nil_policy_analysis.sql
│       ├── mart_research_effectiveness.sql
│       └── mart_geographic_equity_indicators.sql
├── tests/
│   └── generic/
├── macros/
└── seeds/
    └── state_fips_codes.csv
```

## Key Design Decisions

1. **Incremental, not rewrite** — each iteration builds on working code; no big-bang refactoring
2. **Mississippi NIL drives priorities** — features are built and validated against a concrete scenario
3. **Existing quick-research preserved** — current functionality remains accessible while methodology mode is added alongside
4. **Local-first LLM** — all NL processing uses Ollama/Mistral; no external LLM API dependencies
5. **Unified data layer** — vector store, Snowflake marts, operational DB, and public APIs queried through a single interface
6. **HITL is configurable** — checkpoints can be enabled/disabled per run; not mandatory for every execution
7. **Dagster as the single orchestration plane** — all data pipelines (research, ingestion, transformation) are Dagster assets with lineage, scheduling, and observability
8. **dbt for all transformations** — raw data is transformed in Snowflake via dbt with tests, documentation, and metrics; no ad-hoc SQL
9. **Medallion-style data architecture** — raw → staging → intermediate → mart layers in Snowflake, matching modern data platform patterns
10. **Supabase for operations, Snowflake for analytics** — Supabase (PostgreSQL + pgvector) owns real-time operational state and vector search; Snowflake owns analytical workloads and public dataset storage. Dagster syncs completed data from Supabase → Snowflake. The app never writes to Snowflake directly.
