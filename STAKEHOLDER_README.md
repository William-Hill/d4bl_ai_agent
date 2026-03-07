# D4BL AI Agent - Local Setup Guide

This guide helps you run the D4BL Research and Analysis Tool on your local machine.
Your research data is stored in a shared cloud database, isolated by your `TENANT_ID`.
Each organization's data is scoped so only members with the same tenant identifier
can view each other's research. Other tenants cannot access your data.

> **Important:** Your `.env.stakeholder` file contains database credentials.
> Do not commit it to version control or share it outside your organization.

## Prerequisites

1. **Docker Desktop** - [Install Docker](https://docs.docker.com/get-docker/)
2. **Ollama** - [Install Ollama](https://ollama.com/download)

## Setup

### 1. Install and start Ollama

After installing Ollama, pull the required models:

```bash
ollama pull mistral
ollama pull mxbai-embed-large
```

Make sure Ollama is running (it starts automatically on most systems).

### 2. Configure your environment

```bash
cp .env.stakeholder.example .env.stakeholder
```

Edit `.env.stakeholder` and fill in:
- `TENANT_ID` - your organization identifier (provided by D4BL)
- `POSTGRES_HOST` - shared database host (provided by D4BL)
- `POSTGRES_USER` - database username (provided by D4BL)
- `POSTGRES_PASSWORD` - database password (provided by D4BL)

### 3. Start the application

```bash
docker compose -f docker-compose.stakeholder.yml --env-file .env.stakeholder up --build
```

### 4. Open the app

Visit [http://localhost:3000](http://localhost:3000) in your browser.

## Stopping

```bash
docker compose -f docker-compose.stakeholder.yml down
```

## Troubleshooting

- **"Cannot connect to Ollama"** - Make sure Ollama is running: `ollama serve`
- **"Database connection failed"** - Check your `.env.stakeholder` credentials
- **Slow first run** - Docker needs to download images (~2-3 GB). Subsequent runs are fast.
