// ui/src/lib/api.ts
// Allow running without a .env.local by falling back to localhost.
const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

function setTokens(data: any) {
  const access = data?.access_token || data?.accessToken || "";
  const refresh = data?.refresh_token || data?.refreshToken || "";

  if (access) {
    localStorage.setItem("access_token", access);
    // backward compat
    localStorage.setItem("token", access);
  }
  if (refresh) localStorage.setItem("refresh_token", refresh);
}

export function getAccessToken() {
  return (
    (typeof window !== "undefined" && localStorage.getItem("access_token")) ||
    (typeof window !== "undefined" && localStorage.getItem("token")) ||
    ""
  );
}

export function clearTokens() {
  localStorage.removeItem("access_token");
  localStorage.removeItem("token");
  localStorage.removeItem("refresh_token");
}

async function refreshAccessToken(): Promise<string> {
  const refresh = localStorage.getItem("refresh_token") || "";
  if (!refresh) return "";

  const res = await fetch(`${API_BASE}/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refresh }),
  });

  const data = await res.json();
  if (!res.ok) throw new Error(data?.detail || "Refresh failed");

  // backend returns only access_token
  const access = data?.access_token || "";
  if (access) {
    localStorage.setItem("access_token", access);
    localStorage.setItem("token", access); // backward compat
  }
  return access;
}

async function authFetch(url: string, init: RequestInit = {}) {
  let token = getAccessToken();

  const headers: any = { ...(init.headers || {}) };
  if (token) headers.Authorization = `Bearer ${token}`;

  let res = await fetch(url, { ...init, headers });

  // If token expired, try refresh once
  if (res.status === 401) {
    try {
      token = await refreshAccessToken();
      if (token) {
        const headers2: any = { ...(init.headers || {}) };
        headers2.Authorization = `Bearer ${token}`;
        res = await fetch(url, { ...init, headers: headers2 });
      }
    } catch {
      // fallthrough
    }
  }

  return res;
}

export async function apiRegister(email: string, password: string) {
  const res = await fetch(`${API_BASE}/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data?.detail || "Register failed");
  setTokens(data);
  return data;
}

export async function apiLogin(email: string, password: string) {
  const res = await fetch(`${API_BASE}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data?.detail || "Login failed");
  setTokens(data);
  return data;
}

export async function apiConversations() {
  const res = await authFetch(`${API_BASE}/conversations`);
  const data = await res.json();
  if (!res.ok) throw new Error(data?.detail || "Failed to load conversations");
  return data;
}

export async function apiMessages(conversationId: string) {
  const res = await authFetch(`${API_BASE}/conversations/${conversationId}/messages`);
  const data = await res.json();
  if (!res.ok) throw new Error(data?.detail || "Failed to load messages");
  return data;
}

export async function apiUploadPdf(file: File) {
  const fd = new FormData();
  fd.append("file", file);

  const res = await authFetch(`${API_BASE}/files/upload`, {
    method: "POST",
    body: fd,
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data?.detail || "Upload failed");
  return data;
}

// Backward-compatible aliases expected by page.tsx
export const login = apiLogin;
export const register = apiRegister;