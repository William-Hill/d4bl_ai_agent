# Prerequisites

This guide covers all prerequisites needed to run the D4BL Research and Analysis Tool.

## Required Software

### Docker and Docker Compose

**macOS:**
```bash
# Install Docker Desktop from https://www.docker.com/products/docker-desktop
# Or via Homebrew
brew install --cask docker
```

**Linux (Ubuntu/Debian):**
```bash
# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Install Docker Compose
sudo apt-get update
sudo apt-get install docker-compose-plugin
```

**Windows:**
- Download and install Docker Desktop from https://www.docker.com/products/docker-desktop

**Verify installation:**
```bash
docker --version
docker compose version
```

### Ollama

Ollama is required to run the Mistral LLM model locally.

1. **Install Ollama**:
   - Visit https://ollama.ai and download for your platform
   - Or use package managers:
     ```bash
     # macOS
     brew install ollama
     
     # Linux
     curl -fsSL https://ollama.ai/install.sh | sh
     ```

2. **Start Ollama service**:
   ```bash
   ollama serve
   ```

3. **Pull the Mistral model**:
   ```bash
   ollama pull mistral
   ```

4. **Verify Ollama is running**:
   ```bash
   curl http://localhost:11434/api/tags
   ```

## API Keys

### Firecrawl API Key

The tool uses Firecrawl for web research. You'll need an API key:

1. Sign up at https://firecrawl.dev
2. Get your API key from the dashboard
3. Add it to your `.env` file:
   ```bash
   FIRECRAWL_API_KEY=your_api_key_here
   ```

## Environment Variables

Create a `.env` file in the project root:

```bash
# Required
FIRECRAWL_API_KEY=your_firecrawl_api_key

# Optional (defaults shown)
OLLAMA_BASE_URL=http://localhost:11434
```

## Optional: Local Development Prerequisites

If you want to develop locally without Docker, you'll also need:

### Python 3.10-3.13

**Using pyenv (Recommended):**

1. **Install pyenv**:
   ```bash
   # macOS
   brew install pyenv
   
   # Linux
   curl https://pyenv.run | bash
   ```

2. **Add to shell**:
   ```bash
   # Add to ~/.zshrc or ~/.bashrc
   export PYENV_ROOT="$HOME/.pyenv"
   command -v pyenv >/dev/null || export PATH="$PYENV_ROOT/bin:$PATH"
   eval "$(pyenv init -)"
   ```

3. **Install Python 3.13.9**:
   ```bash
   pyenv install 3.13.9
   cd /path/to/d4bl_ai_agent
   pyenv local 3.13.9
   ```

**Alternative: Direct Installation**

- **macOS**: `brew install python@3.13`
- **Linux**: `sudo apt install python3.13 python3.13-venv python3.13-pip`
- **Windows**: Download from https://python.org/downloads

### Node.js 18+ (for Frontend Development)

**Using nvm (Recommended):**

```bash
# Install nvm
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.0/install.sh | bash

# Install Node.js
nvm install 18
nvm use 18
```

**Alternative: Direct Installation**

- Download from https://nodejs.org
- Or use package managers:
  ```bash
  # macOS
  brew install node
  
  # Linux
  sudo apt install nodejs npm
  ```

## Verification Checklist

Before running the application, verify:

- [ ] Docker and Docker Compose installed
- [ ] Ollama installed and running (`ollama serve`)
- [ ] Mistral model pulled (`ollama pull mistral`)
- [ ] Firecrawl API key obtained
- [ ] `.env` file created with required variables
- [ ] Ollama accessible at http://localhost:11434

## Next Steps

Once prerequisites are installed, proceed to the [Quick Start](../README.md#quick-start-docker-compose) in the main README.


