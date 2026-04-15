const WS_URL = "ws://127.0.0.1:8765/ws";
const MAX_BACKOFF = 30000;

export function createWSConnection(onMessage) {
  let ws = null;
  let backoff = 1000;
  let closed = false;

  function connect() {
    if (closed) return;

    ws = new WebSocket(WS_URL);

    ws.onopen = () => {
      console.log("[ws] connected");
      backoff = 1000;
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        onMessage(data);
      } catch {
        console.warn("[ws] non-JSON message:", event.data);
      }
    };

    ws.onclose = () => {
      if (closed) return;
      console.log(`[ws] disconnected, reconnecting in ${backoff}ms`);
      setTimeout(connect, backoff);
      backoff = Math.min(backoff * 2, MAX_BACKOFF);
    };

    ws.onerror = (err) => {
      console.error("[ws] error:", err);
      ws.close();
    };
  }

  connect();

  return {
    close() {
      closed = true;
      if (ws) ws.close();
    },
  };
}
