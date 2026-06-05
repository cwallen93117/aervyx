"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { TaskMap, type TrackCollection } from "../../../components/TaskMap";
import { type EventRecord, type ResultRecord, type TaskRecord, type UploadRecord } from "../../../components/dashboard/types";
import { computeTaskOptimization } from "../../../lib/taskOptimization";

const TOKEN_KEY = "flightcomp-platform-token";
type BasemapMode = "streets" | "satellite" | "terrain";
type ScenarioKey =
  | "map-only-2d-streets"
  | "map-only-2d-satellite"
  | "map-only-2d-terrain-basemap"
  | "map-only-3d-terrain"
  | "tracks-only"
  | "map-2d-tracks"
  | "map-3d-terrain-tracks";

type ScenarioDefinition = {
  key: ScenarioKey;
  area: string;
  label: string;
  renderMap: boolean;
  includeTracks: boolean;
  initial3D: boolean;
  basemap: BasemapMode;
  autoReplay?: boolean;
  settleMs: number;
};

type ResourceSummary = {
  totalCount: number;
  transferBytes: number;
  basemapTiles: number;
  demTiles: number;
};

type MemorySample = {
  label: string;
  timestamp: string;
  jsHeapUsedBytes: number | null;
  jsHeapTotalBytes: number | null;
  userAgentSpecificBytes: number | null;
  resources: ResourceSummary;
};

type ScenarioResult = {
  key: ScenarioKey;
  area: string;
  label: string;
  status: "ok" | "error";
  error?: string;
  trackPayloadBytes: number;
  trackPointCount: number;
  trackCount: number;
  before: MemorySample;
  afterLoad: MemorySample;
  afterClose: MemorySample;
};

type TrackLoadStats = {
  tracksByUploadId: Record<number, TrackCollection>;
  payloadBytesByUploadId: Record<number, number>;
};

type BrowserPerformance = Performance & {
  memory?: {
    usedJSHeapSize?: number;
    totalJSHeapSize?: number;
  };
  measureUserAgentSpecificMemory?: () => Promise<{ bytes: number }>;
};

const SCENARIOS: ScenarioDefinition[] = [
  {
    key: "map-only-2d-streets",
    area: "2D map",
    label: "Map only, 2D streets",
    renderMap: true,
    includeTracks: false,
    initial3D: false,
    basemap: "streets",
    settleMs: 2500,
  },
  {
    key: "map-only-2d-satellite",
    area: "Basemap tiles",
    label: "Map only, 2D satellite",
    renderMap: true,
    includeTracks: false,
    initial3D: false,
    basemap: "satellite",
    settleMs: 2500,
  },
  {
    key: "map-only-2d-terrain-basemap",
    area: "Basemap tiles",
    label: "Map only, 2D terrain basemap",
    renderMap: true,
    includeTracks: false,
    initial3D: false,
    basemap: "terrain",
    settleMs: 2500,
  },
  {
    key: "map-only-3d-terrain",
    area: "3D terrain",
    label: "Map only, 3D DEM terrain",
    renderMap: true,
    includeTracks: false,
    initial3D: true,
    basemap: "streets",
    settleMs: 3500,
  },
  {
    key: "tracks-only",
    area: "Track logs",
    label: "Fetch and parse selected tracks only",
    renderMap: false,
    includeTracks: true,
    initial3D: false,
    basemap: "streets",
    settleMs: 1000,
  },
  {
    key: "map-2d-tracks",
    area: "2D track rendering",
    label: "2D map with selected tracks",
    renderMap: true,
    includeTracks: true,
    initial3D: false,
    basemap: "streets",
    settleMs: 3500,
  },
  {
    key: "map-3d-terrain-tracks",
    area: "3D terrain + replay",
    label: "3D terrain with selected tracks and playback",
    renderMap: true,
    includeTracks: true,
    initial3D: true,
    basemap: "streets",
    autoReplay: true,
    settleMs: 6000,
  },
];

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

function sleep(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function formatBytes(bytes: number | null) {
  if (bytes == null || !Number.isFinite(bytes)) {
    return "n/a";
  }
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  const units = ["KB", "MB", "GB"] as const;
  let value = bytes / 1024;
  let unitIndex = 0;
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }
  return `${value.toFixed(value >= 100 ? 0 : 1)} ${units[unitIndex]}`;
}

