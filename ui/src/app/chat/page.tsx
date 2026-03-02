"use client";

import { useEffect, useRef, useState } from "react";
import { connectWS } from "@/lib/ws";
import { apiConversations, apiMessages, apiUploadPdf } from "@/lib/api";

export default function ChatPage() {
  const token = typeof window !== "undefined" ? localStorage.getItem("token") || "" : "";
  const wsRef = useRef<WebSocket | null>(null);

  const [conversations, setConversations] = useState<any[]>([]);
  const [selectedConversation, setSelectedConversation] = useState<string | null>(null);
  const [messages, setMessages] = useState<any[]>([]);
  const [input, setInput] = useState("");
  const [stream, setStream] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>("");

  const loadConversations = async () => {
    const data = await apiConversations(token);
    setConversations(data.conversations || []);
  };

  const loadMessages = async (conversationId: string) => {
    const data = await apiMessages(token, conversationId);
    setMessages(data.messages || []);
  };

  useEffect(() => {
    if (!token) return;

    loadConversations();

    const socket = connectWS(token, {
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
      onClose: () => {
        setError("WebSocket disconnected");
      },
    });

    wsRef.current = socket;

    return () => socket.close();
  }, [token]);

  useEffect(() => {
    if (selectedConversation) loadMessages(selectedConversation);
  }, [selectedConversation]);

  const sendChat = () => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
    if (!input.trim()) return;

    setBusy(true);
    setError("");
    wsRef.current.send(
      JSON.stringify({
        action: "chat",
        job_id: "chat1",
        conversation_id: selectedConversation,
        message: input,
      })
    );
    setInput("");
  };

  const uploadPdf = async (file: File) => {
    setBusy(true);
    setError("");
    try {
      await apiUploadPdf(token, file);
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

      {/* ...rest of your UI unchanged... */}
    </div>
  );
}