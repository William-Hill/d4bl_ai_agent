# Staging Environment Setup Guide

This guide walks through setting up the staging infrastructure for the D4BL AI Agent.

## Overview

| Service | Provider | Tier |
|---------|----------|------|
| Backend (FastAPI) | Fly.io | shared-cpu-1x, 256MB |
| Frontend (Next.js) | Fly.io | shared-cpu-1x, 256MB |
| Crawl4AI | Fly.io | shared-cpu-1x, 512MB |
| Database + Vectors | Supabase Cloud | Free |
| LLM | Google Gemini Flash | Pay-per-use |
| Observability | Langfuse Cloud | Free (50k obs/mo) |

Estimated cost: ~$13-18/month

## Step 1: Supabase Cloud Setup

1. Go to [supabase.com](https://supabase.com) and sign in
2. Click **New Project**
3. Choose your organization and set:
   - **Name:** `d4bl-staging`
   - **Database Password:** generate a strong password and save it
   - **Region:** US East (or closest to your users)
4. Wait for the project to provision (~2 minutes)

### Get connection details

From the Supabase dashboard:

1. Go to **Settings > Database**
2. Find the **Connection string** section (URI format)
3. Note these values:
   - **Host:** `db.<project-ref>.supabase.co`
   - **Port:** `5432`
   - **User:** `postgres`
   - **Password:** the password you set
   - **Database:** `postgres`

### Enable pgvector extension

1. Go to **SQL Editor** in the Supabase dashboard
2. Run:
   ```sql
   CREATE EXTENSION IF NOT EXISTS vector;
   ```

## Step 2: Langfuse Cloud Setup

1. Go to [cloud.langfuse.com](https://cloud.langfuse.com) and sign up
2. Create a new project called `d4bl-staging`
3. Go to **Settings > API Keys**
4. Create a new API key pair
5. Note:
   - **Public Key:** `pk-lf-...`
   - **Secret Key:** `sk-lf-...`
   - **Host:** `https://cloud.langfuse.com`

## Step 3: Google Gemini API Key

1. Go to [aistudio.google.com/apikey](https://aistudio.google.com/apikey)
2. Click **Create API Key**
3. Select or create a Google Cloud project
4. Copy the API key

## Step 4: Fly.io Setup

### Install flyctl

```bash
# macOS
brew install flyctl

# Linux
curl -L https://fly.io/install.sh | sh

# Windows
powershell -Command "iwr https://fly.io/install.ps1 -useb | iex"
```

### Authenticate

```bash
flyctl auth login
```

### Create the three apps

```bash
# Backend API
flyctl apps create d4bl-api

# Frontend
flyctl apps create d4bl-frontend

# Crawl4AI
flyctl apps create d4bl-crawl4ai
```

### Set secrets on the backend app

```bash
flyctl secrets set \
  LLM_PROVIDER=gemini \
  LLM_MODEL=gemini-2.0-flash \
  LLM_API_KEY=<your-gemini-api-key> \
  POSTGRES_HOST=db.<project-ref>.supabase.co \
  POSTGRES_PORT=5432 \
  POSTGRES_USER=postgres \
  POSTGRES_PASSWORD=<your-supabase-db-password> \
  POSTGRES_DB=postgres \
  CRAWL_PROVIDER=crawl4ai \
  CRAWL4AI_BASE_URL=http://d4bl-crawl4ai.internal:11235 \
  LANGFUSE_HOST=https://cloud.langfuse.com \
  LANGFUSE_PUBLIC_KEY=<your-langfuse-public-key> \
  LANGFUSE_SECRET_KEY=<your-langfuse-secret-key> \
  CORS_ALLOWED_ORIGINS=https://d4bl-frontend.fly.dev \
  EMBEDDINGS_OLLAMA_BASE_URL=http://d4bl-api.internal:11434 \
  EMBEDDINGS_OLLAMA_MODEL_NAME=mxbai-embed-large \
  --app d4bl-api
```

### Set secrets on the frontend app

```bash
flyctl secrets set \
  NEXT_PUBLIC_API_URL=https://d4bl-api.fly.dev \
  API_INTERNAL_URL=http://d4bl-api.internal:8000 \
  --app d4bl-frontend
```

### Deploy manually (first time)

```bash
# From the repo root:
flyctl deploy --config fly.api.toml --remote-only
flyctl deploy --config fly.frontend.toml --remote-only
flyctl deploy --config fly.crawl4ai.toml --remote-only
```

### Verify deployment

```bash
# Check app status
flyctl status --app d4bl-api
flyctl status --app d4bl-frontend
flyctl status --app d4bl-crawl4ai

# Check health
curl https://d4bl-api.fly.dev/api/health
curl https://d4bl-frontend.fly.dev/

# View logs
flyctl logs --app d4bl-api
```

## Step 5: GitHub Secrets

Go to your repo on GitHub: **Settings > Secrets and variables > Actions**

Add these repository secrets:

| Secret | Value | Source |
|--------|-------|--------|
| `FLY_API_TOKEN` | `fo1_...` | `flyctl tokens create deploy -x 999999h` |
| `GEMINI_API_KEY` | `AI...` | Step 3 |
| `SUPABASE_URL` | `db.<ref>.supabase.co` | Step 1 |
| `SUPABASE_ANON_KEY` | `eyJ...` | Supabase dashboard > Settings > API |
| `SUPABASE_SERVICE_ROLE_KEY` | `eyJ...` | Supabase dashboard > Settings > API |
| `LANGFUSE_PUBLIC_KEY` | `pk-lf-...` | Step 2 |
| `LANGFUSE_SECRET_KEY` | `sk-lf-...` | Step 2 |

### Generate a Fly.io deploy token

```bash
flyctl tokens create deploy -x 999999h
```

Copy the token (starts with `fo1_`) and save it as the `FLY_API_TOKEN` secret.

## Step 6: Verify CI/CD

### PR Checks

1. Create a test branch and PR:
   ```bash
   git checkout -b test/ci-check
   echo "# test" >> README.md
   git add README.md && git commit -m "test: verify CI"
   git push -u origin test/ci-check
   gh pr create --title "Test CI" --body "Verify PR checks work"
   ```
2. Go to the PR on GitHub and verify the three checks run:
   - `python-checks` (lint + tests)
   - `frontend-checks` (lint + typecheck + build)
   - `docker-build` (smoke test)
3. Close the PR and delete the branch:
   ```bash
   gh pr close --delete-branch
   ```

### Auto-deploy

Once the epic branch is merged to `main`, the deploy workflow triggers automatically. You can also trigger it by pushing to any `epic/*` branch.

## Monitoring

### Fly.io Dashboard

Visit [fly.io/dashboard](https://fly.io/dashboard) to monitor:
- CPU/memory usage per app
- Request metrics
- Deployment history

### Langfuse

Visit [cloud.langfuse.com](https://cloud.langfuse.com) to monitor:
- LLM traces and spans
- Token usage and costs
- Evaluation results

### Scaling

If you need more resources:

```bash
# Scale up memory
flyctl scale memory 512 --app d4bl-api

# Scale to dedicated CPU
flyctl scale vm shared-cpu-2x --app d4bl-api

# Add another machine
flyctl scale count 2 --app d4bl-api
```

## Costs to Watch

| Item | Free tier limit | What happens when exceeded |
|------|----------------|---------------------------|
| Supabase | 500MB DB, 1GB bandwidth | Pauses project; upgrade to Pro ($25/mo) |
| Langfuse | 50k observations/mo | Stops ingesting; upgrade or self-host |
| Gemini Flash | $0 (pay-per-use) | Billed to Google Cloud; ~$0.10/1M input tokens |
| Fly.io | No free tier | Billed monthly; check `flyctl billing` |
