"use client";

import { useEffect, useMemo, useState } from "react";
import { TaskMap, type MapTelemetrySmoothing } from "../TaskMap";
import type { TurnpointRecord, TurnpointSourceRecord } from "./types";

type TurnpointSymbol = "" | "grass_strip" | "paved_runway" | "dot" | "bar" | "lz" | "launch";
type TurnpointSortKey = "name" | "symbol";
type TurnpointSortState = { key: TurnpointSortKey; direction: "asc" | "desc" } | null;
type EditableTurnpoint = {
  id: number | null;
  name: string;
  code: string;
  symbol: TurnpointSymbol;
  latitude: string;
  longitude: string;
  elevation_m: string;
  extra_json: Record<string, string>;
};

export type WaypointFileSourceRecord = TurnpointSourceRecord;

type FeedbackSetter = (message: string) => void;

export interface WaypointFilesEditorProps {
  token: string;
  sources: WaypointFileSourceRecord[];
  emptyMessage?: string;
  telemetrySmoothing?: MapTelemetrySmoothing;
  setMessage: FeedbackSetter;
  setError: FeedbackSetter;
  onSourcesChanged?: () => Promise<void> | void;
}

const turnpointSymbolOptions = [
  { value: "", label: "Blank" },
  { value: "grass_strip", label: "Grass Strip" },
  { value: "paved_runway", label: "Paved Runway" },
  { value: "dot", label: "Dot" },
  { value: "bar", label: "Bar" },
  { value: "lz", label: "LZ" },
  { value: "launch", label: "Launch" },
] satisfies Array<{ value: TurnpointSymbol; label: string }>;

const waypointExportFormats = [
  { value: "gpx", label: "GPX" },
  { value: "cup", label: "CUP" },
  { value: "wpt", label: "WPT" },
  { value: "kmz", label: "KMZ" },
  { value: "csv", label: "CSV" },
] as const;

function defaultExportFormat(fileFormat: string | null | undefined): string {
  return waypointExportFormats.some((option) => option.value === fileFormat) ? fileFormat as string : "gpx";
}

function resolveApiBase() {
  const configured = process.env.NEXT_PUBLIC_API_BASE_URL?.trim();
  if (configured?.startsWith("/")) return configured;
  if (typeof window !== "undefined") return configured || "/backend";
  return configured ?? "/backend";
}

async function apiFetchBlob(path: string, token: string): Promise<{ blob: Blob; filename: string | null }> {
  const response = await fetch(`${resolveApiBase()}${path}`, {
    cache: "no-store",
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
  });
  if (!response.ok) throw new Error((await response.text()) || `Request failed (${response.status})`);
  const disposition = response.headers.get("content-disposition");
  const filenameMatch = disposition?.match(/filename\*=UTF-8''([^;]+)|filename="?([^";]+)"?/i);
  const filename = filenameMatch ? decodeURIComponent(filenameMatch[1] ?? filenameMatch[2] ?? "") : null;
  return { blob: await response.blob(), filename };
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
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

function normalizeEditableSymbol(value: unknown): TurnpointSymbol {
  return value === "grass_strip" || value === "paved_runway" || value === "dot" || value === "bar" || value === "lz" || value === "launch" ? value : "";
}

function turnpointSymbolLabel(symbol: unknown): string {
  return turnpointSymbolOptions.find((option) => option.value === normalizeEditableSymbol(symbol))?.label ?? "";
}

function turnpointToEditable(turnpoint?: TurnpointRecord | null, fallback?: { latitude: number; longitude: number; elevationM?: number | null }): EditableTurnpoint {
  return {
    id: turnpoint?.id ?? null,
    name: turnpoint?.name ?? "",
    code: turnpoint?.code ?? "",
    symbol: normalizeEditableSymbol(turnpoint?.symbol),
    latitude: String(turnpoint?.latitude ?? fallback?.latitude ?? ""),
    longitude: String(turnpoint?.longitude ?? fallback?.longitude ?? ""),
    elevation_m: turnpoint?.elevation_m == null ? (fallback?.elevationM == null ? "" : String(Math.round(fallback.elevationM))) : String(turnpoint.elevation_m),
    extra_json: Object.fromEntries(Object.entries(turnpoint?.extra_json ?? {}).map(([key, value]) => [key, String(value ?? "")])),
  };
}

