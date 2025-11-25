# Testing Langfuse Integration with CrewAI Agents

This guide explains how to test that Langfuse is working correctly with your CrewAI agents.

## Prerequisites

1. **Langfuse services are running**:
   ```bash
   docker compose ps
   ```
   You should see `langfuse`, `langfuse-postgres`, `langfuse-clickhouse`, `langfuse-redis`, and `langfuse-minio` all running.

2. **Get your Langfuse API keys**:
   - Access the Langfuse UI at: http://localhost:3001
   - If this is your first time, you'll need to create an account
   - Go to Settings → API Keys
   - Create a new API key pair (Public Key and Secret Key)

3. **Configure your `.env` file**:
   ```bash
   # Langfuse Configuration
   LANGFUSE_PUBLIC_KEY=pk-lf-your-public-key-here
   LANGFUSE_SECRET_KEY=sk-lf-your-secret-key-here
   LANGFUSE_HOST=http://localhost:3001
   LANGFUSE_BASE_URL=http://localhost:3001
   ```

## Testing Steps

### Step 1: Verify Langfuse is Initialized

1. **Check the API logs** to see if Langfuse initialized:
   ```bash
   docker compose logs d4bl-api | grep -i langfuse
   ```

   You should see messages like:
   ```
   ✅ Langfuse client authenticated and ready!
   ✅ CrewAI instrumentation initialized for Langfuse observability
      Langfuse Host: http://localhost:3001
   ```

2. **If you see warnings**, check:
   - Are the API keys set in your `.env` file?
   - Are the keys correct? (They should start with `pk-lf-` and `sk-lf-`)
   - Is `LANGFUSE_HOST` pointing to the correct URL?

### Step 2: Run a Test Research Job

1. **Start your services** (if not already running):
   ```bash
   docker compose up -d
   ```

2. **Submit a research job** through your UI or API:
   - Access your frontend at: http://localhost:3000
   - Or use the API directly:
     ```bash
     curl -X POST http://localhost:8000/api/research \
       -H "Content-Type: application/json" \
       -d '{
         "query": "What are the latest trends in AI?",
         "summary_format": "detailed"
       }'
     ```

3. **Wait for the job to complete** (this may take a few minutes)

### Step 3: Verify Traces in Langfuse

1. **Open Langfuse UI**: http://localhost:3001

2. **Check the Traces page**:
   - Navigate to "Traces" in the sidebar
   - You should see traces from your CrewAI agents
   - Each trace should show:
     - The overall research job execution
     - Individual agent activities (researcher, data_analyst, etc.)
     - Tool calls (Firecrawl searches, etc.)
     - LLM calls and responses

3. **Inspect a trace**:
   - Click on a trace to see detailed information
   - You should see:
     - **Spans**: Individual operations (agent tasks, tool calls, LLM calls)
     - **Timing**: How long each operation took
     - **Inputs/Outputs**: What was sent to and received from each component
     - **Metadata**: Additional context about the execution

### Step 4: Verify Agent Activities

In a trace, you should see:

1. **Agent Spans**:
   - `researcher` agent activities
   - `data_analyst` agent activities
   - Any other agents you have configured

2. **Tool Spans**:
   - Firecrawl search operations
   - Any other tools your agents use

3. **LLM Spans**:
   - Calls to Ollama (or other LLM providers)
   - Request/response pairs
   - Token usage (if available)

## Troubleshooting

### No Traces Appearing

1. **Check API logs**:
   ```bash
   docker compose logs d4bl-api | tail -50
   ```
   Look for Langfuse-related errors or warnings.

2. **Verify environment variables**:
   ```bash
   docker compose exec d4bl-api env | grep LANGFUSE
   ```
   Make sure all required variables are set.

3. **Check Langfuse connection**:
   ```bash
   docker compose logs langfuse | tail -50
   ```
   Look for any errors in the Langfuse container.

4. **Verify instrumentation**:
   The CrewAI instrumentation should be initialized automatically when the `crew.py` module is imported. Check the logs for:
   ```
   ✅ CrewAI instrumentation initialized for Langfuse observability
   ```

### Traces Appear but Are Empty

- This might indicate that the instrumentation isn't capturing the crew execution properly
- Check that `CrewAIInstrumentor().instrument()` was called successfully
- Verify that the crew is actually running (check your application logs)

### Authentication Errors

If you see authentication errors:
1. Verify your API keys are correct
2. Make sure `LANGFUSE_HOST` matches where Langfuse is accessible from the `d4bl-api` container
   - From inside Docker: `http://langfuse:3000`
   - From host: `http://localhost:3001`
3. Check that the keys haven't expired or been revoked in Langfuse UI

## Expected Behavior

When working correctly, you should see:

1. **Automatic trace creation** for each research job
2. **Nested spans** showing the hierarchy of operations:
   - Trace (top level - the entire research job)
     - Span (agent execution)
       - Span (tool call)
       - Span (LLM call)
3. **Timing information** for performance analysis
4. **Input/output data** for debugging
5. **Error tracking** if something goes wrong

## Next Steps

Once you've verified Langfuse is working:

1. **Explore the Langfuse UI** to understand the data being captured
2. **Set up alerts** for errors or performance issues
3. **Use the data** to optimize your agent workflows
4. **Create dashboards** to monitor agent performance over time

## Additional Resources

- [Langfuse Documentation](https://langfuse.com/docs)
- [CrewAI Integration Guide](https://langfuse.com/integrations/frameworks/crewai)
- [OpenInference Specification](https://github.com/Arize-ai/openinference)

