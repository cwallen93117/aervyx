"use client";

import { useCallback, useEffect, useState } from "react";
import type { UserEmailRecord } from "./types";

function resolveApiBase() {
  const configured = process.env.NEXT_PUBLIC_API_BASE_URL?.trim();
  if (configured?.startsWith("/")) return configured;
  if (typeof window !== "undefined") {
    if (configured) {
      try {
        const parsed = new URL(configured);
        if (parsed.hostname === "localhost" || parsed.hostname === "127.0.0.1") {
          return `${window.location.protocol}//${window.location.hostname}:${parsed.port || "8000"}`;
        }
      } catch { return configured; }
      return configured;
    }
    return "/backend";
  }
  return configured ?? "/backend";
}

async function apiFetch<T>(path: string, token: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers ?? {});
  headers.set("Authorization", `Bearer ${token}`);
  if (!(init.body instanceof FormData) && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  const response = await fetch(`${resolveApiBase()}${path}`, { ...init, headers, cache: "no-store" });
  if (!response.ok) {
    const text = await response.text().catch(() => "");
    throw new Error(text || `Request failed: ${response.status}`);
  }
  if (response.status === 204) return undefined as T;
  const text = await response.text();
  return (text ? JSON.parse(text) : undefined) as T;
}

export interface EmailsManagerProps {
  token: string;
}

export default function EmailsManager({ token }: EmailsManagerProps) {
  const [emails, setEmails] = useState<UserEmailRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [newEmail, setNewEmail] = useState("");
  const [adding, setAdding] = useState(false);
  const [feedback, setFeedback] = useState<{ type: "success" | "error"; text: string } | null>(null);

  const showFeedback = useCallback((type: "success" | "error", text: string) => {
    setFeedback({ type, text });
    setTimeout(() => setFeedback(null), 3000);
  }, []);

  const loadEmails = useCallback(async () => {
    try {
      const data = await apiFetch<UserEmailRecord[]>("/api/auth/emails", token);
      setEmails(data);
    } catch {
      showFeedback("error", "Failed to load emails");
    } finally {
      setLoading(false);
    }
  }, [token, showFeedback]);

  useEffect(() => { loadEmails(); }, [loadEmails]);

  async function addEmail() {
    const email = newEmail.trim().toLowerCase();
    if (!email || !email.includes("@")) return;
    setAdding(true);
    try {
      await apiFetch<UserEmailRecord>("/api/auth/emails", token, {
        method: "POST",
        body: JSON.stringify({ email }),
      });
      setNewEmail("");
      showFeedback("success", "Email added");
      loadEmails();
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to add email";
      // Try to parse API error detail
      try {
        const parsed = JSON.parse(msg);
        showFeedback("error", parsed.detail || msg);
      } catch {
        showFeedback("error", msg);
      }
    } finally {
      setAdding(false);
    }
  }

  async function removeEmail(emailId: number) {
    try {
      await apiFetch<void>(`/api/auth/emails/${emailId}`, token, { method: "DELETE" });
      showFeedback("success", "Email removed");
      loadEmails();
    } catch (err) {
      showFeedback("error", err instanceof Error ? err.message : "Failed to remove email");
    }
  }

  if (loading) return <p className="muted">Loading emails...</p>;

  return (
    <div className="stack">
      <p className="settings-description">
        Additional email addresses help match your account to pilot records imported by event organizers.
      </p>

      {feedback ? <div className={`status-chip ${feedback.type}`}>{feedback.text}</div> : null}

      <div className="buddy-create-row">
        <input
          className="buddy-create-input"
          type="email"
          value={newEmail}
          onChange={(e) => setNewEmail(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") addEmail(); }}
          placeholder="Add another email address"
        />
        <button type="button" onClick={addEmail} disabled={adding || !newEmail.trim()}>
          {adding ? "Adding..." : "Add email"}
        </button>
      </div>

      {emails.length === 0 ? (
        <p className="muted">No additional emails. Your primary email is used for pilot matching by default.</p>
      ) : (
        <ul className="buddy-member-list">
          {emails.map((email) => (
            <li key={email.id} className="buddy-member-row">
              <span className="buddy-member-name">{email.email}</span>
              <button
                type="button"
                className="ghost-button danger-text buddy-remove-btn"
                onClick={() => removeEmail(email.id)}
              >
                Remove
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
