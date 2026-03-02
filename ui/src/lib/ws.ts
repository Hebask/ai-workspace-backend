// ui/src/lib/ws.ts
// Prefer explicit WS url, else derive it from NEXT_PUBLIC_API_BASE.
const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";
const WS_URL =
  process.env.NEXT_PUBLIC_WS_URL ||
  API_BASE.replace(/^http(s?):\/\//, "ws$1://") + "/ws";

type WSHandlers = {
  onMessage: (msg: any) => void;
  onClose?: () => void;
  onError?: (err: Event) => void;
};

type Tokens = { access_token: string; refresh_token?: string };

function getAccessToken() {
  if (typeof window === "undefined") return "";
  return localStorage.getItem("token") || localStorage.getItem("access_token") || "";
}

function getRefreshToken() {
  if (typeof window === "undefined") return "";
  return localStorage.getItem("refresh_token") || "";
}

function saveTokens(t: Tokens) {
  if (typeof window === "undefined") return;
  if (t.access_token) {
    // keep backward compat with your current UI key "token"
    localStorage.setItem("token", t.access_token);
    localStorage.setItem("access_token", t.access_token);
  }
  if (t.refresh_token) localStorage.setItem("refresh_token", t.refresh_token);
}

async function refreshAccessToken(): Promise<string> {
  const refresh_token = getRefreshToken();
  if (!refresh_token) throw new Error("Missing refresh_token in localStorage");

  const res = await fetch(`${API_BASE}/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token }),
  });

  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data?.detail || "Refresh failed");

  // backend may return only access_token, or both tokens
  saveTokens({
    access_token: data.access_token,
    refresh_token: data.refresh_token, // optional
  });

  return data.access_token;
}

function isTokenExpiredError(msg: any): boolean {
  const s = String(msg?.error || msg?.detail || msg?.message || "").toLowerCase();
  return (
    s.includes("expiredsignatureerror") ||
    (s.includes("signature") && s.includes("expired")) ||
    s.includes("token has expired") ||
    (s.includes("jwt") && s.includes("expired"))
  );
}

export function connectWS(initialToken: string, handlers: WSHandlers) {
  let ws: WebSocket | null = null;
  let pingTimer: any = null;

  // avoid multiple simultaneous refresh/reconnects
  let reconnecting = false;

  // queue sends while reconnecting
  const sendQueue: any[] = [];

  const doSend = (obj: any) => {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(obj));
    } else {
      sendQueue.push(obj);
    }
  };

  const flushQueue = () => {
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    while (sendQueue.length) {
      ws.send(JSON.stringify(sendQueue.shift()));
    }
  };

  const cleanup = () => {
    if (pingTimer) clearInterval(pingTimer);
    pingTimer = null;
    try {
      ws?.close();
    } catch {}
    ws = null;
  };

  const open = (tokenToUse: string) => {
    cleanup();
    ws = new WebSocket(WS_URL);

    ws.onopen = () => {
      doSend({ action: "auth", token: tokenToUse });

      // keep-alive every 25s (works even if server ignores it)
      pingTimer = setInterval(() => {
        if (ws && ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ action: "ping" }));
        }
      }, 25_000);

      flushQueue();
    };

    ws.onmessage = async (ev) => {
      let msg: any = null;
      try {
        msg = JSON.parse(ev.data);
      } catch {
        return;
      }

      // If server reports token expired over WS, refresh and reconnect
      if (!reconnecting && msg?.type === "error" && isTokenExpiredError(msg)) {
        reconnecting = true;
        try {
          const newAccess = await refreshAccessToken();
          open(newAccess);
        } catch (e: any) {
          cleanup();
          handlers.onMessage?.({
            type: "error",
            error: e?.message || "Token refresh failed",
          });
          handlers.onClose?.();
        } finally {
          reconnecting = false;
        }
        return;
      }

      handlers.onMessage(msg);
    };

    ws.onerror = (e) => handlers.onError?.(e);

    ws.onclose = () => {
      if (pingTimer) clearInterval(pingTimer);
      pingTimer = null;
      handlers.onClose?.();
    };
  };

  // start connection
  open(initialToken || getAccessToken());

  // return a small wrapper so your UI can keep using ws.send(...)
  return {
    raw: () => ws,
    close: () => cleanup(),
    sendJson: (obj: any) => doSend(obj),
  };
}