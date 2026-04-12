"use client";

import { type FormEvent, useCallback, useEffect, useRef, useState } from "react";

declare global {
  interface Window {
    google?: {
      accounts: {
        id: {
          initialize: (config: { client_id: string; callback: (response: { credential: string }) => void; auto_select?: boolean; itp_support?: boolean }) => void;
          renderButton: (parent: HTMLElement, options: { theme?: string; size?: string; width?: number; text?: string; shape?: string; logo_alignment?: string; type?: string }) => void;
          prompt: () => void;
        };
      };
    };
  }
}

function resolveApiBase() {
  const configured = process.env.NEXT_PUBLIC_API_BASE_URL?.trim();
  if (configured?.startsWith("/")) {
    return configured;
  }
  if (typeof window !== "undefined") {
    if (configured) {
      try {
        const parsed = new URL(configured);
        if (parsed.hostname === "localhost" || parsed.hostname === "127.0.0.1") {
          return `${window.location.protocol}//${window.location.hostname}:${parsed.port || "8000"}`;
        }
      } catch {
        return configured;
      }
      return configured;
    }
    return "/backend";
  }
  return configured ?? "/backend";
}
const TOKEN_KEY = "flightcomp-platform-token";
const REFRESH_TOKEN_KEY = "flightcomp-platform-refresh-token";
const SESSION_COOKIE = "flightcomp_session";

function setSessionCookie() {
  document.cookie = `${SESSION_COOKIE}=1; Path=/; Max-Age=31536000; SameSite=Lax`;
}

async function readApiError(response: Response, fallback: string) {
  try {
    const payload = (await response.json()) as { detail?: string };
    if (payload.detail === "Invalid credentials") {
      return "That email/username or password didn't match. Check your credentials and try again.";
    }
    if (payload.detail?.trim()) {
      return payload.detail;
    }
  } catch {
    try {
      const text = await response.text();
      if (text.trim()) {
        return text;
      }
    } catch {
      return fallback;
    }
  }
  return fallback;
}

