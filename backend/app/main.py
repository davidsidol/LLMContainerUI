import os
import time
from datetime import UTC, datetime
from json import JSONDecodeError
from uuid import UUID
from typing import Literal

import httpx
import psycopg
from psycopg.rows import dict_row
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field


Role = Literal["system", "user", "assistant"]
Provider = Literal["demo", "openai", "xai", "claude", "ollama"]


class ChatMessage(BaseModel):
    role: Role
    content: str = Field(min_length=1, max_length=20_000)


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1, max_length=100)
    provider: Provider | None = None
    model: str | None = Field(default=None, max_length=100)
    conversationId: UUID | None = None


class ChatResponse(BaseModel):
    provider: Provider
    model: str
    conversationId: UUID
    message: ChatMessage


class ConversationSummary(BaseModel):
    id: UUID
    title: str
    provider: Provider | None
    model: str | None
    updatedAt: datetime
    createdAt: datetime


class ConversationDetail(ConversationSummary):
    messages: list[ChatMessage]


def env_list(name: str, default: str) -> list[str]:
    return [value.strip() for value in os.getenv(name, default).split(",") if value.strip()]


app = FastAPI(title="LLM Container UI API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=env_list("CORS_ORIGINS", "http://localhost:3000"),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/config")
async def config() -> dict[str, str]:
    provider = os.getenv("LLM_PROVIDER", "demo")
    return {
        "provider": provider,
        "openaiModel": os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
        "xaiModel": os.getenv("XAI_MODEL", "grok-4.3"),
        "claudeModel": os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6"),
        "ollamaModel": os.getenv("OLLAMA_MODEL", "llama3.2"),
    }


@app.get("/api/conversations", response_model=list[ConversationSummary])
async def conversations() -> list[ConversationSummary]:
    with db_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, title, provider, model, updated_at, created_at
            FROM conversations
            ORDER BY updated_at DESC
            LIMIT 100
            """
        ).fetchall()
    return [conversation_summary(row) for row in rows]


@app.get("/api/conversations/{conversation_id}", response_model=ConversationDetail)
async def conversation(conversation_id: UUID) -> ConversationDetail:
    with db_connection() as conn:
        conversation_row = conn.execute(
            """
            SELECT id, title, provider, model, updated_at, created_at
            FROM conversations
            WHERE id = %s
            """,
            (conversation_id,),
        ).fetchone()
        if not conversation_row:
            raise HTTPException(status_code=404, detail="Conversation not found.")

        message_rows = conn.execute(
            """
            SELECT role, content
            FROM messages
            WHERE conversation_id = %s
            ORDER BY created_at ASC, id ASC
            """,
            (conversation_id,),
        ).fetchall()

    return ConversationDetail(
        **conversation_summary(conversation_row).model_dump(),
        messages=[ChatMessage(role=row["role"], content=row["content"]) for row in message_rows],
    )


@app.delete("/api/conversations/{conversation_id}")
async def delete_conversation(conversation_id: UUID) -> dict[str, str]:
    with db_connection() as conn:
        result = conn.execute("DELETE FROM conversations WHERE id = %s", (conversation_id,))
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Conversation not found.")
        conn.commit()
    return {"status": "deleted"}


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    provider = request.provider or os.getenv("LLM_PROVIDER", "demo")
    conversation_id = ensure_conversation(request, provider)
    latest_user = latest_user_message(request)
    if latest_user:
        save_message(conversation_id, "user", latest_user.content, provider, request.model)

    if provider == "openai":
        response = await openai_chat(request)
    if provider == "xai":
        response = await xai_chat(request)
    if provider == "claude":
        response = await claude_chat(request)
    if provider == "ollama":
        response = await ollama_chat(request)
    if provider == "demo":
        response = demo_chat(request)
    if provider not in ("openai", "xai", "claude", "ollama", "demo"):
        raise HTTPException(status_code=400, detail=f"Unsupported provider: {provider}")

    response.conversationId = conversation_id
    save_message(
        conversation_id,
        "assistant",
        response.message.content,
        response.provider,
        response.model,
    )
    update_conversation_model(conversation_id, response.provider, response.model)
    return response


def demo_chat(request: ChatRequest) -> ChatResponse:
    latest_user = next(
        (message.content for message in reversed(request.messages) if message.role == "user"),
        "",
    )
    content = (
        "Demo mode is working. I received your message and the container stack is healthy.\n\n"
        f"You said: {latest_user}\n\n"
        "Set LLM_PROVIDER to openai, xai, claude, or ollama with the matching API settings "
        "to connect this UI to a real model."
    )
    return ChatResponse(
        provider="demo",
        model="local-demo",
        conversationId=request.conversationId or UUID(int=0),
        message=ChatMessage(role="assistant", content=content),
    )


async def openai_chat(request: ChatRequest) -> ChatResponse:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=400, detail="OPENAI_API_KEY is not set.")

    model = request.model or os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
    return await chat_completions_chat(
        provider="openai",
        url="https://api.openai.com/v1/chat/completions",
        api_key=api_key,
        model=model,
        request=request,
        timeout=60,
    )


async def xai_chat(request: ChatRequest) -> ChatResponse:
    api_key = os.getenv("XAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=400, detail="XAI_API_KEY is not set.")

    model = request.model or os.getenv("XAI_MODEL", "grok-4.3")
    return await chat_completions_chat(
        provider="xai",
        url="https://api.x.ai/v1/chat/completions",
        api_key=api_key,
        model=model,
        request=request,
        timeout=60,
    )


async def chat_completions_chat(
    *,
    provider: Provider,
    url: str,
    api_key: str,
    model: str,
    request: ChatRequest,
    timeout: int,
) -> ChatResponse:
    payload = {
        "model": model,
        "messages": [message.model_dump() for message in request.messages],
        "temperature": 0.7,
    }

    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            url,
            headers={"Authorization": f"Bearer {api_key}"},
            json=payload,
        )

    if response.status_code >= 400:
        raise_provider_error(response)

    data = parse_provider_json(response)
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise HTTPException(
            status_code=502,
            detail=f"{provider} returned an unexpected response shape.",
        ) from exc
    return ChatResponse(
        provider=provider,
        model=model,
        conversationId=request.conversationId or UUID(int=0),
        message=ChatMessage(role="assistant", content=content),
    )


async def claude_chat(request: ChatRequest) -> ChatResponse:
    api_key = os.getenv("CLAUDE_API_KEY")
    if not api_key:
        raise HTTPException(status_code=400, detail="CLAUDE_API_KEY is not set.")

    model = request.model or os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")
    system_messages = [message.content for message in request.messages if message.role == "system"]
    chat_messages = [
        message.model_dump()
        for message in request.messages
        if message.role in ("user", "assistant")
    ]
    payload = {
        "model": model,
        "max_tokens": 1024,
        "messages": chat_messages,
    }
    if system_messages:
        payload["system"] = "\n\n".join(system_messages)

    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json=payload,
        )

    if response.status_code >= 400:
        raise_provider_error(response)

    data = parse_provider_json(response)
    content = "".join(
        block.get("text", "")
        for block in data.get("content", [])
        if block.get("type") == "text"
    )
    return ChatResponse(
        provider="claude",
        model=model,
        conversationId=request.conversationId or UUID(int=0),
        message=ChatMessage(role="assistant", content=content),
    )


async def ollama_chat(request: ChatRequest) -> ChatResponse:
    base_url = os.getenv("OLLAMA_BASE_URL", "http://host.docker.internal:11434").rstrip("/")
    model = request.model or os.getenv("OLLAMA_MODEL", "llama3.2")
    payload = {
        "model": model,
        "messages": [message.model_dump() for message in request.messages],
        "stream": False,
    }

    async with httpx.AsyncClient(timeout=120) as client:
        try:
            response = await client.post(f"{base_url}/api/chat", json=payload)
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    if response.status_code >= 400:
        raise_provider_error(response)

    data = parse_provider_json(response)
    content = data.get("message", {}).get("content", "")
    return ChatResponse(
        provider="ollama",
        model=model,
        conversationId=request.conversationId or UUID(int=0),
        message=ChatMessage(role="assistant", content=content),
    )


def database_url() -> str:
    return os.getenv("DATABASE_URL", "postgresql://llm_chat:llm_chat_password@postgres:5432/llm_chat")


def db_connection() -> psycopg.Connection:
    return psycopg.connect(database_url(), row_factory=dict_row)


def init_db() -> None:
    last_error: Exception | None = None
    for _ in range(20):
        try:
            with db_connection() as conn:
                conn.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS conversations (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        title TEXT NOT NULL,
                        provider TEXT,
                        model TEXT,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS messages (
                        id BIGSERIAL PRIMARY KEY,
                        conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                        role TEXT NOT NULL CHECK (role IN ('system', 'user', 'assistant')),
                        provider TEXT,
                        model TEXT,
                        content TEXT NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_messages_conversation_created
                    ON messages (conversation_id, created_at, id)
                    """
                )
                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_conversations_updated
                    ON conversations (updated_at DESC)
                    """
                )
                conn.commit()
                return
        except psycopg.OperationalError as exc:
            last_error = exc
            time.sleep(1)
    raise RuntimeError("Database is not available.") from last_error


def ensure_conversation(request: ChatRequest, provider: Provider) -> UUID:
    if request.conversationId:
        with db_connection() as conn:
            row = conn.execute(
                "SELECT id FROM conversations WHERE id = %s",
                (request.conversationId,),
            ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Conversation not found.")
        return request.conversationId

    latest_user = latest_user_message(request)
    title = title_from_message(latest_user.content if latest_user else "New conversation")
    with db_connection() as conn:
        row = conn.execute(
            """
            INSERT INTO conversations (title, provider, model)
            VALUES (%s, %s, %s)
            RETURNING id
            """,
            (title, provider, request.model),
        ).fetchone()
        conn.commit()
    return row["id"]


def latest_user_message(request: ChatRequest) -> ChatMessage | None:
    return next((message for message in reversed(request.messages) if message.role == "user"), None)


def save_message(
    conversation_id: UUID,
    role: Role,
    content: str,
    provider: Provider | None,
    model: str | None,
) -> None:
    with db_connection() as conn:
        conn.execute(
            """
            INSERT INTO messages (conversation_id, role, provider, model, content)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (conversation_id, role, provider, model, content),
        )
        conn.execute(
            "UPDATE conversations SET updated_at = now() WHERE id = %s",
            (conversation_id,),
        )
        conn.commit()


