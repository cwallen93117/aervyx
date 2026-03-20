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
  const [showLoginPassword, setShowLoginPassword] = useState(false);
  const [showRegisterPassword, setShowRegisterPassword] = useState(false);
  const [forgotMode, setForgotMode] = useState(false);
  const [forgotEmail, setForgotEmail] = useState("");
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
      setMessage(`Created account for ${payload.user.full_name}. Redirecting...`);
      router.replace(destination);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Registration failed");
    }
  }

  function handleForgotPassword(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    if (!forgotEmail.trim()) {
      setError("Enter your email to continue.");
      return;
    }
    setMessage("Password recovery is not automated yet. We've recorded your email and the team can assist from the admin side.");
    setForgotMode(false);
    setForgotEmail("");
  }

  return (
    <main className="aervyx-auth-shell">
      <section className="aervyx-auth-hero">
        <div className="aervyx-auth-glow aervyx-auth-glow-cyan" />
        <div className="aervyx-auth-glow aervyx-auth-glow-purple" />
        <a href="/" className="aervyx-auth-brand">
          <span className="aervyx-auth-brand-mark">△</span>
          <span className="aervyx-auth-brand-wordmark">Aervyx.net</span>
        </a>
        <div className="aervyx-auth-copy">
          <span className="aervyx-auth-kicker">Competition portal</span>
          <h1>{authMode === "login" ? "Welcome back to mission control." : "Create your pilot portal."}</h1>
          <p>
            {authMode === "login"
              ? "Access live tasks, scoring, tracking, and operations from the same Aervyx workspace your meet director is using."
              : "Create a pilot account to upload flights, follow published tasks, and stay synced with scoring as the meet evolves."}
          </p>
        </div>
        <div className="aervyx-auth-feature-list">
          <div className="aervyx-auth-feature">
            <strong>Live ops</strong>
            <span>Published tasks, track status, and scores in one place.</span>
          </div>
          <div className="aervyx-auth-feature">
            <strong>Audit-safe uploads</strong>
            <span>Immutable IGC evidence with hashes and scoring traceability.</span>
          </div>
          <div className="aervyx-auth-feature">
            <strong>Community ready</strong>
            <span>Built for hang gliding and paragliding comps, clubs, and federations.</span>
          </div>
        </div>
      </section>

      <section className="aervyx-auth-panel-wrap">
        <div className="aervyx-auth-panel">
          <div className="aervyx-auth-panel-header">
            <span className="aervyx-auth-panel-eyebrow">{authMode === "login" ? "Secure sign in" : "New account"}</span>
            <h2>{authMode === "login" ? "Sign in to continue" : "Create your account"}</h2>
            <p>{authMode === "login" ? "Use your portal credentials to enter the dashboard." : "Your email becomes your login. You can join events after your account is created."}</p>
          </div>

          <div className="aervyx-auth-tabs">
            <button type="button" className={authMode === "login" ? "aervyx-auth-tab active" : "aervyx-auth-tab"} onClick={() => { setAuthMode("login"); setForgotMode(false); }}>
              Log in
            </button>
            <button type="button" className={authMode === "register" ? "aervyx-auth-tab active" : "aervyx-auth-tab"} onClick={() => { setAuthMode("register"); setForgotMode(false); }}>
              Create account
            </button>
          </div>

          {message ? <div className="aervyx-auth-banner success">{message}</div> : null}
          {error ? <div className="aervyx-auth-banner error">{error}</div> : null}

          {authMode === "login" ? (
            <form className="aervyx-auth-form" onSubmit={handleLogin}>
              <label className="stack compact">
                <span>Email / username</span>
                <input
                  value={loginForm.username}
                  onChange={(event) => setLoginForm({ ...loginForm, username: event.target.value })}
                  placeholder="pilot@example.com"
                  autoComplete="username"
                  required
                />
              </label>
              <label className="stack compact">
                <span>Password</span>
                <div className="aervyx-password-field">
                  <input
                    type={showLoginPassword ? "text" : "password"}
                    value={loginForm.password}
                    onChange={(event) => setLoginForm({ ...loginForm, password: event.target.value })}
                    placeholder="Enter your password"
                    autoComplete="current-password"
                    required
                  />
                  <button type="button" className="aervyx-password-toggle" onClick={() => setShowLoginPassword((value) => !value)}>
                    {showLoginPassword ? "Hide" : "Show"}
                  </button>
                </div>
              </label>
              <div className="aervyx-auth-inline-actions">
                <button type="button" className="aervyx-auth-helper-button" onClick={() => setForgotMode((value) => !value)}>
                  {forgotMode ? "Hide password help" : "Forgot password?"}
                </button>
              </div>
              {forgotMode ? (
                <div className="aervyx-auth-forgot-card">
                  <strong>Password recovery</strong>
                  <p>Reset emails are not automated yet. Enter your email and we'll show a safe placeholder confirmation.</p>
                  <form className="aervyx-auth-forgot-form" onSubmit={handleForgotPassword}>
                    <input type="email" value={forgotEmail} onChange={(event) => setForgotEmail(event.target.value)} placeholder="pilot@example.com" autoComplete="email" required />
                    <button type="submit" className="aervyx-auth-helper-submit">Continue</button>
                  </form>
                </div>
              ) : null}
              <button type="submit" className="aervyx-auth-submit">Sign in</button>
              <a href="/" className="aervyx-auth-secondary-link">Back to Aervyx landing page</a>
            </form>
          ) : (
            <form className="aervyx-auth-form" onSubmit={handleRegister}>
              <div className="inline-grid">
                <label className="stack compact">
                  <span>First name</span>
                  <input value={registerForm.first_name} onChange={(event) => setRegisterForm({ ...registerForm, first_name: event.target.value })} autoComplete="given-name" required />
                </label>
                <label className="stack compact">
                  <span>Last name</span>
                  <input value={registerForm.last_name} onChange={(event) => setRegisterForm({ ...registerForm, last_name: event.target.value })} autoComplete="family-name" required />
                </label>
              </div>
              <label className="stack compact">
                <span>Email</span>
                <input type="email" value={registerForm.email} onChange={(event) => setRegisterForm({ ...registerForm, email: event.target.value })} autoComplete="email" required />
              </label>
              <label className="stack compact">
                <span>Password</span>
                <div className="aervyx-password-field">
                  <input
                    type={showRegisterPassword ? "text" : "password"}
                    value={registerForm.password}
                    onChange={(event) => setRegisterForm({ ...registerForm, password: event.target.value })}
                    autoComplete="new-password"
                    required
                  />
                  <button type="button" className="aervyx-password-toggle" onClick={() => setShowRegisterPassword((value) => !value)}>
                    {showRegisterPassword ? "Hide" : "Show"}
                  </button>
                </div>
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
              <button type="submit" className="aervyx-auth-submit">Create account</button>
              <a href="/" className="aervyx-auth-secondary-link">Back to Aervyx landing page</a>
            </form>
          )}
        </div>
      </section>
    </main>
  );
}
