# Phoenix by Arize AI Setup Guide

This guide explains how to set up and use Phoenix by Arize AI for observability of your CrewAI agents.

## Overview

Phoenix by Arize AI is an open-source observability platform for LLM applications. It provides:
- **Tracing**: Detailed traces of agent execution, LLM calls, and tool usage
- **Monitoring**: Performance metrics and latency tracking
- **Debugging**: Step-by-step execution logs and error tracking
- **Evaluation**: Built-in evaluation metrics for LLM applications

Reference: [Phoenix CrewAI Integration Documentation](https://arize.com/docs/phoenix/integrations/python/crewai/crewai-tracing)

## Prerequisites

- Docker and Docker Compose installed
- Phoenix is included in the `docker-compose.yml` file and will start automatically

Reference: [Phoenix Docker Deployment Documentation](https://arize.com/docs/phoenix/self-hosting/deployment-options/docker)

## Setup Steps

### 1. Start Phoenix Service

Phoenix is included in the `docker-compose.yml` file. When you run:

```bash
docker compose up
```

The following service will be started:
- **phoenix**: Phoenix observability server using the official Docker image `arizephoenix/phoenix:latest`
  - Port 6006: Phoenix UI and OTLP HTTP collector
  - Port 4317: OTLP gRPC collector

### 2. Access Phoenix UI

Once the service is running, access the Phoenix UI at:
- **Phoenix Dashboard**: http://localhost:6006

### 3. Configure Environment Variables (Optional)

Phoenix doesn't require API keys or authentication. You can optionally configure:

```bash
# Phoenix Configuration (optional)
PHOENIX_PROJECT_NAME=d4bl-crewai  # Default project name for traces
```

### 4. Restart Services

After any configuration changes:

```bash
docker compose restart d4bl-api
```

Or restart all services:

```bash
docker compose down
docker compose up
```

## How It Works

### Automatic Instrumentation

The Phoenix observability is automatically initialized when the `crew.py` module is imported using `phoenix.otel.register()`. This means:

1. **No code changes required**: All CrewAI agent executions are automatically traced
2. **Automatic capture**: LLM calls, tool usage, and agent interactions are captured
3. **Zero overhead**: Instrumentation is lightweight and doesn't affect performance
4. **Automatic OpenTelemetry setup**: The `register()` function automatically configures OpenTelemetry to send traces to Phoenix

### What Gets Traced

The following are automatically captured:

- **Agent executions**: Each agent's role, goal, and backstory
- **Task processing**: Task descriptions, expected outputs, and results
- **LLM calls**: Model used, prompts, responses, tokens, and latency
- **Tool usage**: Tool calls, inputs, outputs, and execution time
- **Crew orchestration**: Task dependencies and execution flow

### Viewing Traces

1. **Access Phoenix UI**: http://localhost:6006
2. **Navigate to Traces**: Traces will appear automatically as your agents run
3. **Filter and Search**: Use filters to find specific traces
4. **View Details**: Click on any trace to see detailed execution information

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `PHOENIX_PROJECT_NAME` | Project name for organizing traces | `d4bl-crewai` |

**Note**: The `phoenix.otel.register()` function automatically configures OpenTelemetry to connect to Phoenix. When running in Docker, it connects to the `phoenix` service via the Docker network. No manual endpoint configuration is needed.

## Advantages of Phoenix

1. **No Authentication Required**: Unlike Langfuse, Phoenix doesn't require API keys
2. **Simple Docker Setup**: Single Docker service, no complex dependencies (PostgreSQL, ClickHouse, Redis, MinIO)
3. **Open Source**: Fully open-source with no vendor lock-in
4. **Built-in Evaluation**: Includes evaluation metrics for LLM applications
5. **OpenTelemetry Native**: Built on OpenTelemetry for full transparency
6. **Easy Integration**: Simple `phoenix.otel.register()` call handles all configuration
7. **Official Docker Image**: Uses the official `arizephoenix/phoenix` Docker image

## Troubleshooting

### Phoenix UI Not Accessible

1. **Check if Phoenix container is running**:
   ```bash
   docker compose ps phoenix
   ```

2. **Check Phoenix logs**:
   ```bash
   docker compose logs phoenix
   ```

3. **Verify port is not in use**:
   ```bash
   lsof -i :6006
   ```

4. **Restart Phoenix service**:
   ```bash
   docker compose restart phoenix
   ```

### No Traces Appearing

1. **Check API logs**:
   ```bash
   docker compose logs d4bl-api | grep -i phoenix
   ```

2. **Verify environment variables**:
   ```bash
   docker compose exec d4bl-api env | grep PHOENIX
   ```

3. **Check OpenTelemetry configuration**:
   ```bash
   docker compose logs d4bl-api | grep -i "instrumentation\|OTLP"
   ```

4. **Verify instrumentation**:
   The Phoenix observability should be initialized automatically when the `crew.py` module is imported. Check the logs for:
   ```
   ✅ Phoenix observability initialized
   ```

### Traces Appear but Are Empty

- This might indicate that the instrumentation isn't capturing the crew execution properly
- Check that `CrewAIInstrumentor().instrument()` was called successfully
- Verify that the crew is actually running (check your application logs)

## Testing

1. **Run a test research job** through your UI or API
2. **Check Phoenix UI**: http://localhost:6006
3. **Look for traces** - they should appear automatically as the crew runs

## Additional Resources

- [Phoenix Documentation](https://docs.arize.com/phoenix)
- [Phoenix GitHub Repository](https://github.com/Arize-ai/phoenix)
- [OpenInference Specification](https://github.com/Arize-ai/openinference)

