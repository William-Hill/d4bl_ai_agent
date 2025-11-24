# Development Guide

This guide covers local development without Docker.

## Prerequisites

See [Prerequisites Guide](PREREQUISITES.md) for detailed setup instructions. You'll need:

- Python 3.10-3.13
- Node.js 18+
- Ollama installed and running
- Firecrawl API key

## Setup

### 1. Python Environment

```bash
# Create virtual environment
python3.13 -m venv .venv

# Activate virtual environment
source .venv/bin/activate  # macOS/Linux
# or
.venv\Scripts\activate     # Windows

# Install dependencies
pip install -r requirements.txt
```

### 2. Frontend Dependencies

```bash
cd ui-nextjs
npm install
cd ..
```

### 3. Environment Variables

Create a `.env` file in the project root:

```bash
FIRECRAWL_API_KEY=your_firecrawl_api_key
OLLAMA_BASE_URL=http://localhost:11434
```

## Running Locally

### Start Backend

```bash
# Activate virtual environment
source .venv/bin/activate

# Start FastAPI server
python run_ui.py
```

Backend will be available at http://localhost:8000

### Start Frontend

In a separate terminal:

```bash
cd ui-nextjs
npm run dev
```

Frontend will be available at http://localhost:3000

## Project Structure

```
d4bl_ai_agent/
├── src/d4bl/
│   ├── api.py            # FastAPI backend
│   ├── crew.py           # CrewAI agents
│   └── main.py           # CLI entry point
├── ui-nextjs/            # Next.js frontend
│   ├── app/              # App Router pages
│   ├── components/       # React components
│   ├── hooks/            # Custom hooks
│   └── lib/              # Utilities
├── output/               # Generated reports
└── docs/                 # Documentation
```

## Development Workflow

### Backend Development

1. Make changes to Python files in `src/d4bl/`
2. Backend auto-reloads (uvicorn reload enabled)
3. Check logs in terminal for errors

### Frontend Development

1. Make changes to files in `ui-nextjs/`
2. Next.js hot-reloads automatically
3. Check browser console for errors

### Testing Changes

1. Start both backend and frontend
2. Open http://localhost:3000
3. Submit a test query
4. Monitor logs in both terminals

## Code Style

### Python

- Follow PEP 8 style guide
- Use type hints where possible
- Format with `black` (if configured)
- Lint with `flake8` or `pylint` (if configured)

### TypeScript/React

- Use TypeScript for type safety
- Follow React best practices
- Use functional components with hooks
- Format with Prettier (if configured)

## Debugging

### Backend Debugging

```bash
# Run with debug logging
python run_ui.py

# Check logs in terminal
# Use print() statements or logging module
```

### Frontend Debugging

- Use browser DevTools
- Check Network tab for API calls
- Check Console for errors
- Use React DevTools extension

### WebSocket Debugging

```javascript
// In browser console
const ws = new WebSocket('ws://localhost:8000/ws/{job_id}');
ws.onmessage = (e) => console.log('WS:', JSON.parse(e.data));
ws.onerror = (e) => console.error('WS Error:', e);
```

## Common Development Tasks

### Adding a New API Endpoint

1. Edit `src/d4bl/api.py`
2. Add route handler:
   ```python
   @app.get("/api/new-endpoint")
   async def new_endpoint():
       return {"message": "Hello"}
   ```
3. Test at http://localhost:8000/api/new-endpoint

### Adding a New Frontend Component

1. Create component in `ui-nextjs/components/`
2. Import and use in `ui-nextjs/app/page.tsx`
3. Component hot-reloads automatically

### Modifying Agent Behavior

1. Edit `src/d4bl/crew.py`
2. Modify agent configurations
3. Restart backend to apply changes

### Updating Dependencies

**Python:**
```bash
pip install --upgrade package-name
pip freeze > requirements.txt
```

**Node.js:**
```bash
cd ui-nextjs
npm install package-name
npm install  # Updates package-lock.json
```

## Testing

### Manual Testing

1. Test research job creation
2. Verify WebSocket connection
3. Check live logs streaming
4. Verify results display

### API Testing

Use the interactive docs at http://localhost:8000/docs

Or use curl:
```bash
curl -X POST http://localhost:8000/api/research \
  -H "Content-Type: application/json" \
  -d '{"query": "test", "summary_format": "brief"}'
```

## Troubleshooting

### Backend won't start

- Check Python version: `python --version`
- Verify virtual environment is activated
- Check dependencies: `pip list`
- Check for port conflicts: `lsof -i :8000`

### Frontend won't start

- Check Node.js version: `node --version`
- Verify dependencies: `cd ui-nextjs && npm list`
- Clear cache: `rm -rf ui-nextjs/.next`
- Check for port conflicts: `lsof -i :3000`

### WebSocket connection fails

- Verify backend is running
- Check CORS settings in `api.py`
- Check browser console for errors
- Verify WebSocket URL format

### Agents not working

- Verify Ollama is running: `curl http://localhost:11434/api/tags`
- Check Mistral model: `ollama list`
- Verify API keys in `.env`
- Check backend logs for errors

## Building for Production

### Backend

```bash
# No build step needed for Python
# Just ensure dependencies are installed
pip install -r requirements.txt
```

### Frontend

```bash
cd ui-nextjs
npm run build
npm start  # Runs production server
```

## Contributing

See [Contributing Guidelines](CONTRIBUTING.md) for details on:
- Code style
- Commit messages
- Pull request process
- Testing requirements

## Additional Resources

- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Next.js Documentation](https://nextjs.org/docs)
- [CrewAI Documentation](https://docs.crewai.com/)
- [Ollama Documentation](https://ollama.ai/docs)

