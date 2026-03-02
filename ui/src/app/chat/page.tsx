"use client";

import { useEffect, useMemo, useState } from "react";
import {
  clearToken,
  createCheckoutSession,
  createPortalSession,
  getMessages,
  getToken,
  listConversations,
  uploadPdf,
} from "@/lib/api";
import { connectWS } from "@/lib/ws";
import { useRouter } from "next/navigation";

export default function ChatPage() {
  const router = useRouter();
  const token = useMemo(() => getToken(), []);
  const [ws, setWs] = useState<WebSocket | null>(null);

  const [convs, setConvs] = useState<any[]>([]);
  const [conversationId, setConversationId] = useState<string | undefined>(undefined);

  const [messages, setMessages] = useState<any[]>([]);
  const [input, setInput] = useState("");
  const [stream, setStream] = useState("");
  const [busy, setBusy] = useState(false);
  const STRIPE_ENABLED = process.env.NEXT_PUBLIC_STRIPE_ENABLED === "true";

  useEffect(() => {
    if (!token) router.push("/");
  }, [token, router]);

  async function refreshConvs() {
    try {
      const data: any = await listConversations();
      setConvs(data.conversations || []);
    } catch {}
  }

  async function loadMessages(cid: string) {
    try {
      const data: any = await getMessages(cid);
      setMessages(data.messages || []);
    } catch {
      setMessages([]);
    }
  }

  useEffect(() => {
    refreshConvs();
  }, []);

  useEffect(() => {
    if (!token) return;

    const socket = connectWS(token, (msg) => {
      if (msg.type === "authed") return;

      if (msg.type === "conversation" && msg.conversation_id) {
        setConversationId(msg.conversation_id);
        refreshConvs();
      }

      if (msg.type === "started") {
        setBusy(true);
        setStream("");
      }

      if (msg.type === "delta") {
        setStream((s) => s + (msg.delta || ""));
      }

      if (msg.type === "result") {
        setBusy(false);

        if (msg.conversation_id) {
          setConversationId(msg.conversation_id);
          loadMessages(msg.conversation_id);
          refreshConvs();
        } else if (conversationId) {
          loadMessages(conversationId);
        }
      }

      if (msg.type === "error") {
        setBusy(false);
        alert(msg.error || "Error");
      }
    });

    setWs(socket);
    return () => socket.close();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  useEffect(() => {
    if (conversationId) loadMessages(conversationId);
  }, [conversationId]);

  function sendAssistant() {
    if (!ws) return;
    if (!input.trim()) return;

    setBusy(true);
    setStream("");

    ws.send(
      JSON.stringify({
        action: "assistant",
        job_id: "ui_assistant_1",
        message: input,
        conversation_id: conversationId,
      })
    );

    setInput("");
  }

  async function onUpload(e: any) {
    const file: File | undefined = e.target.files?.[0];
    if (!file) return;
    try {
      const res = await uploadPdf(file, conversationId);
      alert(`Uploaded: pages=${res.pages} chunks=${res.chunks}`);
    } catch (err: any) {
      alert(String(err?.message || err));
    } finally {
      e.target.value = "";
    }
  }

  async function subscribe() {
    const res: any = await createCheckoutSession();
    window.location.href = res.url;
  }

  async function portal() {
    const res: any = await createPortalSession();
    window.location.href = res.url;
  }

  function logout() {
    clearToken();
    router.push("/");
  }

  return (
    <main style={{ maxWidth: 1000, margin: "20px auto", fontFamily: "sans-serif" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h2>Chat</h2>
        <button onClick={logout}>Logout</button>
      </div>

      <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
        {STRIPE_ENABLED && (
        <>
            <button onClick={subscribe}>Subscribe Pro</button>
            <button onClick={portal}>Billing Portal</button>
        </>
        )}

        <label style={{ border: "1px solid #ccc", padding: "6px 10px", cursor: "pointer" }}>
          Upload PDF
          <input type="file" accept="application/pdf" onChange={onUpload} style={{ display: "none" }} />
        </label>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "280px 1fr", gap: 16 }}>
        <aside style={{ border: "1px solid #ddd", padding: 10 }}>
          <b>Conversations</b>
          <div style={{ marginTop: 8 }}>
            {convs.map((c) => (
              <div
                key={c._id}
                style={{
                  padding: 8,
                  cursor: "pointer",
                  background: conversationId === c._id ? "#f0f0f0" : "transparent",
                  borderRadius: 6,
                }}
                onClick={() => setConversationId(c._id)}
              >
                <div style={{ fontWeight: 600 }}>{c.title || "New chat"}</div>
                <div style={{ fontSize: 12, opacity: 0.7 }}>{c._id}</div>
              </div>
            ))}
          </div>
        </aside>

        <section style={{ border: "1px solid #ddd", padding: 10 }}>
          <div style={{ minHeight: 280 }}>
            {messages.map((m) => (
              <div key={m._id} style={{ marginBottom: 10 }}>
                <b>{m.role}:</b> <span style={{ whiteSpace: "pre-wrap" }}>{m.content}</span>
              </div>
            ))}

            {stream && (
              <div style={{ marginTop: 10 }}>
                <b>assistant:</b> <span style={{ whiteSpace: "pre-wrap" }}>{stream}</span>
              </div>
            )}
          </div>

          <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Type a message..."
              style={{ flex: 1, padding: 10 }}
              onKeyDown={(e) => {
                if (e.key === "Enter") sendAssistant();
              }}
              disabled={busy}
            />
            <button onClick={sendAssistant} disabled={busy}>
              Send
            </button>
          </div>

          {busy && <div style={{ marginTop: 8, opacity: 0.7 }}>Working...</div>}
        </section>
      </div>
    </main>
  );
}