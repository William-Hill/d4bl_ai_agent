# D4BL AI Agent UI

A modern web interface for interacting with the D4BL AI Agent research tool. The UI allows you to submit research queries, track progress in real-time, and view results in a clean, user-friendly interface.

## Features

- 🎨 **Modern, Responsive UI** - Clean and intuitive interface that works on desktop and mobile
- ⚡ **Real-time Progress Updates** - WebSocket-based progress tracking
- 📊 **Multiple Summary Formats** - Choose from brief, detailed, or comprehensive summaries
- 🔄 **Async Processing** - Non-blocking research jobs with status tracking
- 🐳 **Docker Support** - Easy deployment with Docker and Docker Compose

## Quick Start

### Option 1: Run Locally (Recommended for Development)

1. **Install dependencies** (if not already installed):
   ```bash
   pip install -r requirements.txt
   ```

2. **Start the UI server**:
   ```bash
   python run_ui.py
   ```

3. **Open your browser**:
   Navigate to `http://localhost:8000`

### Option 2: Run with Docker Compose (Recommended for Deployment)

1. **Ensure you have a `.env` file** with your API keys:
   ```bash
   FIRECRAWL_API_KEY=your_key_here
   OLLAMA_BASE_URL=http://ollama:11434
   ```

2. **Start all services** (includes Ollama):
   ```bash
   docker-compose up
   ```

3. **Open your browser**:
   Navigate to `http://localhost:8000`

### Option 3: Run with Docker (Standalone)

1. **Build the Docker image**:
   ```bash
   docker build -t d4bl-ui .
   ```

2. **Run the container**:
   ```bash
   docker run -p 8000:8000 --env-file .env d4bl-ui
   ```

   Note: If using Ollama, make sure it's accessible from the container.

## Usage

1. **Enter a Research Query**: Type your research question in the text area
   - Example: "How does algorithmic bias affect criminal justice outcomes for Black communities?"

2. **Select Summary Format**:
   - **Brief**: 250-500 words, key findings only
   - **Detailed**: 1000-1500 words, thorough analysis (default)
   - **Comprehensive**: 2000-3000 words, in-depth report

3. **Click "Start Research"**: The system will:
   - Create a research job
   - Show real-time progress updates
   - Display results when complete

4. **View Results**: Results include:
   - Research report (formatted markdown)
   - Task outputs from each agent
   - Raw research data

## API Endpoints

The UI is backed by a FastAPI server with the following endpoints:

- `GET /` - Main UI page
- `POST /api/research` - Create a new research job
- `GET /api/jobs/{job_id}` - Get job status
- `WS /ws/{job_id}` - WebSocket for real-time updates
- `GET /api/health` - Health check
- `GET /docs` - Interactive API documentation (Swagger UI)

## Architecture

```
┌─────────────┐
│   Browser   │
│  (Frontend) │
└──────┬──────┘
       │ HTTP/WebSocket
       ▼
┌─────────────┐
│  FastAPI    │
│   Server    │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│   CrewAI    │
│   Agents    │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│   Ollama    │
│    LLM      │
└─────────────┘
```

## Development

### Project Structure

```
.
├── ui/                 # Frontend files
│   ├── index.html     # Main HTML
│   ├── styles.css     # Styling
│   └── app.js         # JavaScript logic
├── src/
│   └── d4bl/
│       ├── api.py     # FastAPI backend
│       └── crew.py    # CrewAI agents
├── run_ui.py          # Development server script
├── Dockerfile         # Docker configuration
└── docker-compose.yml # Docker Compose setup
```

### Making Changes

1. **Frontend Changes**: Edit files in `ui/` directory
   - HTML: `ui/index.html`
   - CSS: `ui/styles.css`
   - JavaScript: `ui/app.js`

2. **Backend Changes**: Edit `src/d4bl/api.py`

3. **Auto-reload**: The development server (`run_ui.py`) includes auto-reload for Python changes. Refresh your browser for frontend changes.

### Testing

1. **Test the API directly**:
   ```bash
   curl -X POST http://localhost:8000/api/research \
     -H "Content-Type: application/json" \
     -d '{"query": "Test query", "summary_format": "brief"}'
   ```

2. **Check API documentation**:
   Visit `http://localhost:8000/docs` for interactive API docs

## Deployment

### Production Considerations

1. **Environment Variables**: Set production values in `.env` or environment
2. **CORS**: Update CORS settings in `api.py` to restrict origins
3. **Security**: Add authentication/authorization as needed
4. **Database**: Replace in-memory job storage with a database (Redis, PostgreSQL, etc.)
5. **Reverse Proxy**: Use nginx or similar for production
6. **HTTPS**: Configure SSL/TLS certificates

### Example Production Setup with Nginx

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # WebSocket support
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

## Troubleshooting

### UI Not Loading

- Check that the `ui/` directory exists and contains `index.html`
- Verify the server is running on the correct port
- Check browser console for errors

### WebSocket Connection Issues

- Ensure WebSocket support is enabled in your reverse proxy (if using one)
- Check firewall settings
- Verify the job_id is valid

### Research Jobs Failing

- Check that Ollama is running and accessible
- Verify API keys in `.env` file
- Check server logs for detailed error messages
- Ensure output directory exists and is writable

### Docker Issues

- Ensure Docker and Docker Compose are installed
- Check that ports 8000 and 11434 are available
- Verify `.env` file exists and contains required keys
- Check container logs: `docker-compose logs`

## Future Enhancements

- [ ] User authentication and session management
- [ ] Job history and saved queries
- [ ] Export results to PDF/Word
- [ ] Advanced filtering and search
- [ ] Multi-user support with job queuing
- [ ] Real-time collaboration features
- [ ] Mobile app version

## License

Same as the main D4BL AI Agent project.

