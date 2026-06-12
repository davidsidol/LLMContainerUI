import os
from json import JSONDecodeError
from typing import Literal

import httpx
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


class ChatResponse(BaseModel):
    provider: Provider
    model: str
    message: ChatMessage


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


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    provider = request.provider or os.getenv("LLM_PROVIDER", "demo")

    if provider == "openai":
        return await openai_chat(request)
    if provider == "xai":
        return await xai_chat(request)
    if provider == "claude":
        return await claude_chat(request)
    if provider == "ollama":
        return await ollama_chat(request)
    if provider == "demo":
        return demo_chat(request)

    raise HTTPException(status_code=400, detail=f"Unsupported provider: {provider}")


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
        message=ChatMessage(role="assistant", content=content),
    )


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