function pointCountForTrack(track: TrackCollection | null) {
  return track?.features.reduce((total, feature) => total + (feature.geometry.type === "LineString" ? feature.geometry.coordinates.length : 0), 0) ?? 0;
}

function mergeTracks(
  uploadIds: number[],
  tracksByUploadId: Record<number, TrackCollection>,
  resultsByUploadId: Map<number, ResultRecord>,
): TrackCollection | null {
  const colors = ["#2563eb", "#dc2626", "#16a34a", "#7c3aed", "#d97706", "#0891b2", "#db2777", "#65a30d"];
  const features = uploadIds.flatMap((uploadId, index) => {
    const collection = tracksByUploadId[uploadId];
    if (!collection) {
      return [];
    }
    const result = resultsByUploadId.get(uploadId);
    return collection.features.map((feature) => ({
      ...feature,
      properties: {
        ...feature.properties,
        color: colors[index % colors.length],
        pilot_name: result?.pilot_name?.trim() || feature.properties?.pilot_name || `Pilot ${uploadId}`,
        upload_id: uploadId,
      },
    }));
  });
  return features.length ? { type: "FeatureCollection", features } : null;
}

function summarizeResources(startTime: number): ResourceSummary {
  const entries = performance.getEntriesByType("resource") as PerformanceResourceTiming[];
  return entries
    .filter((entry) => entry.startTime >= startTime)
    .reduce<ResourceSummary>(
      (summary, entry) => {
        const url = entry.name.toLowerCase();
        summary.totalCount += 1;
        summary.transferBytes += Number.isFinite(entry.transferSize) ? entry.transferSize : 0;
        if (url.includes("elevation-tiles-prod") || url.includes("terrarium")) {
          summary.demTiles += 1;
        } else if (
          url.includes("tile.openstreetmap.org") ||
          url.includes("opentopomap.org") ||
          url.includes("arcgis.com") ||
          url.includes("mapserver/tile")
        ) {
          summary.basemapTiles += 1;
        }
        return summary;
      },
      { totalCount: 0, transferBytes: 0, basemapTiles: 0, demTiles: 0 },
    );
}

async function captureSample(label: string, resourceStartTime: number): Promise<MemorySample> {
  await new Promise((resolve) => window.requestAnimationFrame(resolve));
  const browserPerformance = performance as BrowserPerformance;
  let userAgentSpecificBytes: number | null = null;
  try {
    userAgentSpecificBytes = browserPerformance.measureUserAgentSpecificMemory
      ? (await browserPerformance.measureUserAgentSpecificMemory()).bytes
      : null;
  } catch {
    userAgentSpecificBytes = null;
  }
  return {
    label,
    timestamp: new Date().toISOString(),
    jsHeapUsedBytes: browserPerformance.memory?.usedJSHeapSize ?? null,
    jsHeapTotalBytes: browserPerformance.memory?.totalJSHeapSize ?? null,
    userAgentSpecificBytes,
    resources: summarizeResources(resourceStartTime),
  };
}

async function readJsonWithSize<T>(url: string, token: string): Promise<{ payload: T; bytes: number }> {
  const response = await fetch(url, {
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });
  const text = await response.text();
  if (!response.ok) {
    throw new Error(text || `Request failed with ${response.status}`);
  }
  return { payload: JSON.parse(text) as T, bytes: new TextEncoder().encode(text).length };
}

function issueRows() {
  return [
    ["Track logs", "Full-resolution IGC payloads are fetched and duplicated into replay arrays.", "Run tracks-only and compare JS heap + payload bytes.", "Task-aware replay simplification near waypoints/start/goal."],
    ["2D map rendering", "deck.gl path buffers and labels may grow with all selected track vertices.", "Compare map-only-2d to map-2d-tracks.", "Reduce path churn, simplify layer data, limit labels/markers."],
    ["3D terrain/elevation", "DEM raster tiles and terrain meshes can consume GPU/process memory outside JS heap.", "Compare map-only-2d to map-only-3d-terrain, then 3D with tracks.", "Safer 3D defaults, unload/defer DEM for large replay."],
    ["Basemap tiles", "Satellite/terrain basemaps can add raster tile pressure over wide tasks.", "Compare streets, satellite, and terrain basemap scenarios.", "Default large replay to a lighter basemap or cap zoom/tile loading."],
    ["Replay animation churn", "Playback may allocate new path/layer data repeatedly.", "Compare map-2d-tracks settled memory to 3D playback memory over time.", "Avoid per-frame path slicing and reduce layer updates."],
  ];
}

