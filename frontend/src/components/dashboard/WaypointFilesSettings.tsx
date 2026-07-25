"use client";

import { useCallback, useEffect, useState } from "react";
import type { MapTelemetrySmoothing } from "../TaskMap";
import WaypointFilesEditor from "./WaypointFilesEditor";
import type { TurnpointSourceRecord } from "./types";


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

export default function WaypointFilesSettings({
  token,
  telemetrySmoothing,
  onSourcesChanged,
}: {
  token: string;
  telemetrySmoothing?: MapTelemetrySmoothing;
  onSourcesChanged?: () => Promise<void> | void;
}) {
  const [sources, setSources] = useState<TurnpointSourceRecord[]>([]);
  const [feedback, setFeedback] = useState<{ type: "success" | "error" | "pending"; text: string } | null>(null);

  const loadSources = useCallback(async () => {
    if (!token) return;
    try {
      const records = await apiFetch<TurnpointSourceRecord[]>("/api/turnpoint-library", token);
      setSources(records);
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
      <div className="participant-intake-row">
        <div className="stack compact">
          <strong>Master turnpoint files</strong>
          <p className="hint">Upload once, then select the files each event uses.</p>
        </div>
        <label className="file-input">
          Upload turnpoints
          <input
            type="file"
            accept=".csv,.gpx"
            onChange={async (event) => {
              const file = event.target.files?.[0];
              if (!file) return;
              const body = new FormData();
              body.append("file", file);
              try {
                setFeedback({ type: "pending", text: `Uploading ${file.name}…` });
                const response = await fetch(`${resolveApiBase()}/api/turnpoint-library/upload`, {
                  method: "POST",
                  headers: { Authorization: `Bearer ${token}` },
                  body,
                });
                if (!response.ok) throw new Error((await response.text()) || "Could not upload that turnpoint file.");
                await loadSources();
                setFeedback({ type: "success", text: `Added ${file.name} to the Turnpoint Library.` });
              } catch (caught) {
                setFeedback({ type: "error", text: caught instanceof Error ? caught.message : "Could not upload that turnpoint file." });
              } finally {
                event.currentTarget.value = "";
              }
            }}
          />
        </label>
      </div>
      <WaypointFilesEditor
        token={token}
        sources={sources}
        telemetrySmoothing={telemetrySmoothing}
        setMessage={(text) => setFeedback({ type: "success", text })}
        setError={(text) => setFeedback({ type: "error", text })}
        emptyMessage="No waypoint files are available yet."
        onSourcesChanged={async () => {
          await loadSources();
          await onSourcesChanged?.();
        }}
      />
    </div>
  );
}