function editableToPayload(editable: EditableTurnpoint) {
  const latitude = Number(editable.latitude);
  const longitude = Number(editable.longitude);
  const elevation = editable.elevation_m.trim() ? Number(editable.elevation_m) : null;
  if (!editable.name.trim()) throw new Error("Waypoint name is required.");
  if (!Number.isFinite(latitude) || latitude < -90 || latitude > 90) throw new Error("Latitude must be between -90 and 90.");
  if (!Number.isFinite(longitude) || longitude < -180 || longitude > 180) throw new Error("Longitude must be between -180 and 180.");
  if (elevation !== null && !Number.isFinite(elevation)) throw new Error("Altitude must be a number.");
  return {
    name: editable.name.trim(),
    code: editable.code.trim() || null,
    symbol: editable.symbol || null,
    latitude,
    longitude,
    elevation_m: elevation,
    extra_json: editable.extra_json,
  };
}

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function TurnpointSymbolIcon({ symbol }: { symbol: TurnpointSymbol }) {
  if (symbol === "grass_strip" || symbol === "paved_runway") {
    return <span className={`turnpoint-symbol-icon ${symbol}`} aria-hidden="true">✈</span>;
  }
  if (symbol === "bar") {
    return (
      <svg className="turnpoint-symbol-icon bar" viewBox="0 0 48 48" aria-hidden="true" focusable="false">
        <path fill="#7c3aed" stroke="#ffffff" strokeWidth="2" strokeLinejoin="round" d="M9 7h30L27 22v14h8v5H13v-5h8V22L9 7zm8 5l7 8 7-8H17z" />
        <circle cx="34" cy="12" r="4" fill="#ef4444" stroke="#ffffff" strokeWidth="1.5" />
      </svg>
    );
  }
  if (symbol === "dot") return <span className="turnpoint-symbol-icon dot" aria-hidden="true" />;
  if (symbol === "lz") return <span className="turnpoint-symbol-icon lz" aria-hidden="true">◎↓</span>;
  if (symbol === "launch") return <span className="turnpoint-symbol-icon launch" aria-hidden="true">▲↗</span>;
  return <span className="turnpoint-symbol-icon blank" aria-hidden="true" />;
}

