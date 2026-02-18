# Langfuse Setup Guide

This guide explains how to set up and use Langfuse for observability of your CrewAI agents.

## Overview

Langfuse provides comprehensive observability for your LLM applications, including:
- **Tracing**: Detailed traces of agent execution, LLM calls, and tool usage
- **Monitoring**: Performance metrics and latency tracking
- **Debugging**: Step-by-step execution logs and error tracking
- **Analytics**: Usage patterns and cost analysis

## Prerequisites

- Docker and Docker Compose installed
- Langfuse services will be automatically started with `docker-compose up`

## Setup Steps

### 1. Start Langfuse Services

Langfuse services are included in the `docker-compose.yml` file. When you run:

```bash
docker-compose up
```

The following services will be started:
- **langfuse-postgres**: PostgreSQL database for Langfuse metadata (port 5433)
- **langfuse-clickhouse**: ClickHouse database for traces and analytics (ports 8123, 9000)
- **langfuse**: Langfuse server (port 3000)

### 2. Access Langfuse UI

Once the services are running, access the Langfuse UI at:
- **Langfuse Dashboard**: http://localhost:3001

**Note**: On first access, you'll need to create an account. The first user created will be the admin.

### 3. Get API Keys

After creating your account:

1. Go to **Settings** → **API Keys**
2. Create a new API key pair:
   - **Public Key** (starts with `pk-lf-...`)
   - **Secret Key** (starts with `sk-lf-...`)

### 4. Configure Environment Variables

Add the following to your `.env` file:

```bash
# Langfuse Configuration
LANGFUSE_PUBLIC_KEY=pk-lf-your-public-key-here
LANGFUSE_SECRET_KEY=sk-lf-your-secret-key-here
LANGFUSE_HOST=http://localhost:3001
LANGFUSE_BASE_URL=http://localhost:3001

# Optional: Customize Langfuse database settings
LANGFUSE_POSTGRES_USER=langfuse
LANGFUSE_POSTGRES_PASSWORD=langfuse_password
LANGFUSE_POSTGRES_DB=langfuse
LANGFUSE_CLICKHOUSE_USER=langfuse
LANGFUSE_CLICKHOUSE_PASSWORD=langfuse_password
LANGFUSE_CLICKHOUSE_DB=langfuse
LANGFUSE_NEXTAUTH_SECRET=your-secret-key-change-in-production
LANGFUSE_SALT=your-salt-change-in-production
```

**Important**: 
- For Docker deployments, use `LANGFUSE_HOST=http://langfuse:3000` (internal service name, port 3000 is internal)
- For local development, use `LANGFUSE_HOST=http://localhost:3001` (external port 3001)

### 5. Restart Services

After adding the API keys to your `.env` file:

```bash
docker-compose restart d4bl-api
```

Or restart all services:

```bash
docker-compose down
docker-compose up
```

## How It Works

### Automatic Instrumentation

The CrewAI instrumentation is automatically initialized when the `crew.py` module is imported. This means:

1. **No code changes required**: All CrewAI agent executions are automatically traced
2. **Automatic capture**: LLM calls, tool usage, and agent interactions are captured
3. **Zero overhead**: Instrumentation is lightweight and doesn't affect performance

### What Gets Traced

The following are automatically captured:

- **Agent executions**: Each agent's role, goal, and backstory
- **Task processing**: Task descriptions, expected outputs, and results
- **LLM calls**: Model used, prompts, responses, tokens, and latency
- **Tool usage**: Tool calls, inputs, outputs, and execution time
- **Crew orchestration**: Task dependencies and execution flow

### Viewing Traces

1. **Access Langfuse UI**: http://localhost:3001
2. **Navigate to Traces**: Click on "Traces" in the sidebar
3. **Filter and Search**: Use filters to find specific traces
4. **View Details**: Click on any trace to see detailed execution information

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `LANGFUSE_PUBLIC_KEY` | Langfuse public API key | Required |
| `LANGFUSE_SECRET_KEY` | Langfuse secret API key | Required |
| `LANGFUSE_HOST` | Langfuse server URL | `http://localhost:3000` |
| `LANGFUSE_BASE_URL` | Alternative base URL setting | Same as `LANGFUSE_HOST` |

### Docker Compose Services

The Langfuse services are configured with:

- **PostgreSQL**: Stores metadata and configuration
- **ClickHouse**: Stores traces and analytics data
- **Langfuse Server**: Main application server

All services are on the `d4bl-network` Docker network for internal communication.

## Troubleshooting

### Langfuse UI Not Accessible

1. **Check service status**:
   ```bash
   docker-compose ps
   ```

2. **Check logs**:
   ```bash
   docker-compose logs langfuse
   ```

3. **Verify port 3001 is available**:
   ```bash
   lsof -i :3001
   ```

### Traces Not Appearing

1. **Verify API keys are set**:
   ```bash
   docker-compose exec d4bl-api env | grep LANGFUSE
   ```

2. **Check Langfuse connection**:
   ```bash
   docker-compose logs d4bl-api | grep Langfuse
   ```

3. **Verify instrumentation**:
   Look for "✅ CrewAI instrumentation initialized" in the logs

### Authentication Errors

1. **Verify keys are correct**: Check that keys match those in Langfuse UI
2. **Check key format**: Keys should start with `pk-lf-` and `sk-lf-`
3. **Verify host URL**: Ensure `LANGFUSE_HOST` matches your setup

## Advanced Usage

### Custom Spans

You can add custom spans to your traces:

```python
from langfuse import get_client

langfuse = get_client()

with langfuse.start_as_current_observation(
    as_type="span",
    name="custom-operation",
) as span:
    # Your code here
    span.update_trace(
        input="your input",
        output="your output",
    )
```

### Adding Metadata

Add custom metadata to traces:

```python
from langfuse import propagate_attributes

with propagate_attributes(
    user_id="user_123",
    session_id="session_abc",
    tags=["production", "crewai"],
    metadata={"version": "1.0.0"},
):
    # Your crew execution
    crew.kickoff()
```

### Scoring Traces

Add scores for evaluation:

```python
span.score(name="relevance", value=0.9, data_type="NUMERIC")
span.score_trace(name="feedback", value="positive", data_type="CATEGORICAL")
```

## Resources

- [Langfuse Documentation](https://langfuse.com/docs)
- [CrewAI Integration Guide](https://langfuse.com/integrations/frameworks/crewai)
- [Self-Hosting Guide](https://langfuse.com/self-hosting)

## Security Notes

- **Production**: Change default passwords and secrets in `.env`
- **API Keys**: Keep your secret key secure and never commit it to version control
- **Network**: Langfuse services are on an internal Docker network by default
- **Access**: The Langfuse UI is exposed on port 3001 - consider adding authentication for production

