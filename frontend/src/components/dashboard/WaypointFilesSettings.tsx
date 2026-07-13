"use client";

import { useCallback, useEffect, useState } from "react";
import WaypointFilesEditor, { type WaypointFileSourceRecord } from "./WaypointFilesEditor";

type WaypointFileResponse = {
  source_id: number;
  event_id: number;
  event_name: string;
  event_kind: string;
  filename: string;
  file_format: string;
  sha256: string;
  enabled: boolean;
  uploaded_at: string;
  turnpoint_count: number;
  can_edit: boolean;
};

function resolveApiBase() {
  const configured = process.env.NEXT_PUBLIC_API_BASE_URL?.trim();
  if (configured?.startsWith("/")) return configured;
  if (typeof window !== "undefined") return configured || "/backend";
  return configured ?? "/backend";
}

async function apiFetch<T>(path: string, token: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${resolveApiBase()}${path}`, {
    ...init,
    cache: "no-store",
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      "Content-Type": "application/json",
      ...init.headers,
    },
  });
  if (!response.ok) throw new Error((await response.text()) || `Request failed (${response.status})`);
  return response.json() as Promise<T>;
}

function toEditorSource(record: WaypointFileResponse): WaypointFileSourceRecord {
  return {
    id: record.source_id,
    event_id: record.event_id,
    event_name: record.event_name,
    event_kind: record.event_kind,
    filename: record.filename,
    file_format: record.file_format,
    sha256: record.sha256,
    enabled: record.enabled,
    uploaded_at: record.uploaded_at,
    turnpoint_count: record.turnpoint_count,
    can_edit: record.can_edit,
  };
}

export default function WaypointFilesSettings({ token }: { token: string }) {
  const [sources, setSources] = useState<WaypointFileSourceRecord[]>([]);
  const [feedback, setFeedback] = useState<{ type: "success" | "error" | "pending"; text: string } | null>(null);

  const loadSources = useCallback(async () => {
    if (!token) return;
    try {
      const records = await apiFetch<WaypointFileResponse[]>("/api/auth/waypoint-files", token);
      setSources(records.map(toEditorSource));
      setFeedback(null);
    } catch (caught) {
      setFeedback({ type: "error", text: caught instanceof Error ? caught.message : "Could not load waypoint files." });
    }
  }, [token]);

  useEffect(() => {
    void loadSources();
  }, [loadSources]);

  return (
    <div className="stack form-block">
      {feedback ? <div className={`status-chip ${feedback.type}`}>{feedback.text}</div> : null}
      <WaypointFilesEditor
        token={token}
        sources={sources}
        showContext
        defaultCanEdit={false}
        setMessage={(text) => setFeedback({ type: "success", text })}
        setError={(text) => setFeedback({ type: "error", text })}
        emptyMessage="No waypoint files are available yet."
        onSourcesChanged={loadSources}
      />
    </div>
  );
}
