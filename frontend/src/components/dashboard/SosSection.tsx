"use client";
import { useCallback, useEffect, useMemo, useState } from "react";
import { SectionCard } from "../SectionCard";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type SosStatus = "active" | "acknowledged" | "resolved";

type SosAlert = {
  id: string;
  pilot_id: number | null;
  pilot_name: string;
  lat: number;
  lon: number;
  alt: number | null;
  message: string | null;
  timestamp: string;
  created_at: string;
  status: SosStatus;
  acknowledged_at: string | null;
  resolved_at: string | null;
  resolved_by: string | null;
  notes: string | null;
};

type FilterValue = "all" | SosStatus;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function relativeTime(isoOrNull: string | null | undefined): string {
  if (!isoOrNull) return "\u2014";
  const diffMs = Date.now() - new Date(isoOrNull).getTime();
  if (diffMs < 0) return "just now";
  const seconds = Math.floor(diffMs / 1000);
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

function formatAbsoluteTime(isoOrNull: string | null | undefined): string {
  if (!isoOrNull) return "\u2014";
  return new Date(isoOrNull).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

const STATUS_LABEL: Record<SosStatus, string> = {
  active: "Active",
  acknowledged: "Acknowledged",
  resolved: "Resolved",
};

const STATUS_COLOR: Record<SosStatus, string> = {
  active: "#ef4444",
  acknowledged: "#f59e0b",
  resolved: "#22c55e",
};

const BORDER_COLOR: Record<SosStatus, string> = {
  active: "#ef4444",
  acknowledged: "#f59e0b",
  resolved: "#22c55e",
};

// ---------------------------------------------------------------------------
// Alert card
// ---------------------------------------------------------------------------

type AlertCardProps = {
  alert: SosAlert;
  onAcknowledge: (id: string) => Promise<void>;
  onResolve: (id: string) => Promise<void>;
  onDelete: (id: string) => Promise<void>;
  onSaveNote: (id: string, note: string) => Promise<void>;
};

function AlertCard({ alert, onAcknowledge, onResolve, onDelete, onSaveNote }: AlertCardProps) {
  const [showNoteInput, setShowNoteInput] = useState(false);
  const [noteText, setNoteText] = useState(alert.notes ?? "");
  const [savingNote, setSavingNote] = useState(false);
  const [actioning, setActioning] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const mapsUrl = `https://www.google.com/maps?q=${alert.lat},${alert.lon}`;

  async function handleAcknowledge() {
    setActioning(true);
    try { await onAcknowledge(alert.id); } finally { setActioning(false); }
  }

  async function handleResolve() {
    setActioning(true);
    try { await onResolve(alert.id); } finally { setActioning(false); }
  }

  async function handleDelete() {
    if (!confirmDelete) { setConfirmDelete(true); return; }
    setActioning(true);
    try { await onDelete(alert.id); } finally { setActioning(false); setConfirmDelete(false); }
  }

  async function handleSaveNote() {
    setSavingNote(true);
    try {
      await onSaveNote(alert.id, noteText);
      setShowNoteInput(false);
    } finally {
      setSavingNote(false);
    }
  }

  return (
    <div
      className="section-card"
      style={{
        borderLeft: `3px solid ${BORDER_COLOR[alert.status]}`,
        padding: "12px 16px",
        display: "flex",
        flexDirection: "column",
        gap: "6px",
      }}
    >
      {/* Header row */}
      <div style={{ display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap" }}>
        <strong style={{ fontSize: "1rem" }}>{alert.pilot_name}</strong>
        <span
          style={{
            fontSize: "0.75rem",
            fontWeight: 600,
            padding: "2px 8px",
            borderRadius: "9999px",
            backgroundColor: `${STATUS_COLOR[alert.status]}22`,
            color: STATUS_COLOR[alert.status],
            border: `1px solid ${STATUS_COLOR[alert.status]}55`,
          }}
        >
          {STATUS_LABEL[alert.status]}
        </span>
        <span className="hint" style={{ marginLeft: "auto", whiteSpace: "nowrap" }}>
          {relativeTime(alert.timestamp)}
        </span>
      </div>

      {/* Location row */}
      <div style={{ fontSize: "0.875rem", display: "flex", gap: "10px", flexWrap: "wrap", alignItems: "center" }}>
        <span>
          Location: {alert.lat.toFixed(5)}, {alert.lon.toFixed(5)}
          {alert.alt != null && ` \u00b7 ${Math.round(alert.alt)}m`}
        </span>
        <a
          href={mapsUrl}
          target="_blank"
          rel="noopener noreferrer"
          style={{ color: "var(--accent, #3b82f6)", textDecoration: "underline", fontSize: "0.8rem" }}
        >
          Open in Maps
        </a>
      </div>

      {/* Message row */}
      {alert.message && (
        <div style={{ fontSize: "0.9375rem", fontStyle: "italic", color: "var(--fg, inherit)" }}>
          {alert.message}
        </div>
      )}

      {/* Notes row */}
      {alert.notes && !showNoteInput && (
        <div className="hint" style={{ fontSize: "0.8125rem" }}>
          Note: {alert.notes}
        </div>
      )}

      {/* Inline note editor */}
      {showNoteInput && (
        <div className="form-block" style={{ gap: "6px" }}>
          <textarea
            value={noteText}
            onChange={(e) => setNoteText(e.target.value)}
            rows={2}
            style={{ width: "100%", resize: "vertical", fontSize: "0.875rem" }}
            placeholder="Add admin note..."
          />
          <div className="button-row">
            <button
              type="button"
              className="ghost-button"
              onClick={handleSaveNote}
              disabled={savingNote}
              style={{ fontSize: "0.8125rem" }}
            >
              {savingNote ? "Saving..." : "Save note"}
            </button>
            <button
              type="button"
              className="ghost-button"
              onClick={() => { setShowNoteInput(false); setNoteText(alert.notes ?? ""); }}
              style={{ fontSize: "0.8125rem" }}
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Action row */}
      <div className="button-row" style={{ marginTop: "4px", flexWrap: "wrap" }}>
        {alert.status === "active" && (
          <button
            type="button"
            className="ghost-button"
            onClick={handleAcknowledge}
            disabled={actioning}
            style={{ color: "#f59e0b", borderColor: "#f59e0b55", fontSize: "0.8125rem" }}
          >
            Acknowledge
          </button>
        )}
        {(alert.status === "active" || alert.status === "acknowledged") && (
          <button
            type="button"
            className="ghost-button"
            onClick={handleResolve}
            disabled={actioning}
            style={{ color: "#22c55e", borderColor: "#22c55e55", fontSize: "0.8125rem" }}
          >
            Resolve
          </button>
        )}
        {alert.status === "resolved" && (
          <span className="hint" style={{ fontSize: "0.8125rem", alignSelf: "center" }}>
            Resolved{alert.resolved_by ? ` by ${alert.resolved_by}` : ""}{alert.resolved_at ? ` at ${formatAbsoluteTime(alert.resolved_at)}` : ""}
          </span>
        )}
        {!showNoteInput && (
          <button
            type="button"
            className="ghost-button"
            onClick={() => { setShowNoteInput(true); setNoteText(alert.notes ?? ""); }}
            style={{ fontSize: "0.8125rem" }}
          >
            {alert.notes ? "Edit note" : "Add note"}
          </button>
        )}
        {alert.status === "resolved" && (
          <button
            type="button"
            className="ghost-button"
            onClick={handleDelete}
            disabled={actioning}
            style={{ color: confirmDelete ? "#ef4444" : undefined, fontSize: "0.8125rem" }}
          >
            {confirmDelete ? "Confirm delete" : "Delete"}
          </button>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function SosSection({ apiBase, token }: { apiBase: string; token: string | null }) {
  const [alerts, setAlerts] = useState<SosAlert[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<FilterValue>("all");

  const authHeaders = useMemo<Record<string, string>>(
    () => {
      const h: Record<string, string> = {};
      if (token) h["Authorization"] = `Bearer ${token}`;
      return h;
    },
    [token],
  );

  const fetchAlerts = useCallback(async () => {
    try {
      const res = await fetch(`${apiBase}/api/admin/sos?status=all&limit=50`, {
        headers: authHeaders,
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: SosAlert[] = await res.json();
      setAlerts(data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load SOS alerts");
    } finally {
      setLoading(false);
    }
  }, [apiBase, authHeaders]);

  useEffect(() => {
    void fetchAlerts();
    const interval = setInterval(() => { void fetchAlerts(); }, 10_000);
    return () => clearInterval(interval);
  }, [fetchAlerts]);

  async function patchAlert(id: string, body: { status?: "acknowledged" | "resolved"; notes?: string }) {
    const res = await fetch(`${apiBase}/api/admin/sos/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json", ...authHeaders },
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    await fetchAlerts();
  }

  async function deleteAlert(id: string) {
    const res = await fetch(`${apiBase}/api/admin/sos/${id}`, {
      method: "DELETE",
      headers: authHeaders,
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    await fetchAlerts();
  }

  const filtered = useMemo(
    () => (filter === "all" ? alerts : alerts.filter((a) => a.status === filter)),
    [alerts, filter],
  );

  const counts = useMemo(
    () => ({
      active: alerts.filter((a) => a.status === "active").length,
      acknowledged: alerts.filter((a) => a.status === "acknowledged").length,
      resolved: alerts.filter((a) => a.status === "resolved").length,
    }),
    [alerts],
  );

  const FILTERS: Array<{ value: FilterValue; label: string }> = [
    { value: "all", label: "All" },
    { value: "active", label: "Active" },
    { value: "acknowledged", label: "Acknowledged" },
    { value: "resolved", label: "Resolved" },
  ];

  return (
    <SectionCard>
      <div className="stack" style={{ gap: "16px" }}>
        {/* A) Filter bar */}
        <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
          {FILTERS.map((f) => (
            <button
              key={f.value}
              type="button"
              onClick={() => setFilter(f.value)}
              style={{
                padding: "4px 14px",
                borderRadius: "9999px",
                border: filter === f.value ? "1px solid var(--accent, #3b82f6)" : "1px solid var(--border, #d1d5db)",
                background: filter === f.value ? "var(--accent, #3b82f6)" : "transparent",
                color: filter === f.value ? "#fff" : "inherit",
                fontWeight: filter === f.value ? 700 : 400,
                cursor: "pointer",
                fontSize: "0.875rem",
              }}
            >
              {f.label}
            </button>
          ))}
        </div>

        {/* B) Summary stats */}
        <div style={{ display: "flex", gap: "12px", flexWrap: "wrap" }}>
          <div
            className="section-card"
            style={{
              flex: "1 1 0",
              minWidth: "120px",
              padding: "10px 14px",
              borderLeft: counts.active > 0 ? "3px solid #ef4444" : undefined,
            }}
          >
            <div className="hint" style={{ fontSize: "0.75rem" }}>Active Alerts</div>
            <strong style={{ fontSize: "1.25rem", color: counts.active > 0 ? "#ef4444" : "inherit" }}>
              {counts.active}
            </strong>
          </div>
          <div className="section-card" style={{ flex: "1 1 0", minWidth: "120px", padding: "10px 14px", borderLeft: "3px solid #f59e0b" }}>
            <div className="hint" style={{ fontSize: "0.75rem" }}>Acknowledged</div>
            <strong style={{ fontSize: "1.25rem", color: "#f59e0b" }}>{counts.acknowledged}</strong>
          </div>
          <div className="section-card" style={{ flex: "1 1 0", minWidth: "120px", padding: "10px 14px", borderLeft: "3px solid #22c55e" }}>
            <div className="hint" style={{ fontSize: "0.75rem" }}>Resolved</div>
            <strong style={{ fontSize: "1.25rem", color: "#22c55e" }}>{counts.resolved}</strong>
          </div>
        </div>

        {/* C) Alert list */}
        {loading ? (
          <div className="hint">Loading SOS alerts...</div>
        ) : error ? (
          <div className="hint" style={{ color: "#ef4444" }}>Error: {error}</div>
        ) : filtered.length === 0 ? (
          <div className="hint">
            {filter === "all"
              ? "No SOS alerts found."
              : `No ${filter} alerts found.`}
          </div>
        ) : (
          <div className="stack" style={{ gap: "10px" }}>
            {filtered.map((alert) => (
              <AlertCard
                key={alert.id}
                alert={alert}
                onAcknowledge={(id) => patchAlert(id, { status: "acknowledged" })}
                onResolve={(id) => patchAlert(id, { status: "resolved" })}
                onDelete={deleteAlert}
                onSaveNote={(id, notes) => patchAlert(id, { notes })}
              />
            ))}
          </div>
        )}
      </div>
    </SectionCard>
  );
}
