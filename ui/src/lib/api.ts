// ui/src/lib/api.ts
const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

function getAccessToken() {
  if (typeof window === "undefined") return "";
  return localStorage.getItem("access_token") || "";
}

function getRefreshToken() {
  if (typeof window === "undefined") return "";
  return localStorage.getItem("refresh_token") || "";
}

function setTokens(access: string, refresh?: string) {
  localStorage.setItem("access_token", access);
  if (refresh) localStorage.setItem("refresh_token", refresh);
}

export function clearTokens() {
  if (typeof window === "undefined") return;
  localStorage.removeItem("access_token");
  localStorage.removeItem("refresh_token");
}

async function refreshAccessToken(): Promise<string> {
  const refresh_token = getRefreshToken();
  if (!refresh_token) throw new Error("Session expired. Please login again.");

  const res = await fetch(`${API_BASE}/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token }),
  });

  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    clearTokens();
    throw new Error(data?.detail || "Refresh failed. Please login again.");
  }

  setTokens(data.access_token, data.refresh_token);
  return data.access_token;
}

async function authFetch(url: string, init: RequestInit = {}, retry = true) {
  const token = getAccessToken();

  const res = await fetch(url, {
    ...init,
    headers: {
      ...(init.headers || {}),
      Authorization: `Bearer ${token}`,
    },
  });

  // retry once if token expired/unauthorized
  if ((res.status === 401 || res.status === 403) && retry) {
    await refreshAccessToken();
    return authFetch(url, init, false);
  }

  const text = await res.text();
  const data = text ? JSON.parse(text) : {};

  if (!res.ok) {
    throw new Error(data?.detail || `Request failed: ${res.status}`);
  }
  return data;
}

/** AUTH */
export async function register(email: string, password: string) {
  const res = await fetch(`${API_BASE}/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });

  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data?.detail || "Register failed");

  // ✅ store tokens
  if (data?.access_token) setTokens(data.access_token, data.refresh_token);
  return data;
}

export async function login(email: string, password: string) {
  const res = await fetch(`${API_BASE}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });

  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data?.detail || "Login failed");

  // ✅ store tokens
  if (data?.access_token) setTokens(data.access_token, data.refresh_token);
  return data;
}

/** DATA */
export async function apiConversations() {
  return authFetch(`${API_BASE}/conversations`);
}

export async function apiMessages(conversationId: string) {
  return authFetch(`${API_BASE}/conversations/${conversationId}/messages`);
}

export async function apiUploadPdf(file: File) {
  const fd = new FormData();
  fd.append("file", file);

  // IMPORTANT: don't set Content-Type for multipart, browser will do it
  return authFetch(`${API_BASE}/files/upload`, { method: "POST", body: fd });
}