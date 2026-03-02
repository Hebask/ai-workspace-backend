"use client";

import { useEffect, useRef, useState } from "react";
import { connectWS } from "@/lib/ws";
import { apiConversations, apiMessages, apiUploadPdf, getAccessToken } from "@/lib/api";

type WSClient = ReturnType<typeof connectWS>;

export default function ChatPage() {
  const wsRef = useRef<WSClient | null>(null);

  const [conversations, setConversations] = useState<any[]>([]);
  const [selectedConversation, setSelectedConversation] = useState<string | null>(null);
  const [messages, setMessages] = useState<any[]>([]);
  const [input, setInput] = useState("");
  const [stream, setStream] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>("");

  const loadConversations = async () => {
    const data = await apiConversations();
    setConversations(data.conversations || []);
  };

  const loadMessages = async (conversationId: string) => {
    const data = await apiMessages(conversationId);
    setMessages(data.messages || []);
  };

  useEffect(() => {
    const token = typeof window !== "undefined" ? getAccessToken() : "";
    if (!token) return;

    loadConversations().catch((e: any) => setError(e?.message || "Failed to load conversations"));

    const client = connectWS(token, {
      onMessage: (msg) => {
        if (msg.type === "conversation" && msg.conversation_id) {
          setSelectedConversation(msg.conversation_id);
          loadConversations();
          loadMessages(msg.conversation_id);
        }

        if (msg.type === "delta" && msg.delta) {
          setStream((prev) => prev + msg.delta);
        }

        if (msg.type === "result") {
          setBusy(false);
          setStream("");
          if (msg.conversation_id) {
            setSelectedConversation(msg.conversation_id);
            loadMessages(msg.conversation_id);
            loadConversations();
          }
        }

        if (msg.type === "error") {
          setBusy(false);
          setStream("");
          setError(msg.error || "Unknown error");
        }
      },
      onClose: () => setError("WebSocket disconnected"),
      onError: () => setError("WebSocket error"),
    });

    wsRef.current = client;

    return () => {
      try {
        client.close();
      } catch {}
      wsRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (selectedConversation) loadMessages(selectedConversation);
  }, [selectedConversation]);

  const sendChat = () => {
    const client = wsRef.current;
    const ws = client?.raw();
    if (!client || !ws || ws.readyState !== WebSocket.OPEN) return;
    if (!input.trim()) return;

    setBusy(true);
    setError("");

    client.sendJson({
      action: "chat",
      job_id: `chat_${Date.now()}`,
      conversation_id: selectedConversation,
      message: input,
    });

    setInput("");
  };

  const uploadPdf = async (file: File) => {
    setBusy(true);
    setError("");
    try {
      await apiUploadPdf(file);
      await loadConversations();
    } catch (e: any) {
      setError(e?.message || "Upload failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={{ padding: 24, fontFamily: "sans-serif" }}>
      <h1>Chat</h1>

      <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
        <label style={{ border: "1px solid #555", padding: "6px 10px", cursor: "pointer" }}>
          Upload PDF
          <input
            type="file"
            accept="application/pdf"
            style={{ display: "none" }}
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) uploadPdf(f);
            }}
          />
        </label>
      </div>

      {error && (
        <div style={{ color: "crimson", marginBottom: 12, whiteSpace: "pre-wrap" }}>
          {error}
        </div>
      )}

      <div style={{ display: "flex", gap: 16 }}>
        <div style={{ width: 260, border: "1px solid #333", padding: 10 }}>
          <div style={{ fontWeight: 700, marginBottom: 8 }}>Conversations</div>
          {conversations.map((c) => {
            const id = c._id || c.id;
            return (
              <div key={id}>
                <button
                  style={{
                    width: "100%",
                    textAlign: "left",
                    padding: 8,
                    marginBottom: 6,
                    background: id === selectedConversation ? "#222" : "transparent",
                    border: "1px solid #444",
                    color: "white",
                    cursor: "pointer",
                  }}
                  onClick={() => setSelectedConversation(id)}
                  disabled={busy}
                >
                  {c.title || "New chat"}
                </button>
              </div>
            );
          })}
        </div>

        <div style={{ flex: 1, border: "1px solid #333", padding: 10 }}>
          <div style={{ height: 320, overflow: "auto", border: "1px solid #444", padding: 10 }}>
            {messages.map((m, idx) => (
              <div key={m._id || idx} style={{ marginBottom: 10 }}>
                <b>{m.role}:</b> {m.content}
              </div>
            ))}
            {stream && (
              <div style={{ marginTop: 10 }}>
                <b>assistant:</b> {stream}
              </div>
            )}
          </div>

          <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Type a message..."
              style={{ flex: 1, padding: 10 }}
              disabled={busy}
              onKeyDown={(e) => {
                if (e.key === "Enter") sendChat();
              }}
            />
            <button onClick={sendChat} disabled={busy} style={{ padding: "10px 14px" }}>
              Send
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}