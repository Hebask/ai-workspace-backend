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

export function connectWS(token: string, handlers: WSHandlers) {
  const ws = new WebSocket(WS_URL);
  let pingTimer: any = null;

  ws.onopen = () => {
    ws.send(JSON.stringify({ action: "auth", token }));
    // keep-alive every 25s (works even if server ignores it)
    pingTimer = setInterval(() => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ action: "ping" }));
      }
    }, 25_000);
  };

  ws.onmessage = (ev) => {
    try {
      handlers.onMessage(JSON.parse(ev.data));
    } catch {
      // ignore
    }
  };

  ws.onerror = (e) => {
    handlers.onError?.(e);
  };

  ws.onclose = () => {
    if (pingTimer) clearInterval(pingTimer);
    handlers.onClose?.();
  };

  return ws;
}