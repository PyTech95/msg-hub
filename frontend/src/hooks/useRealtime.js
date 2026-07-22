import { useEffect, useRef, useState, useCallback } from "react";

/**
 * Realtime WebSocket hook for tenant-scoped events.
 * Auto-reconnects with exponential backoff. Sends 'ping' every 30s.
 * Events:
 *   { type: "connected" }
 *   { type: "message_event", message_id, event_type, channel, contact_id, ... }
 *   { type: "inbound_message", channel, contact_id, message_id, body, ... }
 *   { type: "wallet_debit", balance_paise, amount_paise, low_balance }
 *   { type: "keepalive"|"pong" }
 *
 * Usage:
 *   const { lastEvent, connected } = useRealtime((evt) => {
 *     if (evt.type === "message_event") { ... }
 *   });
 */
export function useRealtime(onEvent) {
  const [connected, setConnected] = useState(false);
  const [lastEvent, setLastEvent] = useState(null);
  const wsRef = useRef(null);
  const backoffRef = useRef(1000);
  const stopRef = useRef(false);
  const cbRef = useRef(onEvent);
  useEffect(() => { cbRef.current = onEvent; }, [onEvent]);

  const connect = useCallback(() => {
    if (stopRef.current) return;
    // SECURITY: auth is via the httpOnly `access_token` cookie sent by the browser
    // during the WebSocket handshake — no token in the URL query.
    const backend = process.env.REACT_APP_BACKEND_URL || window.location.origin;
    const wsUrl = backend.replace(/^http/, "ws") + `/api/ws`;
    let ws;
    try {
      ws = new WebSocket(wsUrl);
    } catch (_e) {
      scheduleReconnect(); return;
    }
    wsRef.current = ws;

    let pingTimer = null;
    ws.onopen = () => {
      setConnected(true);
      backoffRef.current = 1000;
      pingTimer = setInterval(() => { try { ws.send("ping"); } catch (_) { /* socket closed */ } }, 30000);
    };
    ws.onmessage = (ev) => {
      try {
        const evt = JSON.parse(ev.data);
        setLastEvent(evt);
        cbRef.current?.(evt);
      } catch (_) { /* ignore malformed */ }
    };
    ws.onerror = () => { /* onclose fires next */ };
    ws.onclose = (evt) => {
      setConnected(false);
      if (pingTimer) clearInterval(pingTimer);
      // Don't reconnect on clean close (1000) or auth failure (4401)
      if (evt?.code === 1000 || evt?.code === 4401) return;
      scheduleReconnect();
    };
  }, []);

  const scheduleReconnect = useCallback(() => {
    if (stopRef.current) return;
    const delay = Math.min(backoffRef.current, 30000);
    backoffRef.current = Math.min(delay * 2, 30000);
    setTimeout(connect, delay);
  }, [connect]);

  useEffect(() => {
    stopRef.current = false;
    connect();
    return () => {
      stopRef.current = true;
      try { wsRef.current?.close(); } catch (_) { /* already closed */ }
    };
  }, [connect]);

  return { connected, lastEvent };
}
