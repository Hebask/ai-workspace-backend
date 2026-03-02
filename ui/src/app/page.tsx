"use client";

import { useState } from "react";
import { login, register } from "@/lib/api";
import { useRouter } from "next/navigation";

export default function Home() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [mode, setMode] = useState<"login" | "register">("login");
  const [err, setErr] = useState("");
  const router = useRouter();

  async function submit() {
    setErr("");
    try {
      if (mode === "login") await login(email, password);
      else await register(email, password);

      const access = localStorage.getItem("access_token") || "";
      if (!access) throw new Error("No access token saved. Check /auth response.");

      router.push("/chat");
    } catch (e: any) {
      setErr(String(e?.message || e));
    }
  }

  return (
    <main style={{ maxWidth: 420, margin: "40px auto", fontFamily: "sans-serif" }}>
      <h2>AI Workspace</h2>

      <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
        <button onClick={() => setMode("login")} disabled={mode === "login"}>
          Login
        </button>
        <button onClick={() => setMode("register")} disabled={mode === "register"}>
          Register
        </button>
      </div>

      <input
        placeholder="email"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        style={{ width: "100%", marginBottom: 8, padding: 8 }}
      />
      <input
        placeholder="password"
        type="password"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        style={{ width: "100%", marginBottom: 8, padding: 8 }}
      />

      <button onClick={submit} style={{ width: "100%", padding: 10 }}>
        {mode === "login" ? "Login" : "Register"}
      </button>

      {err && <p style={{ color: "crimson", marginTop: 12 }}>{err}</p>}
    </main>
  );
}