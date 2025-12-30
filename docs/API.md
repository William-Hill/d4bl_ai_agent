# API Reference

This document describes the REST API and WebSocket endpoints for the D4BL Research and Analysis Tool.

## Base URL

- **Local Development**: `http://localhost:8000`
- **Docker**: `http://localhost:8000`

## Authentication

Currently, no authentication is required. For production deployments, implement authentication.

## REST API Endpoints

### Create Research Job

Create a new research job.

**Endpoint**: `POST /api/research`

**Request Body**:
```json
{
  "query": "How does algorithmic bias affect criminal justice?",
  "summary_format": "detailed"
}
```

**Parameters**:
- `query` (string, required): Research question or topic
- `summary_format` (string, optional): One of `"brief"`, `"detailed"`, or `"comprehensive"`. Default: `"detailed"`

**Response** (200 OK):
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "pending",
  "message": "Research job created successfully"
}
```

**Error Responses**:
- `400 Bad Request`: Invalid input (empty query or invalid summary_format)
- `500 Internal Server Error`: Server error during job creation

### Get Job Status

Get the current status of a research job.

**Endpoint**: `GET /api/jobs/{job_id}`

**Path Parameters**:
- `job_id` (string, required): Job identifier

**Response** (200 OK):
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "completed",
  "progress": "Research completed successfully!",
  "result": {
    "raw_output": "...",
    "tasks_output": [
      {
        "agent": "Researcher",
        "description": "...",
        "output": "..."
      }
    ],
    "report": "# Research Report\n\n..."
  }
}
```

**Status Values**:
- `pending`: Job created but not started
- `running`: Job is currently executing
- `completed`: Job finished successfully
- `error`: Job failed with an error

**Error Responses**:
- `404 Not Found`: Job ID not found

### Health Check

Check if the API is running.

**Endpoint**: `GET /api/health`

**Response** (200 OK):
```json
{
  "status": "healthy",
  "timestamp": "2024-01-15T10:30:00.000Z"
}
```

## WebSocket API

### Connect to Job Updates

Connect to real-time updates for a specific job.

**Endpoint**: `ws://localhost:8000/ws/{job_id}`

**Path Parameters**:
- `job_id` (string, required): Job identifier

**Connection**:
```javascript
const ws = new WebSocket(`ws://localhost:8000/ws/${jobId}`);

ws.onopen = () => {
  console.log('Connected');
};

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('Message:', data);
};

ws.onerror = (error) => {
  console.error('Error:', error);
};

ws.onclose = () => {
  console.log('Disconnected');
};
```

### Message Types

#### Progress Update

Sent when job status changes.

```json
{
  "type": "progress",
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "running",
  "progress": "Starting research task..."
}
```

#### Live Log

Sent when agents produce output (real-time streaming).

```json
{
  "type": "log",
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "message": "[Researcher] Searching for information about...",
  "timestamp": "2024-01-15T10:30:00.000Z"
}
```

#### Job Complete

Sent when job finishes successfully.

```json
{
  "type": "complete",
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "completed",
  "result": {
    "raw_output": "...",
    "tasks_output": [...],
    "report": "# Research Report\n\n..."
  },
  "logs": ["[Researcher] ...", "[Analyst] ...", ...]
}
```

#### Error

Sent when job fails.

```json
{
  "type": "error",
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "error",
  "error": "Failed to run crew: Connection timeout",
  "logs": ["[Researcher] ...", "ERROR: ..."]
}
```

#### Status

Sent when WebSocket first connects (current job status).

```json
{
  "type": "status",
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "running",
  "progress": "Processing research...",
  "logs": ["[Researcher] ..."]
}
```

## Interactive API Documentation

FastAPI provides interactive API documentation:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

You can test endpoints directly from these interfaces.

## Example Usage

### JavaScript/TypeScript

```typescript
// Create research job
const response = await fetch('http://localhost:8000/api/research', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    query: 'How does algorithmic bias affect criminal justice?',
    summary_format: 'detailed'
  })
});

const { job_id } = await response.json();

// Connect to WebSocket for updates
const ws = new WebSocket(`ws://localhost:8000/ws/${job_id}`);

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  
  switch (data.type) {
    case 'log':
      console.log('Agent output:', data.message);
      break;
    case 'progress':
      console.log('Progress:', data.progress);
      break;
    case 'complete':
      console.log('Results:', data.result);
      break;
    case 'error':
      console.error('Error:', data.error);
      break;
  }
};
```

### Python

```python
import requests
import websocket
import json

# Create research job
response = requests.post(
    'http://localhost:8000/api/research',
    json={
        'query': 'How does algorithmic bias affect criminal justice?',
        'summary_format': 'detailed'
    }
)
job_id = response.json()['job_id']

# Connect to WebSocket
def on_message(ws, message):
    data = json.loads(message)
    if data['type'] == 'log':
        print(f"Agent: {data['message']}")
    elif data['type'] == 'complete':
        print(f"Results: {data['result']}")

ws = websocket.WebSocketApp(
    f'ws://localhost:8000/ws/{job_id}',
    on_message=on_message
)
ws.run_forever()
```

### cURL

```bash
# Create research job
curl -X POST http://localhost:8000/api/research \
  -H "Content-Type: application/json" \
  -d '{
    "query": "How does algorithmic bias affect criminal justice?",
    "summary_format": "detailed"
  }'

# Get job status
curl http://localhost:8000/api/jobs/{job_id}

# Health check
curl http://localhost:8000/api/health
```

## Rate Limiting

Currently, no rate limiting is implemented. For production, implement rate limiting to prevent abuse.

## Error Handling

All errors follow a consistent format:

```json
{
  "detail": "Error message description"
}
```

Common HTTP status codes:
- `400`: Bad Request (invalid input)
- `404`: Not Found (resource doesn't exist)
- `500`: Internal Server Error (server-side error)

## WebSocket Best Practices

1. **Reconnection**: Implement automatic reconnection logic
2. **Heartbeat**: Send periodic ping messages to keep connection alive
3. **Error Handling**: Handle connection errors gracefully
4. **Message Queuing**: Queue messages if connection is temporarily lost
5. **Cleanup**: Close WebSocket when job completes or component unmounts

## Future API Enhancements

See [Future Work](FUTURE_WORK.md) for planned API improvements including:
- Authentication and authorization
- Rate limiting
- Webhook support
- Batch job processing
- Job cancellation
- Result pagination