function TurnpointSymbolSelect({ value, onChange }: { value: TurnpointSymbol; onChange: (next: TurnpointSymbol) => void }) {
  const [open, setOpen] = useState(false);
  const selected = turnpointSymbolOptions.find((option) => option.value === value) ?? turnpointSymbolOptions[0];
  return (
    <div className="turnpoint-symbol-select">
      <button type="button" className="turnpoint-symbol-select-button" onClick={() => setOpen((current) => !current)} aria-expanded={open}>
        <TurnpointSymbolIcon symbol={selected.value} />
        <span>{selected.label}</span>
      </button>
      {open ? (
        <div className="turnpoint-symbol-select-menu" role="listbox">
          {turnpointSymbolOptions.map((option) => (
            <button
              key={option.value || "blank"}
              type="button"
              className="turnpoint-symbol-select-option"
              onClick={() => {
                onChange(option.value);
                setOpen(false);
              }}
            >
              <TurnpointSymbolIcon symbol={option.value} />
              <span>{option.label}</span>
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}

export default function WaypointFilesEditor({
  token,
  sources,
  emptyMessage = "No waypoint files uploaded yet.",
  telemetrySmoothing,
  setMessage,
  setError,
  onSourcesChanged,
}: WaypointFilesEditorProps) {
  const [selectedSourceId, setSelectedSourceId] = useState<number | null>(null);
  const [sourceTurnpoints, setSourceTurnpoints] = useState<TurnpointRecord[]>([]);
  const [sourceTurnpointsLoading, setSourceTurnpointsLoading] = useState(false);
  const [editingTurnpointId, setEditingTurnpointId] = useState<number | null>(null);
  const [turnpointEdit, setTurnpointEdit] = useState<EditableTurnpoint | null>(null);
  const [draftTurnpoint, setDraftTurnpoint] = useState<EditableTurnpoint | null>(null);
  const [turnpointSort, setTurnpointSort] = useState<TurnpointSortState>(null);
  const [mergeSourceIds, setMergeSourceIds] = useState<Set<number>>(new Set());
  const [mergeFilename, setMergeFilename] = useState("");
  const [mergeOpen, setMergeOpen] = useState(false);
  const [saveAsSource, setSaveAsSource] = useState<WaypointFileSourceRecord | null>(null);
  const [saveAsFilename, setSaveAsFilename] = useState("");
  const [saveAsFormat, setSaveAsFormat] = useState("gpx");
  const [downloadFormats, setDownloadFormats] = useState<Record<number, string>>({});

  useEffect(() => {
    if (selectedSourceId && !sources.some((source) => source.id === selectedSourceId)) {
      closeTurnpointSourceDetail();
    }
    setMergeSourceIds((current) => new Set([...current].filter((id) => sources.some((source) => source.id === id))));
  }, [selectedSourceId, sources]);

  const selectedTurnpointSource = sources.find((source) => source.id === selectedSourceId) ?? null;
  const selectedSourceExtraColumns = Array.from(new Set(sourceTurnpoints.flatMap((turnpoint) => Object.keys(turnpoint.extra_json ?? {}))));
  const turnpointTableColSpan = 6 + selectedSourceExtraColumns.length;
  const sortedSourceTurnpoints = useMemo(() => {
    if (!turnpointSort) return sourceTurnpoints;
    const direction = turnpointSort.direction === "asc" ? 1 : -1;
    return [...sourceTurnpoints].sort((left, right) => {
      const leftValue = turnpointSort.key === "name" ? left.name : turnpointSymbolLabel(left.symbol);
      const rightValue = turnpointSort.key === "name" ? right.name : turnpointSymbolLabel(right.symbol);
      return leftValue.localeCompare(rightValue, undefined, { sensitivity: "base" }) * direction;
    });
  }, [sourceTurnpoints, turnpointSort]);

  async function refreshSources() {
    await onSourcesChanged?.();
  }

  async function loadSourceTurnpoints(source: WaypointFileSourceRecord) {
    if (!token) return;
    setSourceTurnpointsLoading(true);
    try {
      const loaded = await apiFetch<TurnpointRecord[]>(`/api/turnpoint-library/${source.id}/turnpoints`, token);
      setSelectedSourceId(source.id);
      setSourceTurnpoints(loaded);
      setEditingTurnpointId(null);
      setTurnpointEdit(null);
      setDraftTurnpoint(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not load that waypoint file.");
    } finally {
      setSourceTurnpointsLoading(false);
    }
  }

  async function reloadSelectedSource() {
    if (selectedTurnpointSource) await loadSourceTurnpoints(selectedTurnpointSource);
  }

  async function saveTurnpointEdit() {
    if (!token || !selectedTurnpointSource || !turnpointEdit?.id) return;
    try {
      const saved = await apiFetch<TurnpointRecord>(`/api/turnpoint-library/${selectedTurnpointSource.id}/turnpoints/${turnpointEdit.id}`, token, {
        method: "PUT",
        body: JSON.stringify(editableToPayload(turnpointEdit)),
      });
      setMessage(`Saved waypoint ${saved.name}.`);
      await reloadSelectedSource();
      await refreshSources();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not save that waypoint.");
    }
  }

  async function saveDraftTurnpoint() {
    if (!token || !selectedTurnpointSource || !draftTurnpoint) return;
    try {
      const saved = await apiFetch<TurnpointRecord>(`/api/turnpoint-library/${selectedTurnpointSource.id}/turnpoints`, token, {
        method: "POST",
        body: JSON.stringify(editableToPayload(draftTurnpoint)),
      });
      setMessage(`Added waypoint ${saved.name}.`);
      setDraftTurnpoint(null);
      await reloadSelectedSource();
      await refreshSources();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not add that waypoint.");
    }
  }

  async function deleteSourceTurnpoint(turnpoint: TurnpointRecord) {
    if (!token || !selectedTurnpointSource) return;
    const confirmed = window.confirm(`Delete waypoint "${turnpoint.name}" from ${selectedTurnpointSource.filename}?`);
    if (!confirmed) return;
    try {
      await apiFetch<void>(`/api/turnpoint-library/${selectedTurnpointSource.id}/turnpoints/${turnpoint.id}`, token, { method: "DELETE" });
      setMessage(`Deleted waypoint ${turnpoint.name}.`);
      await reloadSelectedSource();
      await refreshSources();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not delete that waypoint.");
    }
  }

  async function downloadTurnpointSource(source: WaypointFileSourceRecord) {
    if (!token) return;
    const format = downloadFormats[source.id] ?? defaultExportFormat(source.file_format);
    try {
      const { blob, filename } = await apiFetchBlob(`/api/turnpoint-library/${source.id}/download?format=${encodeURIComponent(format)}`, token);
      downloadBlob(blob, filename ?? `${source.filename.replace(/\.[^.]+$/, "")}.${format}`);
      setMessage(`Started downloading ${source.filename}.`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not download that waypoint file.");
    }
  }

  async function renameTurnpointSource(source: WaypointFileSourceRecord) {
    if (!token) return;
    const nextName = window.prompt("Rename waypoint file", source.filename)?.trim();
    if (!nextName || nextName === source.filename) return;
    try {
      const renamed = await apiFetch<TurnpointSourceRecord>(`/api/turnpoint-library/${source.id}`, token, {
        method: "PATCH",
        body: JSON.stringify({ filename: nextName }),
      });
      setMessage(`Renamed ${source.filename} to ${renamed.filename}.`);
      await refreshSources();
      if (selectedSourceId === source.id) await loadSourceTurnpoints({ ...source, filename: renamed.filename });
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not rename that waypoint file.");
    }
  }

  function openSaveAs(source: WaypointFileSourceRecord) {
    const stem = source.filename.replace(/\.[^.]+$/, "");
    const suffix = source.filename.includes(".") ? source.filename.slice(source.filename.lastIndexOf(".")) : "";
    setSaveAsSource(source);
    setSaveAsFilename(`${stem} v2${suffix}`);
    setSaveAsFormat(defaultExportFormat(source.file_format));
  }

  async function saveTurnpointSourceAs() {
    if (!token || !saveAsSource || !saveAsFilename.trim()) return;
    try {
      const saved = await apiFetch<TurnpointSourceRecord>(`/api/turnpoint-library/${saveAsSource.id}/save-as`, token, {
        method: "POST",
        body: JSON.stringify({ filename: saveAsFilename.trim(), file_format: saveAsFormat }),
      });
      setMessage(`Saved ${saveAsSource.filename} as ${saved.filename}.`);
      setSaveAsSource(null);
      await refreshSources();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not save that waypoint file as a new version.");
    }
  }

  async function mergeTurnpointSources() {
    const selected = sources.filter((source) => mergeSourceIds.has(source.id));
    if (!token || selected.length < 2 || !mergeFilename.trim()) return;
    try {
      const merged = await apiFetch<TurnpointSourceRecord>("/api/turnpoint-library/merge", token, {
        method: "POST",
        body: JSON.stringify({ source_ids: selected.map((source) => source.id), filename: mergeFilename.trim() }),
      });
      setMessage(`Created merged GPX ${merged.filename}.`);
      setMergeOpen(false);
      setMergeFilename("");
      setMergeSourceIds(new Set());
      await refreshSources();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not merge those waypoint files.");
    }
  }

  async function deleteTurnpointSource(source: WaypointFileSourceRecord) {
    if (!token) return;
    const confirmed = window.confirm(`Delete ${source.filename} from the Turnpoint Library? Event selections will be removed, but existing task routes and scores stay unchanged.`);
    if (!confirmed) return;
    try {
      await apiFetch<void>(`/api/turnpoint-library/${source.id}`, token, { method: "DELETE" });
      setMessage(`Deleted ${source.filename}.`);
      closeTurnpointSourceDetail();
      await refreshSources();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not delete that waypoint file.");
    }
  }

  function updateEditableExtra(target: "edit" | "draft", key: string, value: string) {
    const setter = target === "edit" ? setTurnpointEdit : setDraftTurnpoint;
    setter((current) => current ? { ...current, extra_json: { ...current.extra_json, [key]: value } } : current);
  }

  function toggleTurnpointSort(key: TurnpointSortKey) {
    setTurnpointSort((current) => {
      if (!current || current.key !== key) return { key, direction: "asc" };
      return { key, direction: current.direction === "asc" ? "desc" : "asc" };
    });
  }

  function sortLabel(key: TurnpointSortKey) {
    if (turnpointSort?.key !== key) return "Sort";
    return turnpointSort.direction === "asc" ? "A-Z" : "Z-A";
  }

  function closeTurnpointSourceDetail() {
    setSelectedSourceId(null);
    setSourceTurnpoints([]);
    setEditingTurnpointId(null);
    setTurnpointEdit(null);
    setDraftTurnpoint(null);
  }

  return (
    <div className="stack form-block">
      <div className="button-row">
        <button
          type="button"
          className="ghost-button"
          disabled={mergeSourceIds.size < 2}
          onClick={() => {
            setMergeFilename("Merged turnpoints.gpx");
            setMergeOpen(true);
          }}
        >
          Merge selected
        </button>
        <span className="hint">{mergeSourceIds.size} selected</span>
      </div>
      <div className="participant-table-wrap">
        <table className="participant-table turnpoint-library-table">
          <thead>
            <tr>
              <th>Selection</th>
              <th>File name</th>
              <th>Format</th>
              <th>Waypoints</th>
              <th className="participant-table-actions">Actions</th>
            </tr>
          </thead>
          <tbody>
            {sources.length ? (
              sources.map((source) => (
                  <tr key={source.id}>
                    <td className="participant-table-check">
                      <input
                        type="checkbox"
                        aria-label={`Select ${source.filename} for merge`}
                        checked={mergeSourceIds.has(source.id)}
                        onChange={(event) => setMergeSourceIds((current) => {
                          const next = new Set(current);
                          if (event.target.checked) next.add(source.id);
                          else next.delete(source.id);
                          return next;
                        })}
                      />
                    </td>
                    <td className="turnpoint-file-name-cell">
                      <button type="button" className="link-button" onClick={() => void loadSourceTurnpoints(source)}>
                        <strong>{source.filename}</strong>
                      </button>
                    </td>
                    <td>{source.file_format.toUpperCase()}</td>
                    <td>{source.turnpoint_count}</td>
                    <td className="participant-table-actions">
                      <div className="compact-slot-actions">
                          <button type="button" className="ghost-button" onClick={() => void loadSourceTurnpoints(source)}>Edit</button>
                          <select
                            value={downloadFormats[source.id] ?? defaultExportFormat(source.file_format)}
                            aria-label={`Download format for ${source.filename}`}
                            onChange={(event) => setDownloadFormats((current) => ({ ...current, [source.id]: event.target.value }))}
                          >
                            {waypointExportFormats.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                          </select>
                          <button type="button" className="ghost-button" onClick={() => void downloadTurnpointSource(source)}>Download</button>
                          <button type="button" className="ghost-button" onClick={() => void renameTurnpointSource(source)}>Rename</button>
                          <button type="button" className="ghost-button" onClick={() => openSaveAs(source)}>Save as</button>
                          <button type="button" className="ghost-button danger-button" onClick={() => void deleteTurnpointSource(source)}>Delete</button>
                      </div>
                    </td>
                  </tr>
              ))
            ) : (
              <tr>
                <td colSpan={5} className="participant-table-empty">{emptyMessage}</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      {selectedTurnpointSource ? (
        <div className="turnpoint-file-detail">
          <div className="results-sheet-header turnpoint-detail-header">
            <div>
              <h3>{selectedTurnpointSource.filename}</h3>
              <p className="hint">
                {sourceTurnpoints.length} waypoint{sourceTurnpoints.length === 1 ? "" : "s"} in this file.
                {" Click the map to draft a new waypoint."}
              </p>
            </div>
            <button type="button" className="turnpoint-detail-close" onClick={closeTurnpointSourceDetail} aria-label="Close waypoint file detail">x</button>
          </div>
          <div className="turnpoint-file-layout">
            <div className="turnpoint-editor-map">
              <TaskMap
                turnpoints={sourceTurnpoints}
                airspaces={[]}
                taskPoints={[]}
                track={null}
                editable
                onSelectTurnpoint={(turnpoint) => {
                  const sourceTurnpoint = sourceTurnpoints.find((candidate) => candidate.id === turnpoint.id);
                  if (!sourceTurnpoint) return;
                  setDraftTurnpoint(null);
                  setEditingTurnpointId(sourceTurnpoint.id);
                  setTurnpointEdit(turnpointToEditable(sourceTurnpoint));
                }}
                onMapClick={(position) => {
                  setEditingTurnpointId(null);
                  setTurnpointEdit(null);
                  setDraftTurnpoint(turnpointToEditable(null, position));
                }}
                fitKey={`${selectedTurnpointSource.id}-${sourceTurnpoints.length}`}
                viewStateKey={`turnpoint-source-${selectedTurnpointSource.id}`}
                fitMaxZoom={12}
                telemetrySmoothing={telemetrySmoothing}
                overlayConfig={{ click_to_add_turnpoint: true }}
              />
            </div>
            <div className="stack compact turnpoint-draft-panel">
              {draftTurnpoint ? (
                <>
                  <strong>New waypoint</strong>
                  <div className="turnpoint-edit-grid">
                    <label><span>Name</span><input value={draftTurnpoint.name} onChange={(event) => setDraftTurnpoint({ ...draftTurnpoint, name: event.target.value })} /></label>
                    <label><span>Latitude</span><input value={draftTurnpoint.latitude} inputMode="decimal" onChange={(event) => setDraftTurnpoint({ ...draftTurnpoint, latitude: event.target.value })} /></label>
                    <label><span>Longitude</span><input value={draftTurnpoint.longitude} inputMode="decimal" onChange={(event) => setDraftTurnpoint({ ...draftTurnpoint, longitude: event.target.value })} /></label>
                    <label><span>Altitude</span><input value={draftTurnpoint.elevation_m} inputMode="decimal" onChange={(event) => setDraftTurnpoint({ ...draftTurnpoint, elevation_m: event.target.value })} /></label>
                    <label><span>Symbol</span><TurnpointSymbolSelect value={draftTurnpoint.symbol} onChange={(symbol) => setDraftTurnpoint({ ...draftTurnpoint, symbol })} /></label>
                  </div>
                  {selectedSourceExtraColumns.length ? (
                    <div className="turnpoint-extra-grid">
                      {selectedSourceExtraColumns.map((key) => (
                        <label key={key}><span>{key}</span><input value={draftTurnpoint.extra_json[key] ?? ""} onChange={(event) => updateEditableExtra("draft", key, event.target.value)} /></label>
                      ))}
                    </div>
                  ) : null}
                  <div className="button-row">
                    <button type="button" className="primary-button" onClick={() => void saveDraftTurnpoint()}>Save waypoint</button>
                    <button type="button" className="ghost-button" onClick={() => setDraftTurnpoint(null)}>Cancel</button>
                  </div>
                </>
              ) : turnpointEdit && editingTurnpointId ? (
                <>
                  <strong>Edit waypoint</strong>
                  <div className="turnpoint-edit-grid">
                    <label><span>Name</span><input value={turnpointEdit.name} onChange={(event) => setTurnpointEdit({ ...turnpointEdit, name: event.target.value })} /></label>
                    <label><span>Latitude</span><input value={turnpointEdit.latitude} inputMode="decimal" onChange={(event) => setTurnpointEdit({ ...turnpointEdit, latitude: event.target.value })} /></label>
                    <label><span>Longitude</span><input value={turnpointEdit.longitude} inputMode="decimal" onChange={(event) => setTurnpointEdit({ ...turnpointEdit, longitude: event.target.value })} /></label>
                    <label><span>Altitude</span><input value={turnpointEdit.elevation_m} inputMode="decimal" onChange={(event) => setTurnpointEdit({ ...turnpointEdit, elevation_m: event.target.value })} /></label>
                    <label><span>Symbol</span><TurnpointSymbolSelect value={turnpointEdit.symbol} onChange={(symbol) => setTurnpointEdit({ ...turnpointEdit, symbol })} /></label>
                  </div>
                  {selectedSourceExtraColumns.length ? (
                    <div className="turnpoint-extra-grid">
                      {selectedSourceExtraColumns.map((key) => (
                        <label key={key}><span>{key}</span><input value={turnpointEdit.extra_json[key] ?? ""} onChange={(event) => updateEditableExtra("edit", key, event.target.value)} /></label>
                      ))}
                    </div>
                  ) : null}
                  <div className="button-row">
                    <button type="button" className="primary-button" onClick={() => void saveTurnpointEdit()}>Save waypoint</button>
                    <button type="button" className="ghost-button" onClick={() => { setEditingTurnpointId(null); setTurnpointEdit(null); }}>Cancel</button>
                  </div>
                </>
              ) : (
                <p className="hint">Click a waypoint to edit it, or click open map space to place a new waypoint draft.</p>
              )}
            </div>
          </div>
          <div className="participant-table-wrap turnpoint-table-scroll">
            <table className="participant-table turnpoint-edit-table">
              <thead>
                <tr>
                  <th>
                    <button type="button" className="turnpoint-sort-button" onClick={() => toggleTurnpointSort("name")} aria-label={`Sort waypoints by name ${turnpointSort?.key === "name" && turnpointSort.direction === "asc" ? "descending" : "ascending"}`}>
                      <span>Name</span>
                      <span>{sortLabel("name")}</span>
                    </button>
                  </th>
                  <th>Lat</th>
                  <th>Long</th>
                  <th>Alt</th>
                  <th>
                    <button type="button" className="turnpoint-sort-button" onClick={() => toggleTurnpointSort("symbol")} aria-label={`Sort waypoints by symbol ${turnpointSort?.key === "symbol" && turnpointSort.direction === "asc" ? "descending" : "ascending"}`}>
                      <span>Symbol</span>
                      <span>{sortLabel("symbol")}</span>
                    </button>
                  </th>
                  {selectedSourceExtraColumns.map((key) => <th key={key}>{key}</th>)}
                  <th className="participant-table-actions">Actions</th>
                </tr>
              </thead>
              <tbody>
                {sourceTurnpointsLoading ? (
                  <tr><td colSpan={turnpointTableColSpan} className="participant-table-empty">Loading waypoints...</td></tr>
                ) : sortedSourceTurnpoints.length ? (
                  sortedSourceTurnpoints.map((turnpoint) => {
                    const isEditing = editingTurnpointId === turnpoint.id && turnpointEdit;
                    return (
                      <tr key={turnpoint.id}>
                        {isEditing ? (
                          <>
                            <td><input value={turnpointEdit.name} onChange={(event) => setTurnpointEdit({ ...turnpointEdit, name: event.target.value })} /></td>
                            <td><input value={turnpointEdit.latitude} inputMode="decimal" onChange={(event) => setTurnpointEdit({ ...turnpointEdit, latitude: event.target.value })} /></td>
                            <td><input value={turnpointEdit.longitude} inputMode="decimal" onChange={(event) => setTurnpointEdit({ ...turnpointEdit, longitude: event.target.value })} /></td>
                            <td><input value={turnpointEdit.elevation_m} inputMode="decimal" onChange={(event) => setTurnpointEdit({ ...turnpointEdit, elevation_m: event.target.value })} /></td>
                            <td><TurnpointSymbolSelect value={turnpointEdit.symbol} onChange={(symbol) => setTurnpointEdit({ ...turnpointEdit, symbol })} /></td>
                            {selectedSourceExtraColumns.map((key) => (
                              <td key={key}><input value={turnpointEdit.extra_json[key] ?? ""} onChange={(event) => updateEditableExtra("edit", key, event.target.value)} /></td>
                            ))}
                            <td className="participant-table-actions">
                              <button type="button" className="primary-button" onClick={() => void saveTurnpointEdit()}>Save</button>
                              <button type="button" className="ghost-button" onClick={() => { setEditingTurnpointId(null); setTurnpointEdit(null); }}>Cancel</button>
                            </td>
                          </>
                        ) : (
                          <>
                            <td><strong>{turnpoint.name}</strong></td>
                            <td>{turnpoint.latitude.toFixed(6)}</td>
                            <td>{turnpoint.longitude.toFixed(6)}</td>
                            <td>{turnpoint.elevation_m == null ? "" : Math.round(turnpoint.elevation_m)}</td>
                            <td className="turnpoint-symbol-cell"><TurnpointSymbolIcon symbol={normalizeEditableSymbol(turnpoint.symbol)} /> {turnpointSymbolLabel(turnpoint.symbol)}</td>
                            {selectedSourceExtraColumns.map((key) => <td key={key}>{String(turnpoint.extra_json?.[key] ?? "")}</td>)}
                              <td className="participant-table-actions">
                                <button type="button" className="ghost-button" onClick={() => { setEditingTurnpointId(turnpoint.id); setTurnpointEdit(turnpointToEditable(turnpoint)); }}>Edit</button>
                                <button type="button" className="ghost-button danger-button" onClick={() => void deleteSourceTurnpoint(turnpoint)}>Delete</button>
                              </td>
                          </>
                        )}
                      </tr>
                    );
                  })
                ) : (
                  <tr><td colSpan={turnpointTableColSpan} className="participant-table-empty">No waypoints in this file.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}
      {saveAsSource ? (
        <div className="confirm-overlay" onClick={() => setSaveAsSource(null)}>
          <div className="confirm-dialog" role="dialog" aria-modal="true" aria-labelledby="turnpoint-save-as-title" onClick={(event) => event.stopPropagation()}>
            <strong id="turnpoint-save-as-title">Save {saveAsSource.filename} as</strong>
            <label className="stack compact">
              <span>New filename</span>
              <input autoFocus value={saveAsFilename} onChange={(event) => setSaveAsFilename(event.target.value)} />
            </label>
            <label className="stack compact">
              <span>Format</span>
              <select value={saveAsFormat} onChange={(event) => setSaveAsFormat(event.target.value)}>
                {waypointExportFormats.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
              </select>
            </label>
            <div className="confirm-actions">
              <button type="button" className="ghost-button" onClick={() => setSaveAsSource(null)}>Cancel</button>
              <button type="button" className="primary-button" disabled={!saveAsFilename.trim()} onClick={() => void saveTurnpointSourceAs()}>Save copy</button>
            </div>
          </div>
        </div>
      ) : null}
      {mergeOpen ? (
        <div className="confirm-overlay" onClick={() => setMergeOpen(false)}>
          <div className="confirm-dialog confirm-dialog-wide" role="dialog" aria-modal="true" aria-labelledby="turnpoint-merge-title" onClick={(event) => event.stopPropagation()}>
            <strong id="turnpoint-merge-title">Merge {mergeSourceIds.size} turnpoint files</strong>
            <p>{sources.filter((source) => mergeSourceIds.has(source.id)).map((source) => source.filename).join(", ")}</p>
            <label className="stack compact">
              <span>New GPX filename</span>
              <input autoFocus value={mergeFilename} onChange={(event) => setMergeFilename(event.target.value)} />
            </label>
            <div className="confirm-actions">
              <button type="button" className="ghost-button" onClick={() => setMergeOpen(false)}>Cancel</button>
              <button type="button" className="primary-button" disabled={!mergeFilename.trim()} onClick={() => void mergeTurnpointSources()}>Create merged GPX</button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