export default function LoginPage() {
  const [destination, setDestination] = useState("/dashboard");
  const [authMode, setAuthMode] = useState<"login" | "register">("login");
  const [showLoginPassword, setShowLoginPassword] = useState(false);
  const [showRegisterPassword, setShowRegisterPassword] = useState(false);
  const [forgotMode, setForgotMode] = useState(false);
  const [forgotEmail, setForgotEmail] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [loginForm, setLoginForm] = useState({ username: "", password: "" });
  const [registerForm, setRegisterForm] = useState({
    first_name: "",
    last_name: "",
    email: "",
    password: "",
    account_role: "pilot",
  });

  const googleButtonRef = useRef<HTMLDivElement>(null);
  const [googleClientId, setGoogleClientId] = useState<string | null | undefined>(undefined);
  const [googleSdkReady, setGoogleSdkReady] = useState(typeof window !== "undefined" && !!window.google);

  useEffect(() => {
    const next = new URLSearchParams(window.location.search).get("next");
    if (next) {
      setDestination(next);
    }
  }, []);

  const handleGoogleResponse = useCallback(async (response: { credential: string }) => {
    setMessage("");
    setError("");
    setIsSubmitting(true);
    try {
      const res = await fetch(`${resolveApiBase()}/api/auth/google`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ credential: response.credential }),
      });
      if (!res.ok) {
        throw new Error(await readApiError(res, "Google sign-in failed. Please try again."));
      }
      const payload = (await res.json()) as { access_token: string; refresh_token?: string; user: { full_name: string } };
      window.localStorage.setItem(TOKEN_KEY, payload.access_token);
      if (payload.refresh_token) window.localStorage.setItem(REFRESH_TOKEN_KEY, payload.refresh_token);
      setSessionCookie();
      setMessage(`Signed in as ${payload.user.full_name}. Opening your dashboard...`);
      window.location.replace(destination);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Google sign-in failed");
    } finally {
      setIsSubmitting(false);
    }
  }, [destination]);

  // Fetch Google Client ID from backend and initialize Google Sign-In
  useEffect(() => {
    fetch(`${resolveApiBase()}/api/auth/google-client-id`)
      .then((res) => res.ok ? res.json() : null)
      .then((data) => {
        if (data?.client_id) {
          setGoogleClientId(data.client_id);
        } else {
          setGoogleClientId(null);
        }
      })
      .catch(() => { setGoogleClientId(null); });
  }, []);

  useEffect(() => {
    if (window.google) { setGoogleSdkReady(true); return; }
    // Find or create the Google Identity Services script
    let script = document.querySelector<HTMLScriptElement>('script[src*="accounts.google.com/gsi/client"]');
    if (!script) {
      script = document.createElement("script");
      script.src = "https://accounts.google.com/gsi/client";
      script.async = true;
      document.head.appendChild(script);
    }
    const onLoad = () => setGoogleSdkReady(true);
    script.addEventListener("load", onLoad);
    return () => script.removeEventListener("load", onLoad);
  }, []);

  useEffect(() => {
    if (!googleClientId || !googleSdkReady || !window.google || !googleButtonRef.current) return;
    window.google.accounts.id.initialize({
      client_id: googleClientId,
      callback: handleGoogleResponse,
      auto_select: false,
      itp_support: true,
    });
    window.google.accounts.id.renderButton(googleButtonRef.current, {
      theme: "outline",
      size: "large",
      width: 320,
      text: "continue_with",
      shape: "rectangular",
      logo_alignment: "left",
      type: "standard",
    });
  }, [googleClientId, googleSdkReady, handleGoogleResponse]);

  async function handleLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage("");
    setError("");
    setIsSubmitting(true);
    try {
      const response = await fetch(`${resolveApiBase()}/api/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          username: loginForm.username.trim().toLowerCase(),
          password: loginForm.password,
        }),
      });
      if (!response.ok) {
        throw new Error(await readApiError(response, "Sign in failed. Please try again."));
      }
      const payload = (await response.json()) as { access_token: string; refresh_token?: string };
      window.localStorage.setItem(TOKEN_KEY, payload.access_token);
      if (payload.refresh_token) window.localStorage.setItem(REFRESH_TOKEN_KEY, payload.refresh_token);
      setSessionCookie();
      setMessage("Sign-in successful. Opening your dashboard...");
      window.location.replace(destination);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Sign in failed");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleRegister(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage("");
    setError("");
    setIsSubmitting(true);
    try {
      const response = await fetch(`${resolveApiBase()}/api/auth/register`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          first_name: registerForm.first_name,
          last_name: registerForm.last_name,
          email: registerForm.email,
          password: registerForm.password,
          account_role: registerForm.account_role,
        }),
      });
      if (!response.ok) throw new Error(await readApiError(response, "Registration failed. Please try again."));
      const payload = (await response.json()) as { access_token: string; refresh_token?: string; user: { full_name: string } };
      window.localStorage.setItem(TOKEN_KEY, payload.access_token);
      if (payload.refresh_token) window.localStorage.setItem(REFRESH_TOKEN_KEY, payload.refresh_token);
      setSessionCookie();
      setMessage(`Created account for ${payload.user.full_name}. Redirecting...`);
      window.location.replace(destination);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Registration failed");
    } finally {
      setIsSubmitting(false);
    }
  }

  function handleForgotPassword(event?: FormEvent<HTMLFormElement>) {
    event?.preventDefault();
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
          <h1>Welcome to Aervyx mission control.</h1>
          <p>Run events, publish tasks, manage pilots, score flights, and keep competition operations moving from one shared portal.</p>
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
            <p>{authMode === "login" ? "Use your portal credentials to enter the dashboard." : "Choose whether this account is for a pilot or an event organizer. Your email becomes your login."}</p>
          </div>

          <div className="aervyx-auth-panel-body">
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
              <>
                <form className="aervyx-auth-form" onSubmit={handleLogin}>
                  <label className="stack compact">
                    <span>Username / email</span>
                    <div className="aervyx-auth-input-shell">
                      <input
                        value={loginForm.username}
                        onChange={(event) => setLoginForm({ ...loginForm, username: event.target.value })}
                        placeholder="pilot@example.com"
                        autoComplete="username"
                        required
                      />
                    </div>
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
                    </div>
                    <div className="aervyx-auth-inline-actions">
                      <button type="button" className="aervyx-auth-helper-button" onClick={() => setForgotMode((value) => !value)}>
                        {forgotMode ? "Hide password help" : "Forgot password?"}
                      </button>
                      <button type="button" className="aervyx-password-toggle" onClick={() => setShowLoginPassword((value) => !value)}>
                        {showLoginPassword ? "Hide" : "Show"}
                      </button>
                    </div>
                  </label>
                  {forgotMode ? (
                    <div className="aervyx-auth-forgot-card">
                      <strong>Password recovery</strong>
                      <p>Reset emails are not automated yet. Enter your email and we'll show a safe placeholder confirmation.</p>
                      <div className="aervyx-auth-forgot-form">
                        <div className="aervyx-auth-input-shell">
                          <input type="email" value={forgotEmail} onChange={(event) => setForgotEmail(event.target.value)} placeholder="pilot@example.com" autoComplete="email" required />
                        </div>
                        <button type="button" className="aervyx-auth-helper-submit" onClick={() => handleForgotPassword()}>Continue</button>
                      </div>
                    </div>
                  ) : null}
                  <button type="submit" className="aervyx-auth-submit" disabled={isSubmitting}>
                    {isSubmitting ? "Signing in..." : "Sign in"}
                  </button>
                </form>
              </>
            ) : (
              <form className="aervyx-auth-form" onSubmit={handleRegister}>
                <label className="stack compact">
                  <span>Account role</span>
                  <select value={registerForm.account_role} onChange={(event) => setRegisterForm({ ...registerForm, account_role: event.target.value })}>
                    <option value="pilot">Pilot</option>
                    <option value="organizer">Event organizer</option>
                  </select>
                </label>
                <div className="inline-grid">
                  <label className="stack compact">
                    <span>First name</span>
                    <div className="aervyx-auth-input-shell">
                      <input value={registerForm.first_name} onChange={(event) => setRegisterForm({ ...registerForm, first_name: event.target.value })} autoComplete="given-name" required />
                    </div>
                  </label>
                  <label className="stack compact">
                    <span>Last name</span>
                    <div className="aervyx-auth-input-shell">
                      <input value={registerForm.last_name} onChange={(event) => setRegisterForm({ ...registerForm, last_name: event.target.value })} autoComplete="family-name" required />
                    </div>
                  </label>
                </div>
                <label className="stack compact">
                  <span>Username / email</span>
                  <div className="aervyx-auth-input-shell">
                    <input type="email" value={registerForm.email} onChange={(event) => setRegisterForm({ ...registerForm, email: event.target.value })} autoComplete="email" required />
                  </div>
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
                  </div>
                  <div className="aervyx-auth-inline-actions aervyx-auth-inline-actions-end">
                    <button type="button" className="aervyx-password-toggle" onClick={() => setShowRegisterPassword((value) => !value)}>
                      {showRegisterPassword ? "Hide" : "Show"}
                    </button>
                  </div>
                </label>
                <button type="submit" className="aervyx-auth-submit" disabled={isSubmitting}>
                  {isSubmitting ? "Creating account..." : "Create account"}
                </button>
              </form>
            )}
            {googleClientId !== null ? (
              <>
                <div className="aervyx-auth-divider"><span>or</span></div>
                <div ref={googleButtonRef} className="aervyx-auth-google-btn">
                  {(!googleClientId || !googleSdkReady) && (
                    <div className="aervyx-auth-google-skeleton">
                      <svg width="18" height="18" viewBox="0 0 48 48" aria-hidden="true">
                        <path fill="currentColor" opacity=".5" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"/>
                        <path fill="currentColor" opacity=".4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"/>
                        <path fill="currentColor" opacity=".3" d="M10.53 28.59a14.5 14.5 0 0 1 0-9.18l-7.98-6.19a24.09 24.09 0 0 0 0 21.56l7.98-6.19z"/>
                        <path fill="currentColor" opacity=".45" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"/>
                      </svg>
                      <span>Continue with Google</span>
                    </div>
                  )}
                </div>
                <p className="aervyx-auth-google-hint">
                  {authMode === "login"
                    ? "New to Aervyx? Google sign-in will create your account automatically."
                    : "We'll create your Aervyx account using your Google profile."}
                </p>
              </>
            ) : null}
            <a href="/" className="aervyx-auth-secondary-link">Back to Aervyx landing page</a>
          </div>
        </div>
      </section>
    </main>
  );
}