def update_conversation_model(conversation_id: UUID, provider: Provider, model: str) -> None:
    with db_connection() as conn:
        conn.execute(
            """
            UPDATE conversations
            SET provider = %s, model = %s, updated_at = now()
            WHERE id = %s
            """,
            (provider, model, conversation_id),
        )
        conn.commit()


def conversation_summary(row: dict) -> ConversationSummary:
    return ConversationSummary(
        id=row["id"],
        title=row["title"],
        provider=row["provider"],
        model=row["model"],
        updatedAt=row["updated_at"],
        createdAt=row["created_at"],
    )


def title_from_message(content: str) -> str:
    normalized = " ".join(content.split())
    if not normalized:
        return "New conversation"
    return normalized[:57] + "..." if len(normalized) > 60 else normalized


def parse_provider_json(response: httpx.Response) -> dict:
    try:
        return response.json()
    except JSONDecodeError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Provider returned non-JSON response: {response.text[:500]}",
        ) from exc


def raise_provider_error(response: httpx.Response) -> None:
    try:
        payload = response.json()
    except JSONDecodeError:
        payload = response.text

    detail = payload
    if isinstance(payload, dict):
        detail = payload.get("error") or payload.get("detail") or payload

    raise HTTPException(status_code=response.status_code, detail=detail)
