"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { SectionCard } from "../SectionCard";
import type { PilotRecord, TaskRecord, User } from "./types";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type DriverTab = "assignments" | "pickup_status";

type DriverUser = {
  id: number;
  username: string;
  full_name: string;
  profile_type: string;
  pilot_id: number | null;
  role: string;
};

type DriverAssignmentRecord = {
  id: number;
  task_id: number;
  driver_user_id: number;
  driver_name: string;
  pilot_id: number;
  pilot_name: string;
};

type LandingRecord = {
  landing_id: number;
  pilot_id: number;
  pilot_name: string;
  landed_at: string | null;
  ready_at: string | null;
  lat: number | null;
  lon: number | null;
  alt: number | null;
  status: "landed" | "ready" | "picked_up" | "cancelled" | string;
  picked_up_at: string | null;
  driver_name?: string | null;
};

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface DriverDashboardProps {
  token: string;
  user: User | null;
  selectedEventId: number | null;
  tasks: TaskRecord[];
  pilots: PilotRecord[];
  isAdmin: boolean;
  canManagePlatform: boolean;
}

// ---------------------------------------------------------------------------
// API helper (self-contained, mirrors page.tsx pattern)
// ---------------------------------------------------------------------------

function resolveApiBase(): string {
  const configured = process.env.NEXT_PUBLIC_API_BASE_URL?.trim();
  if (configured?.startsWith("/")) return configured;
  if (typeof window !== "undefined") {
    if (configured) {
      try {
        const parsed = new URL(configured);
        if (parsed.hostname === "localhost" || parsed.hostname === "127.0.0.1") {
          return `${window.location.protocol}//${window.location.hostname}:${parsed.port || "8000"}`;
        }
      } catch {
        return configured ?? "/backend";
      }
      return configured;
    }
    return "/backend";
  }
  return configured ?? "/backend";
}

