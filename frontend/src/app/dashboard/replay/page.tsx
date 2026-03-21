"use client";

import { useEffect, useState } from "react";
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

function buildTrackCollection(positions: PositionRecord[]): TrackCollection {
  const byPilot = new Map<number, PositionRecord[]>();
  for (const pos of positions) {
    const pid = pos.pilot_id ?? 0;
    if (!byPilot.has(pid)) byPilot.set(pid, []);
    byPilot.get(pid)!.push(pos);
  }

  let colorIndex = 0;
  const features: TrackCollection["features"] = [];
  for (const [pilotId, pilotPositions] of byPilot) {
    const color = TRACK_COLORS[colorIndex % TRACK_COLORS.length];
    colorIndex++;
    const timestamps = pilotPositions.map((p) => p.timestamp);
    features.push({
      type: "Feature",
      properties: { pilot_id: pilotId, color, timestamps },
      geometry: {
        type: "LineString",
        coordinates: pilotPositions.map((p) =>
          p.alt != null ? [p.lon, p.lat, p.alt] : [p.lon, p.lat]
        ),
      },
    });
  }

  return { type: "FeatureCollection", features };
}

export default function ReplayPage() {
  const searchParams = useSearchParams();
  const taskId = Number(searchParams.get("task")) || 0;
  const [track, setTrack] = useState<TrackCollection | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!taskId) {
      setError("No task selected. Add ?task=ID to the URL.");
      setLoading(false);
      return;
    }

    const token = typeof window !== "undefined" ? localStorage.getItem(TOKEN_KEY) : null;
    if (!token) {
      setError("Not authenticated. Please log in first.");
      setLoading(false);
      return;
    }

    (async () => {
      try {
        const url = `${resolveApiBase()}/api/track/positions/${taskId}?limit=10000`;
        const response = await fetch(url, {
          headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
          cache: "no-store",
        });
        if (!response.ok) throw new Error(`Request failed: ${response.status}`);
        const positions = (await response.json()) as PositionRecord[];
        setTrack(buildTrackCollection(positions));
      } catch (err) {
        setError(`Failed to load positions: ${err}`);
      } finally {
        setLoading(false);
      }
    })();
  }, [taskId]);

  if (error) {
    return (
      <div style={{ padding: 32 }}>
        <h2>Track Replay</h2>
        <p style={{ color: "red" }}>{error}</p>
        <a href="/dashboard">Back to dashboard</a>
      </div>
    );
  }

  if (loading) {
    return (
      <div style={{ padding: 32 }}>
        <h2>Track Replay</h2>
        <p>Loading positions...</p>
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100vh" }}>
      <div style={{ padding: "12px 16px", borderBottom: "1px solid #e2e8f0", display: "flex", alignItems: "center", gap: 16 }}>
        <a href="/dashboard" style={{ textDecoration: "none", color: "inherit" }}>Dashboard</a>
        <span style={{ color: "#94a3b8" }}>/</span>
        <strong>Track Replay — Task {taskId}</strong>
      </div>
      <div style={{ flex: 1 }}>
        <TaskMap
          turnpoints={[]}
          taskPoints={[]}
          track={track}
          editable={false}
          mode="replay"
        />
      </div>
    </div>
  );
}
