const API_BASE = process.env.NEXT_PUBLIC_API_BASE!;

export function getToken() {
  return typeof window !== "undefined" ? localStorage.getItem("token") : null;
}

export function setToken(token: string) {
  localStorage.setItem("token", token);
}

export function clearToken() {
  localStorage.removeItem("token");
}

export async function apiFetch(path: string, init: RequestInit = {}) {
  const token = getToken();
  const headers = new Headers(init.headers || {});

  // Only set JSON content-type if body is not FormData
  const isForm = typeof FormData !== "undefined" && init.body instanceof FormData;
  if (!isForm && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");

  if (token) headers.set("Authorization", `Bearer ${token}`);

  const res = await fetch(`${API_BASE}${path}`, { ...init, headers });
  if (!res.ok) {
    const txt = await res.text();
    throw new Error(txt || `HTTP ${res.status}`);
  }
  const ct = res.headers.get("content-type") || "";
  return ct.includes("application/json") ? res.json() : res.text();
}

export async function login(email: string, password: string) {
  const data: any = await apiFetch("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) });
  setToken(data.access_token);
  return data;
}

export async function register(email: string, password: string) {
  const data: any = await apiFetch("/auth/register", { method: "POST", body: JSON.stringify({ email, password }) });
  setToken(data.access_token);
  return data;
}

export async function me() {
  return apiFetch("/auth/me");
}

export async function listConversations() {
  return apiFetch("/conversations");
}

export async function getMessages(conversationId: string) {
  return apiFetch(`/conversations/${conversationId}/messages`);
}

export async function uploadPdf(file: File, conversationId?: string) {
  const form = new FormData();
  form.append("file", file);
  if (conversationId) form.append("conversation_id", conversationId);

  const token = getToken();
  const res = await fetch(`${API_BASE}/files/upload`, {
    method: "POST",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: form,
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function createCheckoutSession() {
  return apiFetch("/billing/create-checkout-session", { method: "POST" });
}

export async function createPortalSession() {
  return apiFetch("/billing/create-portal-session", { method: "POST" });
}