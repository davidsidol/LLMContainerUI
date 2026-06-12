# LLM Container UI

A Docker Compose chat app with a React UI and FastAPI backend. It supports:

- `demo`: local canned responses so the UI works immediately
- `openai`: OpenAI Chat Completions API
- `xai`: xAI Chat Completions API
- `claude`: Anthropic Claude Messages API
- `ollama`: a local Ollama server

## Run

```sh
docker compose up --build -d
```

Open http://localhost:3000.

## OpenAI

Create `.env` from `.env.example`, then set:

```sh
LLM_PROVIDER=openai
OPENAI_API_KEY=your_key_here
OPENAI_MODEL=gpt-4.1-mini
```

Restart:

```sh
docker compose up --build -d
```

## xAI

Create `.env` from `.env.example`, then set:

```sh
LLM_PROVIDER=xai
XAI_API_KEY=your_key_here
XAI_MODEL=latest
```

Restart:

```sh
docker compose up --build -d
```

## Claude

Create `.env` from `.env.example`, then set:

```sh
LLM_PROVIDER=claude
CLAUDE_API_KEY=your_key_here
CLAUDE_MODEL=claude-3-5-sonnet-latest
```

Restart:

```sh
docker compose up --build -d
```

## Ollama

Run Ollama on your Mac, pull a model, then set:

```sh
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://host.docker.internal:11434
OLLAMA_MODEL=llama3.2
```

Restart:

```sh
docker compose up --build -d
```
