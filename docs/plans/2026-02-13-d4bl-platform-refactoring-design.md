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
              ┌──────────────┼──────────────┐
              │              │              │
     ┌────────▼──────┐ ┌────▼─────┐ ┌──────▼───────┐
     │ Unified Data   │ │ CrewAI   │ │ HITL         │
     │ Layer          │ │ Agents   │ │ Framework    │
     │ ┌────────────┐ │ │(realigned│ │(approvals,   │
     │ │Vector Store│ │ │to D4BL   │ │ reviews)     │
     │ │(Supabase)  │ │ │stages)   │ │              │
     │ ├────────────┤ │ └──────────┘ └──────────────┘
     │ │Structured  │ │
     │ │DB (Postgres)│ │
     │ ├────────────┤ │
     │ │Public Data │ │
     │ │Connectors  │ │
     │ └────────────┘ │
     └────────────────┘
```

### New Modules

- **`src/d4bl/query/`** — NL query engine (vector search + SQL generation + result fusion)
- **`src/d4bl/methodology/`** — D4BL cycle state machine and stage management
- **`src/d4bl/hitl/`** — Human-in-the-loop checkpoint system
- **`src/d4bl/data/`** — Public dataset connectors and importers

### Enhanced Existing Modules

- **`src/d4bl/infra/vector_store.py`** — Fully integrated into the research pipeline
- **`src/d4bl/services/research_runner.py`** — HITL hooks, methodology stage awareness
- **`src/d4bl/agents/`** — Agents mapped to methodology stages
- **`src/d4bl/app/api.py`** — New endpoints for query, methodology, HITL

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

### Iteration 2: Public Data Ingestion

**Goal:** Combine qualitative research data with publicly available datasets for richer analysis.

**Scope:**
- Create `src/d4bl/data/` module with connectors:
  - Census API (demographics, income, education by geography)
  - State legislature data (bill tracking, Mississippi-specific)
  - BLS employment statistics
- Data importers that normalize and store in PostgreSQL with consistent schema
- Extend NL query engine to search across public datasets alongside research data
- Dataset management endpoints: `POST /api/data/import`, `GET /api/data/sources`

**Validation:** Query "What is the racial demographic breakdown of NCAA athletes in Mississippi?" and get results combining Census data with scraped research findings.

### Iteration 3: Human-in-the-Loop Checkpoints

**Goal:** Allow human review and approval at methodology stage transitions and between agent tasks.

**Scope:**
- Create `src/d4bl/hitl/` module:
  - Checkpoint type definitions (methodology-stage and agent-task levels)
  - WebSocket-based approval flow: pause → notify → wait for response
  - Checkpoint state persistence in PostgreSQL (survives browser refresh)
  - Configurable checkpoint placement
- Integrate into `research_runner.py` with hooks at configurable points
- Frontend: Approval UI component showing context, agent output, and approve/reject/edit options

**Checkpoint Flow:**
1. Execution reaches checkpoint → pauses
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
- Design inspired by blackwealthdata.org patterns

**Validation:** Complete the Mississippi NIL case entirely through the Methodology Mode UI, from community engagement input through power building outputs.

### Iteration 6: Communication + Distribution

**Goal:** Generate stakeholder-specific outputs and support multiple distribution formats.

**Scope:**
- Output templating system for different audiences:
  - Policy brief (for legislators)
  - Community report (for affected communities)
  - Academic summary (for researchers)
  - Data dashboard (for analysts)
- Export formats: PDF, presentation slides, structured data
- Communication channel suggestions based on audience analysis

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
         └──┬─────┬─────┬──┘
            │     │     │
   ┌────────▼┐ ┌──▼───┐ ┌▼──────────┐
   │Vector   │ │SQL   │ │Public API  │
   │Search   │ │Query │ │Connector   │
   │(Supabase│ │(PG)  │ │(Census etc)│
   └────┬────┘ └──┬───┘ └─────┬─────┘
        │         │            │
        └─────────┼────────────┘
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

### User Actions at Checkpoints

- **Approve** — continue execution
- **Reject with feedback** — re-run the preceding stage/task with feedback injected into the prompt
- **Edit output** — modify the agent's output directly, then continue

## Key Design Decisions

1. **Incremental, not rewrite** — each iteration builds on working code; no big-bang refactoring
2. **Mississippi NIL drives priorities** — features are built and validated against a concrete scenario
3. **Existing quick-research preserved** — current functionality remains accessible while methodology mode is added alongside
4. **Local-first LLM** — all NL processing uses Ollama/Mistral; no external LLM API dependencies
5. **Unified data layer** — vector store, structured DB, and public APIs queried through a single interface
6. **HITL is configurable** — checkpoints can be enabled/disabled per run; not mandatory for every execution
