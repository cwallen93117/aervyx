"use client";

import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { TaskMap, type TrackCollection } from "../../../components/TaskMap";

const TOKEN_KEY = "flightcomp-platform-token";
const TRACK_COLORS = ["#e11d48", "#2563eb", "#16a34a", "#d97706", "#7c3aed", "#0891b2", "#be185d", "#65a30d", "#0d9488", "#c2410c"];

function resolveApiBase() {
  const configured = process.env.NEXT_PUBLIC_API_BASE_URL?.trim();
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
    return `${window.location.protocol}//${window.location.hostname}:8000`;
  }
  return configured ?? "http://localhost:8000";
}

type PositionRecord = {
  id: string;
  pilot_id: number | null;
  task_id: number;
  lat: number;
  lon: number;
  alt: number | null;
  speed: number | null;
  heading: number | null;
  accuracy: number | null;
  timestamp: string;
  source: string | null;
  device_id: string | null;
  battery_level: number | null;
};

export default function LivePage() {
  const searchParams = useSearchParams();
  const taskId = Number(searchParams.get("task")) || 0;
  const [track, setTrack] = useState<TrackCollection | null>(null);
  const [error, setError] = useState<string | null>(null);
  const positionsByPilot = useRef<Map<number, PositionRecord[]>>(new Map());
  const pilotColorMap = useRef<Map<number, string>>(new Map());
  const colorIndex = useRef(0);

  function getPilotColor(pilotId: number): string {
    if (!pilotColorMap.current.has(pilotId)) {
      pilotColorMap.current.set(pilotId, TRACK_COLORS[colorIndex.current % TRACK_COLORS.length]);
      colorIndex.current++;
    }
    return pilotColorMap.current.get(pilotId)!;
  }

  function buildTrackCollection(): TrackCollection {
    const features: TrackCollection["features"] = [];
    for (const [pilotId, positions] of positionsByPilot.current) {
      if (positions.length === 0) continue;
      features.push({
        type: "Feature",
        properties: { pilot_id: pilotId, color: getPilotColor(pilotId) },
        geometry: {
          type: "LineString",
          coordinates: positions.map((p) => p.alt != null ? [p.lon, p.lat, p.alt] : [p.lon, p.lat]),
        },
      });
    }
    return { type: "FeatureCollection", features };
  }

  function addPosition(pos: PositionRecord) {
    const pid = pos.pilot_id ?? 0;
    if (!positionsByPilot.current.has(pid)) {
      positionsByPilot.current.set(pid, []);
    }
    positionsByPilot.current.get(pid)!.push(pos);
  }

  useEffect(() => {
    if (!taskId) {
      setError("No task selected. Add ?task=ID to the URL.");
      return;
    }

    const token = typeof window !== "undefined" ? localStorage.getItem(TOKEN_KEY) : null;
    if (!token) {
      setError("Not authenticated. Please log in first.");
      return;
    }

    const url = `${resolveApiBase()}/api/track/live/${taskId}`;
    let eventSource: EventSource | null = null;

    // EventSource doesn't support custom headers, so use fetch-based SSE
    const controller = new AbortController();

    (async () => {
      try {
        const response = await fetch(url, {
          headers: { Authorization: `Bearer ${token}`, Accept: "text/event-stream" },
          cache: "no-store",
          signal: controller.signal,
        });
        if (!response.ok) {
          setError(`Connection failed: ${response.status}`);
          return;
        }
        const reader = response.body?.getReader();
        if (!reader) return;

        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop() ?? "";

          for (const line of lines) {
            if (line.startsWith("data: ")) {
              const data = line.substring(6);
              try {
                const parsed = JSON.parse(data);
                if (Array.isArray(parsed)) {
                  // snapshot
                  for (const pos of parsed as PositionRecord[]) {
                    addPosition(pos);
                  }
                } else {
                  // single position
                  addPosition(parsed as PositionRecord);
                }
                setTrack(buildTrackCollection());
              } catch {
                // skip malformed
              }
            }
          }
        }
      } catch (err) {
        if (!controller.signal.aborted) {
          setError(`SSE error: ${err}`);
        }
      }
    })();

    return () => controller.abort();
  }, [taskId]);

  if (error) {
    return (
      <div style={{ padding: 32 }}>
        <h2>Live Tracking</h2>
        <p style={{ color: "red" }}>{error}</p>
        <a href="/dashboard">Back to dashboard</a>
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100vh" }}>
      <div style={{ padding: "12px 16px", borderBottom: "1px solid #e2e8f0", display: "flex", alignItems: "center", gap: 16 }}>
        <a href="/dashboard" style={{ textDecoration: "none", color: "inherit" }}>Dashboard</a>
        <span style={{ color: "#94a3b8" }}>/</span>
        <strong>Live Tracking — Task {taskId}</strong>
        <span style={{ marginLeft: "auto", fontSize: 13, color: "#64748b" }}>
          {positionsByPilot.current.size} pilot{positionsByPilot.current.size !== 1 ? "s" : ""} tracked
        </span>
      </div>
      <div style={{ flex: 1 }}>
        <TaskMap
          turnpoints={[]}
          taskPoints={[]}
          track={track}
          editable={false}
          mode="live"
        />
      </div>
    </div>
  );
}
