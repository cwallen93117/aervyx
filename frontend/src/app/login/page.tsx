"use client";

import { type FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const TOKEN_KEY = "flightcomp-platform-token";
const SESSION_COOKIE = "flightcomp_session";

function setSessionCookie() {
  document.cookie = `${SESSION_COOKIE}=1; Path=/; Max-Age=2592000; SameSite=Lax`;
}

export default function LoginPage() {
  const router = useRouter();
  const [destination, setDestination] = useState("/dashboard");
  const [authMode, setAuthMode] = useState<"login" | "register">("login");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [loginForm, setLoginForm] = useState({ username: "", password: "" });
  const [registerForm, setRegisterForm] = useState({
    first_name: "",
    last_name: "",
    email: "",
    password: "",
    competition_number: "",
    nation: "",
    civl_id: "",
  });

  useEffect(() => {
    const next = new URLSearchParams(window.location.search).get("next");
    if (next) {
      setDestination(next);
    }
  }, []);

  useEffect(() => {
    const token = window.localStorage.getItem(TOKEN_KEY);
    if (!token) return;
    setSessionCookie();
    router.replace(destination);
  }, [destination, router]);

  async function handleLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage("");
    setError("");
    try {
      const response = await fetch(`${API_BASE}/api/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: new URLSearchParams({
          username: loginForm.username,
          password: loginForm.password,
        }),
      });
      if (!response.ok) throw new Error("Sign in failed");
      const payload = (await response.json()) as { access_token: string };
      window.localStorage.setItem(TOKEN_KEY, payload.access_token);
      setSessionCookie();
      router.replace(destination);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Sign in failed");
    }
  }

  async function handleRegister(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage("");
    setError("");
    try {
      const response = await fetch(`${API_BASE}/api/auth/register`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          first_name: registerForm.first_name,
          last_name: registerForm.last_name,
          email: registerForm.email,
          password: registerForm.password,
          competition_number: registerForm.competition_number || null,
          nation: registerForm.nation || null,
          civl_id: registerForm.civl_id || null,
        }),
      });
      if (!response.ok) throw new Error(await response.text());
      const payload = (await response.json()) as { access_token: string; user: { full_name: string } };
      window.localStorage.setItem(TOKEN_KEY, payload.access_token);
      setSessionCookie();
      setMessage(`Created account for ${payload.user.full_name}. Redirecting…`);
      router.replace(destination);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Registration failed");
    }
  }

  return (
    <main className="shell">
      <section className="panel login-panel auth-panel">
        <div className="stack compact">
          <span>FlightComp Platform</span>
          <h1>Sign in to your competition portal</h1>
          <p className="hint">Use your existing portal account or create a new pilot login.</p>
        </div>
        <div className="tab-row">
          <button type="button" className={authMode === "login" ? "tab-button active" : "tab-button"} onClick={() => setAuthMode("login")}>Sign in</button>
          <button type="button" className={authMode === "register" ? "tab-button active" : "tab-button"} onClick={() => setAuthMode("register")}>Create account</button>
        </div>
        {message ? <div className="status-chip success">{message}</div> : null}
        {error ? <div className="status-chip error">{error}</div> : null}
        {authMode === "login" ? (
          <form className="stack" onSubmit={handleLogin}>
            <label className="stack compact">
              <span>Email / username</span>
              <input value={loginForm.username} onChange={(event) => setLoginForm({ ...loginForm, username: event.target.value })} required />
            </label>
            <label className="stack compact">
              <span>Password</span>
              <input type="password" value={loginForm.password} onChange={(event) => setLoginForm({ ...loginForm, password: event.target.value })} required />
            </label>
            <button type="submit">Sign in</button>
          </form>
        ) : (
          <form className="stack" onSubmit={handleRegister}>
            <div className="inline-grid">
              <label className="stack compact">
                <span>First name</span>
                <input value={registerForm.first_name} onChange={(event) => setRegisterForm({ ...registerForm, first_name: event.target.value })} required />
              </label>
              <label className="stack compact">
                <span>Last name</span>
                <input value={registerForm.last_name} onChange={(event) => setRegisterForm({ ...registerForm, last_name: event.target.value })} required />
              </label>
            </div>
            <label className="stack compact">
              <span>Email</span>
              <input type="email" value={registerForm.email} onChange={(event) => setRegisterForm({ ...registerForm, email: event.target.value })} required />
            </label>
            <label className="stack compact">
              <span>Password</span>
              <input type="password" value={registerForm.password} onChange={(event) => setRegisterForm({ ...registerForm, password: event.target.value })} required />
            </label>
            <div className="inline-grid">
              <label className="stack compact">
                <span>Competition number</span>
                <input value={registerForm.competition_number} onChange={(event) => setRegisterForm({ ...registerForm, competition_number: event.target.value })} />
              </label>
              <label className="stack compact">
                <span>Nation</span>
                <input value={registerForm.nation} onChange={(event) => setRegisterForm({ ...registerForm, nation: event.target.value })} />
              </label>
            </div>
            <label className="stack compact">
              <span>CIVL ID</span>
              <input value={registerForm.civl_id} onChange={(event) => setRegisterForm({ ...registerForm, civl_id: event.target.value })} />
            </label>
            <button type="submit">Create account</button>
          </form>
        )}
      </section>
    </main>
  );
}