export default function ReplayMemoryProfilerClient() {
  const apiBase = useMemo(resolveApiBase, []);
  const [token, setToken] = useState("");
  const [events, setEvents] = useState<EventRecord[]>([]);
  const [tasks, setTasks] = useState<TaskRecord[]>([]);
  const [selectedEventId, setSelectedEventId] = useState<number | "">("");
  const [selectedTaskId, setSelectedTaskId] = useState<number | "">("");
  const [task, setTask] = useState<TaskRecord | null>(null);
  const [results, setResults] = useState<ResultRecord[]>([]);
  const [uploads, setUploads] = useState<UploadRecord[]>([]);
  const [maxTracks, setMaxTracks] = useState(25);
  const [status, setStatus] = useState("Choose a task, then run the comparison.");
  const [running, setRunning] = useState(false);
  const [scenarioResults, setScenarioResults] = useState<ScenarioResult[]>([]);
  const [activeScenario, setActiveScenario] = useState<ScenarioDefinition | null>(null);
  const [activeTrack, setActiveTrack] = useState<TrackCollection | null>(null);
  const [mapKey, setMapKey] = useState(0);
  const trackStatsRef = useRef<TrackLoadStats>({ tracksByUploadId: {}, payloadBytesByUploadId: {} });

  const selectedUploadIds = useMemo(() => {
    const resultUploadIds = results
      .map((result) => result.upload_id)
      .filter((uploadId): uploadId is number => uploadId != null);
    const fallbackUploadIds = uploads.map((upload) => upload.id);
    return Array.from(new Set(resultUploadIds.length ? resultUploadIds : fallbackUploadIds)).slice(0, maxTracks);
  }, [maxTracks, results, uploads]);

  const resultsByUploadId = useMemo(
    () => new Map(results.filter((result) => result.upload_id != null).map((result) => [result.upload_id as number, result])),
    [results],
  );
  const taskMetrics = useMemo(() => (task ? computeTaskOptimization(task.points) : null), [task]);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const savedToken = params.get("debug_token") || window.localStorage.getItem(TOKEN_KEY) || "";
    setToken(savedToken);
    if (!savedToken) {
      setStatus("Sign in through the dashboard first so the profiler can reuse your local auth token.");
      return;
    }
    readJsonWithSize<EventRecord[]>(`${apiBase}/api/events`, savedToken)
      .then(({ payload }) => {
        setEvents(payload);
        const first = payload[0]?.id ?? "";
        setSelectedEventId(first);
      })
      .catch((error) => setStatus(error instanceof Error ? error.message : "Could not load events."));
  }, [apiBase]);

  useEffect(() => {
    if (!token || selectedEventId === "") {
      return;
    }
    setStatus("Loading event tasks...");
    readJsonWithSize<TaskRecord[]>(`${apiBase}/api/events/${selectedEventId}/tasks`, token)
      .then(({ payload }) => {
        setTasks(payload);
        const first = payload[0]?.id ?? "";
        setSelectedTaskId(first);
        setStatus(payload.length ? "Choose a benchmark task, then run the comparison." : "This event has no tasks.");
      })
      .catch((error) => setStatus(error instanceof Error ? error.message : "Could not load tasks."));
  }, [apiBase, selectedEventId, token]);

  async function loadTaskData(taskId: number) {
    if (!token) {
      throw new Error("No auth token found. Sign in through the dashboard first.");
    }
    const [taskResponse, resultsResponse, uploadsResponse] = await Promise.all([
      readJsonWithSize<TaskRecord>(`${apiBase}/api/tasks/${taskId}`, token),
      readJsonWithSize<ResultRecord[]>(`${apiBase}/api/tasks/${taskId}/results`, token),
      readJsonWithSize<UploadRecord[]>(`${apiBase}/api/tasks/${taskId}/uploads`, token),
    ]);
    setTask(taskResponse.payload);
    setResults(resultsResponse.payload);
    setUploads(uploadsResponse.payload);
    return {
      task: taskResponse.payload,
      results: resultsResponse.payload,
      uploads: uploadsResponse.payload,
    };
  }

  async function loadTracks(uploadIds: number[]) {
    if (!token) {
      throw new Error("No auth token found. Sign in through the dashboard first.");
    }
    const nextTracks = { ...trackStatsRef.current.tracksByUploadId };
    const nextPayloadBytes = { ...trackStatsRef.current.payloadBytesByUploadId };
    for (const uploadId of uploadIds) {
      if (nextTracks[uploadId]) {
        continue;
      }
      setStatus(`Loading track ${uploadIds.indexOf(uploadId) + 1} of ${uploadIds.length}...`);
      const response = await readJsonWithSize<TrackCollection>(`${apiBase}/api/uploads/${uploadId}/track`, token);
      nextTracks[uploadId] = response.payload;
      nextPayloadBytes[uploadId] = response.bytes;
    }
    trackStatsRef.current = { tracksByUploadId: nextTracks, payloadBytesByUploadId: nextPayloadBytes };
    return trackStatsRef.current;
  }

  async function unmountMap() {
    setActiveScenario(null);
    setActiveTrack(null);
    setMapKey((current) => current + 1);
    await sleep(1000);
  }

  async function runScenario(definition: ScenarioDefinition, uploadIds: number[]) {
    await unmountMap();
    const resourceStartTime = performance.now();
    const before = await captureSample("Before scenario", resourceStartTime);
    let trackLoadStats = trackStatsRef.current;
    let mergedTrack: TrackCollection | null = null;

    if (definition.includeTracks) {
      trackLoadStats = await loadTracks(uploadIds);
      mergedTrack = mergeTracks(uploadIds, trackLoadStats.tracksByUploadId, resultsByUploadId);
    }

    if (definition.renderMap) {
      setActiveTrack(mergedTrack);
      setActiveScenario(definition);
      setMapKey((current) => current + 1);
    }

    await sleep(definition.settleMs);
    const afterLoad = await captureSample("After load/settle", resourceStartTime);
    await unmountMap();
    const afterClose = await captureSample("After close/unmount", resourceStartTime);

    const trackPayloadBytes = uploadIds.reduce((total, uploadId) => total + (trackLoadStats.payloadBytesByUploadId[uploadId] ?? 0), 0);
    const trackPointCount = uploadIds.reduce((total, uploadId) => total + pointCountForTrack(trackLoadStats.tracksByUploadId[uploadId] ?? null), 0);

    return {
      key: definition.key,
      area: definition.area,
      label: definition.label,
      status: "ok" as const,
      trackPayloadBytes,
      trackPointCount,
      trackCount: uploadIds.length,
      before,
      afterLoad,
      afterClose,
    };
  }

  async function runAllScenarios() {
    if (selectedTaskId === "") {
      setStatus("Choose a task first.");
      return;
    }
    setRunning(true);
    setScenarioResults([]);
    trackStatsRef.current = { tracksByUploadId: {}, payloadBytesByUploadId: {} };
    try {
      setStatus("Loading task data...");
      const loaded = await loadTaskData(selectedTaskId);
      const resultUploadIds = loaded.results
        .map((result) => result.upload_id)
        .filter((uploadId): uploadId is number => uploadId != null);
      const fallbackUploadIds = loaded.uploads.map((upload) => upload.id);
      const uploadIds = Array.from(new Set(resultUploadIds.length ? resultUploadIds : fallbackUploadIds)).slice(0, maxTracks);
      if (!uploadIds.length) {
        throw new Error("This task has no replayable uploads.");
      }
      for (const scenario of SCENARIOS) {
        setStatus(`Running: ${scenario.label}`);
        try {
          const result = await runScenario(scenario, uploadIds);
          setScenarioResults((current) => [...current, result]);
        } catch (error) {
          const resourceStartTime = performance.now();
          const sample = await captureSample("Scenario failed", resourceStartTime);
          setScenarioResults((current) => [
            ...current,
            {
              key: scenario.key,
              area: scenario.area,
              label: scenario.label,
              status: "error",
              error: error instanceof Error ? error.message : "Scenario failed.",
              trackPayloadBytes: 0,
              trackPointCount: 0,
              trackCount: uploadIds.length,
              before: sample,
              afterLoad: sample,
              afterClose: sample,
            },
          ]);
        }
      }
      setStatus("Comparison complete. Review the table before implementing any fix.");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Profiler run failed.");
    } finally {
      await unmountMap();
      setRunning(false);
    }
  }

  const heapDelta = (result: ScenarioResult) =>
    result.afterLoad.jsHeapUsedBytes != null && result.before.jsHeapUsedBytes != null
      ? result.afterLoad.jsHeapUsedBytes - result.before.jsHeapUsedBytes
      : null;

  return (
    <main style={{ minHeight: "100vh", padding: 24, background: "#f8fafc", color: "#0f172a" }}>
      <div style={{ maxWidth: 1180, margin: "0 auto", display: "grid", gap: 18 }}>
        <header>
          <p style={{ margin: "0 0 6px", color: "#64748b", fontSize: 13, fontWeight: 700, textTransform: "uppercase" }}>Development profiler</p>
          <h1 style={{ margin: 0, fontSize: 30 }}>Replay memory comparison</h1>
          <p style={{ maxWidth: 780, color: "#475569" }}>
            This page measures track-log loading, 2D map rendering, basemap tiles, 3D DEM terrain, and replay playback separately.
            It does not change production replay behavior.
          </p>
        </header>

        <section style={{ display: "grid", gap: 12, gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))" }}>
          <label style={{ display: "grid", gap: 6 }}>
            <span>Event</span>
            <select value={selectedEventId} disabled={running} onChange={(event) => setSelectedEventId(Number(event.target.value))}>
              {events.map((event) => (
                <option key={event.id} value={event.id}>{event.name}</option>
              ))}
            </select>
          </label>
          <label style={{ display: "grid", gap: 6 }}>
            <span>Benchmark task</span>
            <select value={selectedTaskId} disabled={running} onChange={(event) => setSelectedTaskId(Number(event.target.value))}>
              {tasks.map((item) => (
                <option key={item.id} value={item.id}>{item.name}</option>
              ))}
            </select>
          </label>
          <label style={{ display: "grid", gap: 6 }}>
            <span>Max tracks</span>
            <input type="number" min={1} max={200} value={maxTracks} disabled={running} onChange={(event) => setMaxTracks(Math.max(1, Number(event.target.value) || 1))} />
          </label>
          <div style={{ display: "flex", alignItems: "end" }}>
            <button type="button" disabled={running || !token || selectedTaskId === ""} onClick={() => void runAllScenarios()}>
              {running ? "Running..." : "Run comparison"}
            </button>
          </div>
        </section>

        <p style={{ margin: 0, color: running ? "#92400e" : "#475569" }}>{status}</p>

        <section style={{ overflowX: "auto", background: "#fff", border: "1px solid #e2e8f0", borderRadius: 8 }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead>
              <tr style={{ background: "#f1f5f9" }}>
                {["Area", "Why it could cause OOM", "How this profiler measures it", "Likely fix if confirmed"].map((heading) => (
                  <th key={heading} style={{ padding: 10, textAlign: "left", borderBottom: "1px solid #e2e8f0" }}>{heading}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {issueRows().map((row) => (
                <tr key={row[0]}>
                  {row.map((cell) => (
                    <td key={cell} style={{ padding: 10, verticalAlign: "top", borderBottom: "1px solid #e2e8f0" }}>{cell}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </section>

        <section style={{ overflowX: "auto", background: "#fff", border: "1px solid #e2e8f0", borderRadius: 8 }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead>
              <tr style={{ background: "#f1f5f9" }}>
                {[
                  "Scenario",
                  "Area",
                  "Track payload",
                  "Track points",
                  "JS heap delta",
                  "JS heap after",
                  "UA memory after",
                  "Resources",
                  "Basemap/DEM tiles",
                  "After close heap",
                  "Status",
                ].map((heading) => (
                  <th key={heading} style={{ padding: 10, textAlign: "left", borderBottom: "1px solid #e2e8f0", whiteSpace: "nowrap" }}>{heading}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {scenarioResults.length ? scenarioResults.map((result) => (
                <tr key={result.key}>
                  <td style={{ padding: 10, borderBottom: "1px solid #e2e8f0" }}>{result.label}</td>
                  <td style={{ padding: 10, borderBottom: "1px solid #e2e8f0" }}>{result.area}</td>
                  <td style={{ padding: 10, borderBottom: "1px solid #e2e8f0" }}>{formatBytes(result.trackPayloadBytes)}</td>
                  <td style={{ padding: 10, borderBottom: "1px solid #e2e8f0" }}>{result.trackPointCount.toLocaleString()} / {result.trackCount} tracks</td>
                  <td style={{ padding: 10, borderBottom: "1px solid #e2e8f0" }}>{formatBytes(heapDelta(result))}</td>
                  <td style={{ padding: 10, borderBottom: "1px solid #e2e8f0" }}>{formatBytes(result.afterLoad.jsHeapUsedBytes)}</td>
                  <td style={{ padding: 10, borderBottom: "1px solid #e2e8f0" }}>{formatBytes(result.afterLoad.userAgentSpecificBytes)}</td>
                  <td style={{ padding: 10, borderBottom: "1px solid #e2e8f0" }}>
                    {result.afterLoad.resources.totalCount} / {formatBytes(result.afterLoad.resources.transferBytes)}
                  </td>
                  <td style={{ padding: 10, borderBottom: "1px solid #e2e8f0" }}>
                    {result.afterLoad.resources.basemapTiles} / {result.afterLoad.resources.demTiles}
                  </td>
                  <td style={{ padding: 10, borderBottom: "1px solid #e2e8f0" }}>{formatBytes(result.afterClose.jsHeapUsedBytes)}</td>
                  <td style={{ padding: 10, borderBottom: "1px solid #e2e8f0", color: result.status === "ok" ? "#166534" : "#b91c1c" }}>
                    {result.status === "ok" ? "ok" : result.error}
                  </td>
                </tr>
              )) : (
                <tr>
                  <td colSpan={11} style={{ padding: 18, color: "#64748b" }}>No measurements yet.</td>
                </tr>
              )}
            </tbody>
          </table>
        </section>

        <p style={{ color: "#64748b", fontSize: 13 }}>
          Note: normal web pages cannot reliably read Chrome GPU/process memory. The UA memory column is filled only when Chromium exposes
          `measureUserAgentSpecificMemory`; otherwise use Chrome Task Manager alongside this table for process/GPU confirmation.
        </p>

        {activeScenario && task && taskMetrics ? (
          <section style={{ height: 460, background: "#fff", border: "1px solid #e2e8f0", borderRadius: 8, overflow: "hidden" }}>
            <TaskMap
              key={`${activeScenario.key}-${mapKey}`}
              turnpoints={[]}
              taskPoints={task.points}
              optimizedRoute={taskMetrics.routeCoordinates}
              legMetrics={taskMetrics.legMetrics}
              track={activeTrack}
              editable={false}
              fitKey={`${task.id}-${activeScenario.key}-${mapKey}`}
              units={{ altitude: "ft", speed: "kph", distance: "km", vario: "fpm" }}
              telemetrySmoothing={{
                telemetry_vario_smoothing_seconds: 5,
                telemetry_altitude_smoothing_seconds: 3,
                telemetry_speed_smoothing_seconds: 3,
                telemetry_glide_ratio_smoothing_seconds: 5,
                max_map_pitch_degrees: 75,
              }}
              mode="replay"
              overlayConfig={{
                replay_speed: true,
                replay_scrubber: activeScenario.includeTracks,
                flight_track: activeScenario.includeTracks,
                track_highlight: false,
                basemap_selector: false,
                altitude_slider: false,
                fullscreen_toggle: false,
                "2d_3d_toggle": false,
              }}
              debugInitialBasemapMode={activeScenario.basemap}
              debugInitialPerspective3D={activeScenario.initial3D}
              debugAutoStartReplay={activeScenario.autoReplay}
            />
          </section>
        ) : null}
      </div>
    </main>
  );
}
