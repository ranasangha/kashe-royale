/* ============================================================
   PokerStack API client + session storage
   ============================================================ */

const SESSION_KEY = "pokerstack.session.v1";

export class ApiError extends Error {
  constructor(message, status = 0) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request(path, { method = "GET", body = null, code = null, token = null } = {}) {
  const headers = {};
  if (body !== null) headers["Content-Type"] = "application/json";
  if (token) headers["X-Table-Token"] = token;
  let url = path;
  if (code) {
    const separator = path.includes("?") ? "&" : "?";
    url = `${path}${separator}code=${encodeURIComponent(code)}`;
  }
  let response;
  try {
    response = await fetch(url, {
      method,
      headers,
      body: body !== null ? JSON.stringify(body) : null,
      cache: "no-store",
    });
  } catch (error) {
    throw new ApiError("Cannot reach the table server. Is run.py still running?", 0);
  }
  let payload;
  try {
    payload = await response.json();
  } catch (error) {
    throw new ApiError("The server sent an unreadable response.", response.status);
  }
  if (!response.ok || !payload.ok) {
    throw new ApiError(payload.error || `Request failed (${response.status}).`, response.status);
  }
  return payload.data;
}

export const api = {
  health: () => request("/api/health"),
  openTables: () => request("/api/tables"),
  createTable: (payload) => request("/api/create", { method: "POST", body: payload }),
  joinTable: (payload) => request("/api/join", { method: "POST", body: payload }),
  createPractice: (payload) => request("/api/practice", { method: "POST", body: payload }),
  state: (code, token) => request("/api/state", { code, token }),
  act: (code, token, action, amount = null, seat = null) =>
    request("/api/act", { method: "POST", body: { code, token, action, amount, seat }, token }),
  start: (code, token) => request("/api/start", { method: "POST", body: { code }, token }),
  nextHand: (code, token) => request("/api/next", { method: "POST", body: { code }, token }),
  sit: (code, token, out) => request("/api/sit", { method: "POST", body: { code, out }, token }),
  rebuy: (code, token) => request("/api/rebuy", { method: "POST", body: { code }, token }),
  leave: (code, token) => request("/api/leave", { method: "POST", body: { code }, token }),
  updateSettings: (code, token, settings) =>
    request("/api/settings", { method: "POST", body: { code, settings }, token }),
  undo: (code, token) => request("/api/undo", { method: "POST", body: { code }, token }),
  peek: (code, token) => request("/api/peek", { method: "POST", body: { code }, token }),
};

export function saveSession(session) {
  try {
    const payload = {
      code: session.code,
      token: session.token,
      practice: Boolean(session.practice),
      name: session.name || "",
      savedAt: Date.now(),
    };
    localStorage.setItem(SESSION_KEY, JSON.stringify(payload));
    if (session.code) {
      localStorage.setItem(`pokerstack.token.${session.code}`, session.token);
    }
  } catch (error) {
    /* storage can be unavailable in private modes; the game still works */
  }
}

export function loadSession() {
  try {
    const raw = localStorage.getItem(SESSION_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed || !parsed.code || !parsed.token) return null;
    return parsed;
  } catch (error) {
    return null;
  }
}

export function tokenForRoom(code) {
  try {
    return localStorage.getItem(`pokerstack.token.${code}`) || null;
  } catch (error) {
    return null;
  }
}

export function clearSession() {
  try {
    const raw = localStorage.getItem(SESSION_KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      if (parsed && parsed.code) {
        localStorage.removeItem(`pokerstack.token.${parsed.code}`);
      }
    }
    localStorage.removeItem(SESSION_KEY);
  } catch (error) {
    /* ignore */
  }
}

export function storeRoomToken(code, token) {
  try {
    localStorage.setItem(`pokerstack.token.${code}`, token);
  } catch (error) {
    /* ignore */
  }
}

export function removeRoomToken(code) {
  try {
    localStorage.removeItem(`pokerstack.token.${code}`);
  } catch (error) {
    /* ignore */
  }
}

export function roomFromUrl() {
  try {
    const params = new URLSearchParams(window.location.search);
    return (params.get("room") || "").trim().toUpperCase();
  } catch (error) {
    return "";
  }
}

export function inviteLink(code) {
  const base = `${window.location.origin}${window.location.pathname}`;
  return `${base}?room=${encodeURIComponent(code)}`;
}

export async function copyText(text) {
  if (navigator.clipboard && navigator.clipboard.writeText) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch (error) {
      /* fall through */
    }
  }
  try {
    const area = document.createElement("textarea");
    area.value = text;
    area.style.position = "fixed";
    area.style.opacity = "0";
    document.body.appendChild(area);
    area.select();
    const ok = document.execCommand("copy");
    document.body.removeChild(area);
    return ok;
  } catch (error) {
    return false;
  }
}
