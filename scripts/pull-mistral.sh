#!/bin/sh
# Wait for Ollama to be ready, then pull Mistral model

echo "Waiting for Ollama to be ready..."
until curl -f http://localhost:11434/api/tags > /dev/null 2>&1; do
  echo "Ollama not ready yet, waiting..."
  sleep 2
done

echo "Ollama is ready. Pulling Mistral model..."
ollama pull mistral

echo "Mistral model pulled successfully!"

