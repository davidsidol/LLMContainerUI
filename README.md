# LLM Container UI

A Docker Compose chat app with a React UI, FastAPI backend, and Postgres chat history. It supports:

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

Postgres runs as part of the Compose stack and stores conversations in the `postgres_data` Docker volume.

## Web Search

The UI has a Brave web search toggle that can add current web results to any provider. Add a Brave Search API key to `.env`:

```sh
BRAVE_API_KEY=your_key_here
BRAVE_SEARCH_COUNT=5
BRAVE_SEARCH_FRESHNESS=pw
```

Freshness can be `pd` for 24 hours, `pw` for 7 days, `pm` for 31 days, or empty for no date filter.

Restart:

```sh
docker compose up --build -d
```

## Back Up Chat History

```sh
docker compose exec -T postgres pg_dump -U llm_chat llm_chat > llm_chat_backup.sql
```

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
XAI_MODEL=grok-4.3
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
CLAUDE_MODEL=claude-sonnet-4-6
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
