import React, { useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Bot,
  CheckCircle2,
  CircleAlert,
  Loader2,
  MessageSquare,
  MonitorCog,
  Plus,
  RefreshCw,
  Send,
  Sparkles,
  Trash2,
  User,
} from "lucide-react";
import "./styles.css";

const starterMessages = [
  {
    role: "assistant",
    content:
      "Hi. I am your containerized LLM chat UI. I am running in demo mode until you point the backend at OpenAI, xAI, Claude, or Ollama.",
  },
];

function App() {
  const [messages, setMessages] = useState(starterMessages);
  const [conversations, setConversations] = useState([]);
  const [conversationId, setConversationId] = useState(null);
  const [input, setInput] = useState("");
  const [provider, setProvider] = useState("demo");
  const [model, setModel] = useState("local-demo");
  const [config, setConfig] = useState(null);
  const [status, setStatus] = useState("checking");
  const [error, setError] = useState("");
  const [isSending, setIsSending] = useState(false);
  const endRef = useRef(null);

  useEffect(() => {
    loadConfig();
    loadConversations();
  }, []);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const providerModel = useMemo(() => {
    if (provider === "openai") return config?.openaiModel || "gpt-4.1-mini";
    if (provider === "xai") return config?.xaiModel || "grok-4.3";
    if (provider === "claude") return config?.claudeModel || "claude-sonnet-4-6";
    if (provider === "ollama") return config?.ollamaModel || "llama3.2";
    return "local-demo";
  }, [config, provider]);

  useEffect(() => {
    setModel(providerModel);
  }, [providerModel]);

  async function loadConfig() {
    setStatus("checking");
    setError("");
    try {
      const response = await fetch("/api/config");
      const data = await readApiResponse(response);
      setConfig(data);
      setProvider(data.provider || "demo");
      setStatus("online");
    } catch (err) {
      setStatus("offline");
      setError(err.message || "Could not reach the backend.");
    }
  }

  async function loadConversations() {
    try {
      const response = await fetch("/api/conversations");
      const data = await readApiResponse(response);
      setConversations(data);
    } catch (err) {
      setError(err.message || "Could not load chat history.");
    }
  }

  async function loadConversation(id) {
    setError("");
    try {
      const response = await fetch(`/api/conversations/${id}`);
      const data = await readApiResponse(response);
      setConversationId(data.id);
      setMessages(data.messages.length ? data.messages : starterMessages);
      if (data.provider) setProvider(data.provider);
      if (data.model) setModel(data.model);
      setStatus("online");
    } catch (err) {
      setStatus("offline");
      setError(err.message || "Could not load that conversation.");
    }
  }

  async function deleteConversation(id) {
    setError("");
    try {
      const response = await fetch(`/api/conversations/${id}`, { method: "DELETE" });
      await readApiResponse(response);
      if (conversationId === id) {
        startNewChat();
      }
      await loadConversations();
    } catch (err) {
      setError(err.message || "Could not delete that conversation.");
    }
  }

  async function sendMessage(event) {
    event.preventDefault();
    const trimmed = input.trim();
    if (!trimmed || isSending) return;

    const nextMessages = [...messages, { role: "user", content: trimmed }];
    setMessages(nextMessages);
    setInput("");
    setIsSending(true);
    setError("");

    try {
      const response = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          provider,
          model,
          conversationId,
          messages: nextMessages,
        }),
      });
      const data = await readApiResponse(response);
      setConversationId(data.conversationId);
      setMessages((current) => [...current, data.message]);
      setStatus("online");
      await loadConversations();
    } catch (err) {
      setError(err.message || "Something went wrong.");
      setStatus("offline");
      setMessages((current) => [
        ...current,
        {
          role: "assistant",
          content:
            "I could not complete that request. Check the provider settings and backend logs, then try again.",
        },
      ]);
    } finally {
      setIsSending(false);
    }
  }

  function clearChat() {
    startNewChat();
  }

  function startNewChat() {
    setConversationId(null);
    setMessages(starterMessages);
    setError("");
  }

  return (
    <main className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">
            <Sparkles size={24} />
          </div>
          <div>
            <h1>LLM Container UI</h1>
            <p>React + FastAPI + Docker Compose</p>
          </div>
        </div>

        <button className="primary-action" type="button" onClick={startNewChat}>
          <Plus size={17} />
          New chat
        </button>

        <section className="panel">
          <div className="panel-title">
            <MonitorCog size={18} />
            <span>Runtime</span>
          </div>

          <label className="field">
            <span>Provider</span>
            <select value={provider} onChange={(event) => setProvider(event.target.value)}>
              <option value="demo">Demo</option>
              <option value="openai">OpenAI</option>
              <option value="xai">xAI</option>
              <option value="claude">Claude</option>
              <option value="ollama">Ollama</option>
            </select>
          </label>

          <label className="field">
            <span>Model</span>
            <input value={model} onChange={(event) => setModel(event.target.value)} />
          </label>

          <div className={`status ${status}`}>
            {status === "online" ? <CheckCircle2 size={18} /> : <CircleAlert size={18} />}
            <span>{status === "online" ? "Backend online" : "Backend unavailable"}</span>
          </div>
        </section>

        <button className="secondary-button" type="button" onClick={loadConfig}>
          <RefreshCw size={17} />
          Refresh config
        </button>
        <button className="secondary-button" type="button" onClick={clearChat}>
          Clear chat
        </button>

        <section className="history-panel">
          <div className="panel-title">
            <MessageSquare size={18} />
            <span>History</span>
          </div>
          <div className="history-list">
            {conversations.length ? (
              conversations.map((conversation) => (
                <div
                  className={`history-item ${conversation.id === conversationId ? "active" : ""}`}
                  key={conversation.id}
                >
                  <button type="button" onClick={() => loadConversation(conversation.id)}>
                    <span>{conversation.title}</span>
                    <small>
                      {conversation.provider || "demo"}
                      {conversation.model ? ` · ${conversation.model}` : ""}
                    </small>
                  </button>
                  <button
                    aria-label={`Delete ${conversation.title}`}
                    className="icon-button"
                    type="button"
                    onClick={() => deleteConversation(conversation.id)}
                  >
                    <Trash2 size={15} />
                  </button>
                </div>
              ))
            ) : (
              <p className="empty-history">No saved chats yet.</p>
            )}
          </div>
        </section>
      </aside>

      <section className="chat">
        <header className="chat-header">
          <div>
            <p className="eyebrow">Active session</p>
            <h2>{provider.toUpperCase()} · {model}</h2>
          </div>
          <div className="message-count">{messages.length} messages</div>
        </header>

        {error ? (
          <div className="error-banner">
            <CircleAlert size={18} />
            <span>{error}</span>
          </div>
        ) : null}

        <div className="messages" aria-live="polite">
          {messages.map((message, index) => (
            <article className={`message ${message.role}`} key={`${message.role}-${index}`}>
              <div className="avatar">
                {message.role === "user" ? <User size={18} /> : <Bot size={18} />}
              </div>
              <div className="bubble">
                <span>{message.role === "user" ? "You" : "Assistant"}</span>
                <p>{message.content}</p>
              </div>
            </article>
          ))}
          {isSending ? (
            <article className="message assistant">
              <div className="avatar">
                <Bot size={18} />
              </div>
              <div className="bubble loading">
                <span>Assistant</span>
                <p><Loader2 className="spin" size={16} /> Thinking</p>
              </div>
            </article>
          ) : null}
          <div ref={endRef} />
        </div>

        <form className="composer" onSubmit={sendMessage}>
          <textarea
            value={input}
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                sendMessage(event);
              }
            }}
            placeholder="Send a message to the model"
            rows={2}
          />
          <button aria-label="Send message" type="submit" disabled={isSending || !input.trim()}>
            {isSending ? <Loader2 className="spin" size={20} /> : <Send size={20} />}
          </button>
        </form>
      </section>
    </main>
  );
}

async function readApiResponse(response) {
  const contentType = response.headers.get("content-type") || "";
  const payload = contentType.includes("application/json")
    ? await response.json()
    : await response.text();

  if (response.ok) {
    return payload;
  }

  if (typeof payload === "string") {
    throw new Error(payload || `Request failed with status ${response.status}.`);
  }

  if (typeof payload?.detail === "string") {
    throw new Error(payload.detail);
  }

  throw new Error(`Request failed with status ${response.status}.`);
}

createRoot(document.getElementById("root")).render(<App />);
