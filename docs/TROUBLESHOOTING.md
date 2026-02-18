# Troubleshooting Guide

Common issues and solutions for the D4BL Research and Analysis Tool.

## Docker Issues

### Port Already in Use

**Error**: `ports are not available: bind: address already in use`

**Solution**:
```bash
# Check what's using the port
lsof -i :3000  # Frontend
lsof -i :8000  # Backend

# Stop the process or change ports in docker-compose.yml
```

### Cannot Connect to Ollama

**Error**: `Connection refused` or `Cannot connect to Ollama`

**Solution**:
1. Verify Ollama is running:
   ```bash
   ollama serve
   ```

2. Test Ollama connectivity:
   ```bash
   curl http://localhost:11434/api/tags
   ```

3. Check Docker can reach host:
   ```bash
   # From inside container
   docker exec -it d4bl-api curl http://host.docker.internal:11434/api/tags
   ```

4. On Linux, you may need to use host IP instead:
   ```bash
   # Find host IP
   ip addr show docker0
   
   # Update docker-compose.yml
   extra_hosts:
     - "host.docker.internal:172.17.0.1"
   ```

### Model Not Found

**Error**: `model 'mistral' not found`

**Solution**:
```bash
# Pull the Mistral model
ollama pull mistral

# Verify it's available
ollama list
```

### Container Build Fails

**Error**: Build errors during `docker-compose up --build`

**Solution**:
1. Check Dockerfile syntax
2. Verify all files are present
3. Clear Docker cache:
   ```bash
   docker-compose build --no-cache
   ```
4. Check Docker logs:
   ```bash
   docker-compose logs d4bl-api
   docker-compose logs d4bl-frontend
   ```

## Web Interface Issues

### Frontend Not Loading

**Symptoms**: Blank page or connection errors

**Solution**:
1. Check frontend container is running:
   ```bash
   docker-compose ps
   ```

2. Check frontend logs:
   ```bash
   docker-compose logs d4bl-frontend
   ```

3. Verify backend is accessible:
   ```bash
   curl http://localhost:8000/api/health
   ```

4. Check browser console for errors

### WebSocket Connection Fails

**Symptoms**: No real-time updates, connection errors in console

**Solution**:
1. Verify backend is running on port 8000
2. Check WebSocket URL format:
   ```javascript
   // Should be: ws://localhost:8000/ws/{job_id}
   // NOT: ws://localhost:3000/ws/{job_id}
   ```

3. Check CORS settings in `api.py`
4. Verify firewall isn't blocking WebSocket connections
5. Check browser console for specific error messages

### No Live Logs Appearing

**Symptoms**: Progress updates work but no agent output

**Solution**:
1. Check backend logs for errors
2. Verify WebSocket is receiving log messages
3. Check browser console for WebSocket messages
4. Verify `LiveLogs` component is rendering

### Results Not Displaying

**Symptoms**: Job completes but results don't show

**Solution**:
1. Check browser console for errors
2. Verify WebSocket received `complete` message
3. Check results format in network tab
4. Verify `ResultsCard` component is rendering

## Backend Issues

### API Server Won't Start

**Error**: `ModuleNotFoundError` or import errors

**Solution**:
1. Verify virtual environment is activated
2. Check dependencies are installed:
   ```bash
   pip list | grep fastapi
   pip list | grep crewai
   ```

3. Reinstall dependencies:
   ```bash
   pip install -r requirements.txt
   ```

### CrewAI Initialization Fails

**Error**: `Failed to initialize crew` or LLM errors

**Solution**:
1. Verify Ollama is running and accessible
2. Check Mistral model is available:
   ```bash
   ollama list
   ```

3. Verify `OLLAMA_BASE_URL` in `.env`
4. Check backend logs for specific error

### Job Stuck in "Running" State

**Symptoms**: Job never completes

**Solution**:
1. Check backend logs for errors
2. Verify Ollama is responding:
   ```bash
   curl http://localhost:11434/api/generate -d '{"model": "mistral", "prompt": "test"}'
   ```

3. Check Firecrawl API key is valid
4. Restart containers:
   ```bash
   docker-compose restart
   ```

## Agent Issues

### Research Agent Fails

**Error**: Firecrawl errors or no research results

**Solution**:
1. Verify Firecrawl API key in `.env`
2. Check API key is valid:
   ```bash
   curl -H "Authorization: Bearer $FIRECRAWL_API_KEY" \
     https://api.firecrawl.dev/v0/scrape
   ```

3. Check Firecrawl service status
4. Review backend logs for specific errors

### LLM Timeout Errors

**Error**: `timeout` or `connection timeout`

**Solution**:
1. Check Ollama is running and responsive
2. Increase timeout in `crew.py`:
   ```python
   timeout=180.0  # Increase from 120.0
   ```

3. Check system resources (CPU, RAM)
4. Try a smaller model if available

### Poor Quality Results

**Symptoms**: Results are generic or off-topic

**Solution**:
1. Verify query is clear and specific
2. Check agent prompts in `config/agents.yaml`
3. Adjust temperature in `crew.py`:
   ```python
   temperature=0.3  # Lower = more focused
   ```

4. Review research sources for relevance

## Environment Issues

### Environment Variables Not Loading

**Symptoms**: API keys not found, default values used

**Solution**:
1. Verify `.env` file exists in project root
2. Check `.env` file format (no spaces around `=`)
3. Restart containers after changing `.env`:
   ```bash
   docker-compose down
   docker-compose up
   ```

4. For local development, ensure `.env` is loaded:
   ```python
   from dotenv import load_dotenv
   load_dotenv()
   ```

### Python Version Mismatch

**Error**: `Python version not supported`

**Solution**:
1. Check Python version:
   ```bash
   python --version
   ```

2. Use correct version (3.10-3.13):
   ```bash
   pyenv local 3.13.9
   ```

3. Recreate virtual environment:
   ```bash
   rm -rf .venv
   python3.13 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

## Performance Issues

### Slow Response Times

**Symptoms**: Jobs take very long to complete

**Solution**:
1. Check Ollama performance:
   ```bash
   # Monitor Ollama logs
   ollama serve
   ```

2. Check system resources (CPU, RAM, disk)
3. Consider using a faster model
4. Reduce research scope (fewer pages, shorter queries)

### High Memory Usage

**Symptoms**: System becomes slow, containers crash

**Solution**:
1. Monitor memory usage:
   ```bash
   docker stats
   ```

2. Reduce concurrent jobs
3. Increase Docker memory limits
4. Use smaller LLM models

## Getting Help

If you're still experiencing issues:

1. **Check Logs**:
   ```bash
   # Docker logs
   docker-compose logs -f
   
   # Backend logs (local)
   python run_ui.py
   
   # Frontend logs (local)
   cd ui-nextjs && npm run dev
   ```

2. **Verify Setup**:
   - Review [Prerequisites Guide](PREREQUISITES.md)
   - Check all services are running
   - Verify environment variables

3. **Search Issues**:
   - Check GitHub issues (if applicable)
   - Search error messages online
   - Review documentation

4. **Create Issue**:
   - Include error messages
   - Provide system information
   - Include relevant logs
   - Describe steps to reproduce

## Common Error Messages

### `Connection refused`
- Service not running
- Wrong port or host
- Firewall blocking connection

### `Module not found`
- Dependencies not installed
- Virtual environment not activated
- Wrong Python version

### `Permission denied`
- File permissions issue
- Docker permissions (Linux)
- Port requires sudo

### `Address already in use`
- Port already occupied
- Previous instance not stopped
- Change port in configuration

### `Timeout`
- Service not responding
- Network issues
- Resource constraints


