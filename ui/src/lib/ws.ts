const WS_URL = process.env.NEXT_PUBLIC_WS_URL!;

export function connectWS(token: string, onMessage: (msg: any) => void) {
  const ws = new WebSocket(WS_URL);

  ws.onopen = () => {
    ws.send(JSON.stringify({ action: "auth", token }));
  };

  ws.onmessage = (ev) => {
    try {
      onMessage(JSON.parse(ev.data));
    } catch {
      // ignore
    }
  };

  return ws;
}