async function apiFetch<T>(path: string, token: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers ?? {});
  headers.set("Authorization", `Bearer ${token}`);
  if (!(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(`${resolveApiBase()}${path}`, { ...init, headers, cache: "no-store" });
  if (!response.ok) throw new Error((await response.text()) || `Request failed: ${response.status}`);
  if (response.status === 204) return undefined as T;
  const text = await response.text();
  return (text ? JSON.parse(text) : undefined) as T;
}

// ---------------------------------------------------------------------------
// Formatting helpers
// ---------------------------------------------------------------------------

function formatTime(value: string | null | undefined): string {
  if (!value) return "-";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleTimeString([], { hour: "numeric", minute: "2-digit", second: "2-digit" });
}

function formatCountdown(targetIso: string): string {
  const diff = new Date(targetIso).getTime() - Date.now();
  if (diff <= 0) return "now";
  const totalSeconds = Math.floor(diff / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  if (minutes > 0) return `${minutes}m ${seconds}s`;
  return `${seconds}s`;
}

// ---------------------------------------------------------------------------
// Status badge
// ---------------------------------------------------------------------------

type StatusConfig = { label: string; color: string };

function statusConfig(status: string): StatusConfig {
  switch (status) {
    case "landed":
      return { label: "Landed", color: "#d97706" };
    case "ready":
      return { label: "Ready", color: "#16a34a" };
    case "picked_up":
      return { label: "Picked Up", color: "#2563eb" };
    case "cancelled":
      return { label: "Cancelled", color: "#94a3b8" };
    default:
      return { label: status, color: "#94a3b8" };
  }
}

function StatusBadge({ status }: { status: string }) {
  const { label, color } = statusConfig(status);
  return (
    <span
      style={{
        display: "inline-block",
        padding: "2px 8px",
        borderRadius: "4px",
        fontSize: "0.75rem",
        fontWeight: 600,
        background: color + "20",
        color,
        whiteSpace: "nowrap",
      }}
    >
      {label}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Task selector (shared between tabs)
// ---------------------------------------------------------------------------

function TaskSelector({
  tasks,
  selectedTaskId,
  onChange,
}: {
  tasks: TaskRecord[];
  selectedTaskId: number | null;
  onChange: (id: number | null) => void;
}) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 20 }}>
      <label
        htmlFor="driver-task-select"
        style={{ fontWeight: 600, fontSize: "0.8125rem", color: "var(--ink-secondary)", whiteSpace: "nowrap" }}
      >
        Task
      </label>
      <select
        id="driver-task-select"
        value={selectedTaskId ?? ""}
        onChange={(e) => onChange(e.target.value ? Number(e.target.value) : null)}
        style={{ maxWidth: 320 }}
      >
        <option value="">Select a task…</option>
        {tasks.map((task) => (
          <option key={task.id} value={task.id}>
            {task.name}{task.task_date ? ` — ${task.task_date}` : ""}
          </option>
        ))}
      </select>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Tab 1: Driver Assignments
// ---------------------------------------------------------------------------

function DriverAssignmentsTab({
  token,
  tasks,
  pilots,
  selectedTaskId,
  onTaskChange,
}: {
  token: string;
  tasks: TaskRecord[];
  pilots: PilotRecord[];
  selectedTaskId: number | null;
  onTaskChange: (id: number | null) => void;
}) {
  const [driverUsers, setDriverUsers] = useState<DriverUser[]>([]);
  const [assignments, setAssignments] = useState<DriverAssignmentRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState<Record<number, boolean>>({});
  const [feedback, setFeedback] = useState<{ type: "success" | "error"; text: string } | null>(null);
  // Local edits: driverId -> Set of assigned pilot ids
  const [localAssignments, setLocalAssignments] = useState<Record<number, Set<number>>>({});

  // Fetch driver users once
  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    (async () => {
      try {
        const users = await apiFetch<DriverUser[]>("/api/admin/users", token);
        if (!cancelled) {
          setDriverUsers(users.filter((u) => u.profile_type === "driver"));
        }
      } catch {
        // fail silently — drivers list unavailable
      }
    })();
    return () => { cancelled = true; };
  }, [token]);

  // Fetch assignments when task changes
  useEffect(() => {
    if (!selectedTaskId) {
      setAssignments([]);
      setLocalAssignments({});
      return;
    }
    setLoading(true);
    setFeedback(null);
    let cancelled = false;
    (async () => {
      try {
        const data = await apiFetch<DriverAssignmentRecord[]>(
          `/api/admin/driver-assignments/${selectedTaskId}`,
          token,
        );
        if (cancelled) return;
        setAssignments(data);
        // Build local state from fetched data
        const local: Record<number, Set<number>> = {};
        for (const a of data) {
          if (!local[a.driver_user_id]) local[a.driver_user_id] = new Set();
          local[a.driver_user_id].add(a.pilot_id);
        }
        setLocalAssignments(local);
      } catch (err) {
        if (!cancelled) {
          setFeedback({ type: "error", text: err instanceof Error ? err.message : "Failed to load assignments" });
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [selectedTaskId, token]);

  function togglePilot(driverId: number, pilotId: number) {
    setLocalAssignments((prev) => {
      const updated = { ...prev };
      const current = new Set(prev[driverId] ?? []);
      if (current.has(pilotId)) {
        current.delete(pilotId);
      } else {
        current.add(pilotId);
      }
      updated[driverId] = current;
      return updated;
    });
  }

  async function saveDriver(driverId: number) {
    if (!selectedTaskId) return;
    setSaving((prev) => ({ ...prev, [driverId]: true }));
    setFeedback(null);
    try {
      const pilotIds = Array.from(localAssignments[driverId] ?? []);
      await apiFetch<unknown>(`/api/admin/driver-assignments/${selectedTaskId}`, token, {
        method: "PUT",
        body: JSON.stringify({ driver_user_id: driverId, pilot_ids: pilotIds }),
      });
      setFeedback({ type: "success", text: "Assignments saved." });
    } catch (err) {
      setFeedback({ type: "error", text: err instanceof Error ? err.message : "Save failed" });
    } finally {
      setSaving((prev) => ({ ...prev, [driverId]: false }));
    }
  }

  const assignedPilotIds = new Set(Object.values(localAssignments).flatMap((s) => Array.from(s)));

  const availablePilots = pilots.filter((p) => !assignedPilotIds.has(p.id));

  function pilotLabel(p: PilotRecord): string {
    const name = [p.first_name, p.last_name].filter(Boolean).join(" ") || "(Unknown)";
    return p.competition_number ? `#${p.competition_number} ${name}` : name;
  }

  if (!selectedTaskId) {
    return (
      <>
        <TaskSelector tasks={tasks} selectedTaskId={selectedTaskId} onChange={onTaskChange} />
        <p className="hint">Select a task above to manage driver assignments.</p>
      </>
    );
  }

  return (
    <>
      <TaskSelector tasks={tasks} selectedTaskId={selectedTaskId} onChange={onTaskChange} />

      {feedback && (
        <div
          style={{
            marginBottom: 16,
            padding: "10px 14px",
            borderRadius: "var(--r-md)",
            background: feedback.type === "success" ? "var(--success-soft)" : "var(--danger-soft)",
            color: feedback.type === "success" ? "var(--success)" : "var(--danger)",
            fontSize: "0.875rem",
            fontWeight: 500,
          }}
        >
          {feedback.text}
        </div>
      )}

      {loading ? (
        <p className="hint">Loading assignments…</p>
      ) : driverUsers.length === 0 ? (
        <p className="hint">No driver accounts found. Create users with profile type "driver" in Admin.</p>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
          {driverUsers.map((driver) => {
            const assignedSet = localAssignments[driver.id] ?? new Set<number>();
            const assignedPilots = pilots.filter((p) => assignedSet.has(p.id));
            return (
              <div
                key={driver.id}
                style={{
                  border: "1px solid var(--line)",
                  borderRadius: "var(--r-lg)",
                  overflow: "hidden",
                }}
              >
                {/* Driver header */}
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    padding: "10px 14px",
                    background: "linear-gradient(180deg, #f6f9fe 0%, #eef4fb 100%)",
                    borderBottom: "1px solid var(--line)",
                  }}
                >
                  <div>
                    <span style={{ fontWeight: 600, fontSize: "0.9rem", color: "var(--ink)" }}>
                      {driver.full_name || driver.username}
                    </span>
                    <span
                      style={{
                        marginLeft: 8,
                        fontSize: "0.75rem",
                        fontWeight: 600,
                        padding: "2px 8px",
                        borderRadius: 4,
                        background: "#0ea5e920",
                        color: "#0284c7",
                      }}
                    >
                      Driver
                    </span>
                  </div>
                  <button
                    onClick={() => void saveDriver(driver.id)}
                    disabled={saving[driver.id]}
                    style={{
                      padding: "6px 14px",
                      borderRadius: "var(--r-md)",
                      border: "none",
                      background: "var(--accent)",
                      color: "#fff",
                      fontWeight: 600,
                      fontSize: "0.8125rem",
                      cursor: saving[driver.id] ? "not-allowed" : "pointer",
                      opacity: saving[driver.id] ? 0.7 : 1,
                    }}
                  >
                    {saving[driver.id] ? "Saving…" : "Save Assignments"}
                  </button>
                </div>

                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 0 }}>
                  {/* Assigned pilots */}
                  <div style={{ padding: "12px 14px", borderRight: "1px solid var(--line)" }}>
                    <div
                      style={{
                        fontSize: "0.6875rem",
                        fontWeight: 700,
                        color: "var(--muted)",
                        textTransform: "uppercase",
                        letterSpacing: "0.05em",
                        marginBottom: 8,
                      }}
                    >
                      Assigned Pilots ({assignedPilots.length})
                    </div>
                    {assignedPilots.length === 0 ? (
                      <p style={{ fontSize: "0.8125rem", color: "var(--ink-muted)", margin: 0 }}>
                        None assigned
                      </p>
                    ) : (
                      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                        {assignedPilots.map((p) => (
                          <label
                            key={p.id}
                            style={{
                              display: "flex",
                              alignItems: "center",
                              gap: 8,
                              fontSize: "0.875rem",
                              cursor: "pointer",
                              color: "var(--ink)",
                              padding: "3px 0",
                            }}
                          >
                            <input
                              type="checkbox"
                              checked
                              onChange={() => togglePilot(driver.id, p.id)}
                              style={{ width: 15, height: 15, cursor: "pointer", flexShrink: 0 }}
                            />
                            {pilotLabel(p)}
                          </label>
                        ))}
                      </div>
                    )}
                  </div>

                  {/* Available pilots */}
                  <div style={{ padding: "12px 14px" }}>
                    <div
                      style={{
                        fontSize: "0.6875rem",
                        fontWeight: 700,
                        color: "var(--muted)",
                        textTransform: "uppercase",
                        letterSpacing: "0.05em",
                        marginBottom: 8,
                      }}
                    >
                      Available ({availablePilots.filter((p) => !assignedSet.has(p.id)).length})
                    </div>
                    {availablePilots.filter((p) => !assignedSet.has(p.id)).length === 0 ? (
                      <p style={{ fontSize: "0.8125rem", color: "var(--ink-muted)", margin: 0 }}>
                        All pilots assigned
                      </p>
                    ) : (
                      <div style={{ display: "flex", flexDirection: "column", gap: 4, maxHeight: 200, overflowY: "auto" }}>
                        {availablePilots
                          .filter((p) => !assignedSet.has(p.id))
                          .map((p) => (
                            <label
                              key={p.id}
                              style={{
                                display: "flex",
                                alignItems: "center",
                                gap: 8,
                                fontSize: "0.875rem",
                                cursor: "pointer",
                                color: "var(--ink-secondary)",
                                padding: "3px 0",
                              }}
                            >
                              <input
                                type="checkbox"
                                checked={false}
                                onChange={() => togglePilot(driver.id, p.id)}
                                style={{ width: 15, height: 15, cursor: "pointer", flexShrink: 0 }}
                              />
                              {pilotLabel(p)}
                            </label>
                          ))}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </>
  );
}

// ---------------------------------------------------------------------------
// Tab 2: Pickup Status
// ---------------------------------------------------------------------------

function PickupStatusTab({
  token,
  tasks,
  selectedTaskId,
  onTaskChange,
}: {
  token: string;
  tasks: TaskRecord[];
  selectedTaskId: number | null;
  onTaskChange: (id: number | null) => void;
}) {
  const [landings, setLandings] = useState<LandingRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchLandings = useCallback(async (taskId: number, tok: string) => {
    try {
      const data = await apiFetch<LandingRecord[]>(`/api/driver/landings/${taskId}`, tok);
      setLandings(data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load landing data");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (intervalRef.current) clearInterval(intervalRef.current);
    if (!selectedTaskId) {
      setLandings([]);
      return;
    }
    setLoading(true);
    void fetchLandings(selectedTaskId, token);
    intervalRef.current = setInterval(() => {
      void fetchLandings(selectedTaskId, token);
    }, 30_000);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [selectedTaskId, token, fetchLandings]);

  // Countdown ticker — updates every second when there are "ready" pilots with future ready_at
  useEffect(() => {
    const hasFutureReady = landings.some(
      (l) => l.status === "landed" && l.ready_at && new Date(l.ready_at).getTime() > Date.now(),
    );
    if (!hasFutureReady) return;
    const t = setInterval(() => setTick((n) => n + 1), 1000);
    return () => clearInterval(t);
  }, [landings]);

  // suppress unused-var warning for tick — it forces re-render for countdowns
  void tick;

  const statusOrder: Record<string, number> = { landed: 0, ready: 1, picked_up: 2, cancelled: 3 };
  const sorted = [...landings].sort((a, b) => {
    const oa = statusOrder[a.status] ?? 9;
    const ob = statusOrder[b.status] ?? 9;
    if (oa !== ob) return oa - ob;
    return (a.pilot_name ?? "").localeCompare(b.pilot_name ?? "");
  });

  if (!selectedTaskId) {
    return (
      <>
        <TaskSelector tasks={tasks} selectedTaskId={selectedTaskId} onChange={onTaskChange} />
        <p className="hint">Select a task above to view landing and pickup status.</p>
      </>
    );
  }

  return (
    <>
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 20, flexWrap: "wrap" }}>
        <div style={{ flex: 1 }}>
          <TaskSelector tasks={tasks} selectedTaskId={selectedTaskId} onChange={onTaskChange} />
        </div>
        <span style={{ fontSize: "0.75rem", color: "var(--ink-muted)", whiteSpace: "nowrap" }}>
          Auto-refreshes every 30s
        </span>
      </div>

      {error && (
        <div
          style={{
            marginBottom: 16,
            padding: "10px 14px",
            borderRadius: "var(--r-md)",
            background: "var(--danger-soft)",
            color: "var(--danger)",
            fontSize: "0.875rem",
            fontWeight: 500,
          }}
        >
          {error}
        </div>
      )}

      {loading ? (
        <p className="hint">Loading landing data…</p>
      ) : sorted.length === 0 ? (
        <p className="hint">No landing reports yet for this task.</p>
      ) : (
        <div className="logbook-table-wrap" style={{ overflowX: "auto" }}>
          <table
            className="results-table"
            style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.875rem" }}
          >
            <thead>
              <tr>
                <th style={{ textAlign: "left", padding: "8px 12px", whiteSpace: "nowrap" }}>Pilot</th>
                <th style={{ textAlign: "left", padding: "8px 12px", whiteSpace: "nowrap" }}>Landed At</th>
                <th style={{ textAlign: "left", padding: "8px 12px", whiteSpace: "nowrap" }}>Ready At</th>
                <th style={{ textAlign: "left", padding: "8px 12px", whiteSpace: "nowrap" }}>Status</th>
                <th style={{ textAlign: "left", padding: "8px 12px", whiteSpace: "nowrap" }}>Picked Up By</th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((landing) => {
                const isFutureReady =
                  landing.status === "landed" &&
                  landing.ready_at &&
                  new Date(landing.ready_at).getTime() > Date.now();
                return (
                  <tr key={landing.landing_id}>
                    <td style={{ padding: "8px 12px", fontWeight: 500 }}>{landing.pilot_name}</td>
                    <td style={{ padding: "8px 12px", color: "var(--ink-secondary)" }}>
                      {formatTime(landing.landed_at)}
                    </td>
                    <td style={{ padding: "8px 12px", color: "var(--ink-secondary)" }}>
                      {landing.ready_at ? (
                        <>
                          {formatTime(landing.ready_at)}
                          {isFutureReady && (
                            <span
                              style={{
                                marginLeft: 6,
                                fontSize: "0.75rem",
                                color: "var(--warning)",
                                fontWeight: 500,
                              }}
                            >
                              ({formatCountdown(landing.ready_at)})
                            </span>
                          )}
                        </>
                      ) : (
                        "-"
                      )}
                    </td>
                    <td style={{ padding: "8px 12px" }}>
                      <StatusBadge status={landing.status} />
                    </td>
                    <td style={{ padding: "8px 12px", color: "var(--ink-secondary)" }}>
                      {landing.driver_name ?? "-"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}

// ---------------------------------------------------------------------------
// Root: DriverDashboard
// ---------------------------------------------------------------------------

export default function DriverDashboard({
  token,
  user,
  selectedEventId,
  tasks,
  pilots,
  isAdmin,
  canManagePlatform,
}: DriverDashboardProps) {
  const canManageAssignments = isAdmin || canManagePlatform;

  const [activeTab, setActiveTab] = useState<DriverTab>(
    canManageAssignments ? "assignments" : "pickup_status",
  );

  // Shared task selection across tabs
  const [selectedTaskId, setSelectedTaskId] = useState<number | null>(() => {
    // Pre-select the most recent task if available
    if (tasks.length === 0) return null;
    const sorted = [...tasks].sort((a, b) => {
      const da = a.task_date ?? "";
      const db = b.task_date ?? "";
      return db.localeCompare(da);
    });
    return sorted[0].id;
  });

  // Re-evaluate default when tasks change
  useEffect(() => {
    if (tasks.length === 0) {
      setSelectedTaskId(null);
      return;
    }
    setSelectedTaskId((prev) => {
      if (prev !== null && tasks.some((t) => t.id === prev)) return prev;
      const sorted = [...tasks].sort((a, b) => (b.task_date ?? "").localeCompare(a.task_date ?? ""));
      return sorted[0].id;
    });
  }, [tasks]);

  if (!selectedEventId) {
    return (
      <SectionCard title="Drivers">
        <div style={{ padding: "16px 18px" }}>
          <p className="hint">Select an event from the sidebar to view driver and pickup tools.</p>
        </div>
      </SectionCard>
    );
  }

  return (
    <SectionCard title="Drivers" description="Driver assignments and pilot pickup status for competition tasks.">
      <div style={{ padding: "16px 18px" }}>
        {/* Tab row */}
        <div className="tab-row">
          {canManageAssignments && (
            <button
              className={`tab-button${activeTab === "assignments" ? " active" : ""}`}
              onClick={() => setActiveTab("assignments")}
              type="button"
            >
              Driver Assignments
            </button>
          )}
          <button
            className={`tab-button${activeTab === "pickup_status" ? " active" : ""}`}
            onClick={() => setActiveTab("pickup_status")}
            type="button"
          >
            Pickup Status
          </button>
        </div>

        {/* Tab content */}
        {activeTab === "assignments" && canManageAssignments ? (
          <DriverAssignmentsTab
            token={token}
            tasks={tasks}
            pilots={pilots}
            selectedTaskId={selectedTaskId}
            onTaskChange={setSelectedTaskId}
          />
        ) : (
          <PickupStatusTab
            token={token}
            tasks={tasks}
            selectedTaskId={selectedTaskId}
            onTaskChange={setSelectedTaskId}
          />
        )}
      </div>
    </SectionCard>
  );
}
