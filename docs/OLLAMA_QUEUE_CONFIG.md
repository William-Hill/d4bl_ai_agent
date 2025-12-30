# Ollama Request Queue Configuration

This document explains how to configure Ollama's request queue to manage load and prevent connection refused errors.

## Problem

When multiple agents in CrewAI make concurrent requests to Ollama, you may encounter "Connection refused" errors. This happens when Ollama's connection limits are exceeded or when the server is overwhelmed with too many simultaneous requests.

## Solution: Configure Ollama Server-Side Queue

Ollama has built-in request queue management that can be configured via environment variables. These settings control how Ollama handles incoming requests and manages its internal queue.

### Environment Variables

Set these environment variables **when starting Ollama** (not in your application):

#### `OLLAMA_MAX_QUEUE`
- **Description**: Maximum number of requests that can be queued when the server is busy
- **Default**: `512`
- **Recommendation**: Increase if you have many concurrent agents (e.g., `1024` or `2048`)

#### `OLLAMA_NUM_PARALLEL`
- **Description**: Maximum number of parallel requests each model can process simultaneously
- **Default**: Automatically selected based on available memory (typically 4 or 1)
- **Recommendation**: 
  - For CPU inference: `1` or `2`
  - For GPU inference: `2` to `4` (depending on GPU memory)
  - Lower values reduce load but increase latency

#### `OLLAMA_MAX_LOADED_MODELS`
- **Description**: Maximum number of models that can be loaded concurrently
- **Default**: 3 times the number of GPUs, or 3 for CPU inference
- **Recommendation**: Keep default unless you have specific memory constraints

## Configuration Examples

### macOS/Linux (Systemd Service)

Edit your Ollama service file (usually `/etc/systemd/system/ollama.service`):

```ini
[Service]
Environment="OLLAMA_MAX_QUEUE=1024"
Environment="OLLAMA_NUM_PARALLEL=2"
Environment="OLLAMA_MAX_LOADED_MODELS=3"
```

Then restart the service:
```bash
sudo systemctl daemon-reload
sudo systemctl restart ollama
```

### macOS (Homebrew)

If running Ollama via Homebrew, create a plist override:

```bash
# Create override directory
mkdir -p ~/Library/LaunchAgents

# Create plist file
cat > ~/Library/LaunchAgents/com.ollama.ollama.plist << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>EnvironmentVariables</key>
    <dict>
        <key>OLLAMA_MAX_QUEUE</key>
        <string>1024</string>
        <key>OLLAMA_NUM_PARALLEL</key>
        <string>2</string>
        <key>OLLAMA_MAX_LOADED_MODELS</key>
        <string>3</string>
    </dict>
</dict>
</plist>
EOF

# Load and restart
launchctl unload ~/Library/LaunchAgents/com.ollama.ollama.plist 2>/dev/null
launchctl load ~/Library/LaunchAgents/com.ollama.ollama.plist
```

### Manual Start

If starting Ollama manually:

```bash
export OLLAMA_MAX_QUEUE=1024
export OLLAMA_NUM_PARALLEL=2
export OLLAMA_MAX_LOADED_MODELS=3
ollama serve
```

### Docker

If running Ollama in Docker, add environment variables:

```yaml
services:
  ollama:
    image: ollama/ollama
    environment:
      - OLLAMA_MAX_QUEUE=1024
      - OLLAMA_NUM_PARALLEL=2
      - OLLAMA_MAX_LOADED_MODELS=3
```

## Client-Side Configuration

The application (CrewAI) is already configured with:
- **Timeout**: 180 seconds (3 minutes)
- **Retries**: 5 attempts
- **Connection handling**: Automatic retry with exponential backoff

These settings are in `src/d4bl/crew.py` and help handle temporary connection issues.

## Monitoring

To monitor Ollama's queue status, you can check:

1. **Ollama logs**: Check system logs for queue-related messages
2. **Connection errors**: Monitor your application logs for "Connection refused" errors
3. **Resource usage**: Monitor CPU, memory, and GPU usage during high load

## Troubleshooting

### Still Getting Connection Refused Errors?

1. **Increase `OLLAMA_MAX_QUEUE`**: Allow more requests to be queued
2. **Decrease `OLLAMA_NUM_PARALLEL`**: Reduce concurrent processing to prevent overload
3. **Check system resources**: Ensure Ollama has enough CPU/memory/GPU
4. **Reduce agent concurrency**: Consider using sequential processing instead of parallel
5. **Add delays**: Add small delays between agent tasks if needed

### Performance vs. Reliability Trade-off

- **Higher `OLLAMA_MAX_QUEUE`**: Better reliability, but may use more memory
- **Lower `OLLAMA_NUM_PARALLEL`**: More reliable, but slower processing
- **Higher `OLLAMA_NUM_PARALLEL`**: Faster, but may cause connection issues if resources are limited

## References

- [Ollama Documentation](https://github.com/ollama/ollama/blob/main/docs/faq.md)
- [Ollama Environment Variables](https://github.com/ollama/ollama/blob/main/docs/faq.md#environment-variables)


