"use client";

import { type ChangeEvent, type FormEvent, useEffect, useMemo, useRef, useState } from "react";

import { TaskMap, type MapTelemetrySmoothing, type MapUnitPreferences } from "../TaskMap";
import { SectionCard } from "../SectionCard";
import type { LogbookFlightDetailRecord, LogbookFlightFormRecord, LogbookFlightSummaryRecord, LogbookFolderImportResultRecord, TrackCollection, User } from "./types";

export interface LogbookSectionProps {
  user: User | null;
  flights: LogbookFlightSummaryRecord[];
  loading: boolean;
  feedback: { type: "success" | "error" | "pending"; text: string } | null;
  detailFlight: LogbookFlightDetailRecord | null;
  detailLoading: boolean;
  replayFlight: LogbookFlightSummaryRecord | null;
  replayTrack: TrackCollection | null;
  replayLoading: boolean;
  units: MapUnitPreferences;
  telemetrySmoothing: MapTelemetrySmoothing;
  createManualFlight: (form: LogbookFlightFormRecord) => Promise<void>;
  uploadFlightFile: (file: File) => Promise<void>;
  scanFolderForFlights: (files: File[], confirmedFileKeys?: string[]) => Promise<LogbookFolderImportResultRecord>;
  attachFlightFile: (flight: LogbookFlightSummaryRecord, file: File) => Promise<void>;
  openFlightDetail: (flightId: number) => Promise<void>;
  closeFlightDetail: () => void;
  openFlightReplay: (flight: LogbookFlightSummaryRecord) => Promise<void>;
  closeFlightReplay: () => void;
  downloadFlight: (flightId: number) => Promise<void>;
  deleteFlight: (flight: LogbookFlightSummaryRecord) => Promise<void>;
  bulkDeleteFlights: (flights: LogbookFlightSummaryRecord[]) => Promise<void>;
  saveFlightNotes: (flightId: number, notes: string) => Promise<void>;
  setFlightStar: (flight: LogbookFlightSummaryRecord, starred: boolean) => Promise<void>;
}

type PendingFolderFile = {
  key: string;
  file: File;
};

function logbookImportFileKey(file: File) {
  const relativePath = "webkitRelativePath" in file && typeof file.webkitRelativePath === "string" && file.webkitRelativePath.trim()
    ? file.webkitRelativePath.trim()
    : file.name;
  return `${relativePath}::${file.size}::${file.lastModified}`;
}

function blankManualFlightForm(): LogbookFlightFormRecord {
  return {
    flight_date: new Date().toISOString().slice(0, 10),
    site_name: "",
    duration_seconds: "",
    highest_altitude_m: "",
    best_climb_mps: "",
    notes: "",
  };
}

function formatFlightDate(value: string) {
  const parsed = Date.parse(value);
  if (!Number.isFinite(parsed)) {
    return value;
  }
  return new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric" }).format(new Date(parsed));
}

function formatDuration(seconds: number | null | undefined) {
  if (seconds == null || !Number.isFinite(seconds)) {
    return "--";
  }
  const totalSeconds = Math.max(0, Math.round(seconds));
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  return `${hours}:${String(minutes).padStart(2, "0")}`;
}

function formatAltitude(valueM: number | null | undefined, unit: MapUnitPreferences["altitude"]) {
  if (valueM == null || !Number.isFinite(valueM)) {
    return "--";
  }
  if (unit === "ft") {
    return `${Math.round(valueM * 3.28084).toLocaleString()} ft`;
  }
  return `${Math.round(valueM).toLocaleString()} m`;
}

function formatVario(valueMps: number | null | undefined, unit: MapUnitPreferences["vario"]) {
  if (valueMps == null || !Number.isFinite(valueMps)) {
    return "--";
  }
  if (unit === "fpm") {
    return `${Math.round(valueMps * 196.850394).toLocaleString()} fpm`;
  }
  return `${valueMps.toFixed(1)} m/s`;
}

function sourceLabel(kind: LogbookFlightSummaryRecord["source_kind"]) {
  switch (kind) {
    case "task_upload":
      return "Task upload";
    case "app_upload":
      return "App / IGC";
    case "manual":
      return "Manual";
    default:
      return kind.replace(/_/g, " ");
  }
}

export default function LogbookSection(props: LogbookSectionProps) {
  const {
    user,
    flights,
    loading,
    feedback,
    detailFlight,
    detailLoading,
    replayFlight,
    replayTrack,
    replayLoading,
    units,
    telemetrySmoothing,
    createManualFlight,
    uploadFlightFile,
    scanFolderForFlights,
    attachFlightFile,
    openFlightDetail,
    closeFlightDetail,
    openFlightReplay,
    closeFlightReplay,
    downloadFlight,
    deleteFlight,
    bulkDeleteFlights,
    saveFlightNotes,
    setFlightStar,
  } = props;

  const [manualForm, setManualForm] = useState<LogbookFlightFormRecord>(blankManualFlightForm());
  const [manualOpen, setManualOpen] = useState(false);
  const [manualSubmitting, setManualSubmitting] = useState(false);
  const [notesDraft, setNotesDraft] = useState("");
  const [notesSaving, setNotesSaving] = useState(false);
  const [collapsedYears, setCollapsedYears] = useState<Record<string, boolean>>({});
  const [attachFlightId, setAttachFlightId] = useState<number | null>(null);
  const [folderImportResult, setFolderImportResult] = useState<LogbookFolderImportResultRecord | null>(null);
  const [pendingFolderFiles, setPendingFolderFiles] = useState<PendingFolderFile[]>([]);
  const [selectedReviewKeys, setSelectedReviewKeys] = useState<Record<string, boolean>>({});
  const [selectedFlightIds, setSelectedFlightIds] = useState<Record<number, boolean>>({});
  const [folderImportSubmitting, setFolderImportSubmitting] = useState(false);
  const [folderImportNotice, setFolderImportNotice] = useState<string | null>(null);
  const uploadRef = useRef<HTMLInputElement | null>(null);
  const folderUploadRef = useRef<HTMLInputElement | null>(null);
  const attachUploadRef = useRef<HTMLInputElement | null>(null);
  const [filterYear, setFilterYear] = useState<string>("all");
  const [filterSite, setFilterSite] = useState<string>("all");
  const [filterSearch, setFilterSearch] = useState("");

  const hasPilotProfile = Boolean(user?.pilot_id);

  const availableYears = useMemo(() => {
    const years = new Set<string>();
    flights.forEach((f) => {
      const y = Number.parseInt(f.flight_date.slice(0, 4), 10);
      if (Number.isFinite(y)) years.add(String(y));
    });
    return [...years].sort((a, b) => Number(b) - Number(a));
  }, [flights]);

  const availableSites = useMemo(() => {
    const sites = new Map<string, string>();
    flights.forEach((f) => {
      if (f.site_name) sites.set(f.site_name, f.site_city_state ?? "");
    });
    return [...sites.entries()].sort((a, b) => a[0].localeCompare(b[0]));
  }, [flights]);

  const filteredFlights = useMemo(() => {
    let list = flights;
    if (filterYear !== "all") {
      list = list.filter((f) => f.flight_date.startsWith(filterYear));
    }
    if (filterSite !== "all") {
      list = list.filter((f) => f.site_name === filterSite);
    }
    const q = filterSearch.trim().toLowerCase();
    if (q) {
      list = list.filter((f) => {
        const hay = `${f.site_name} ${f.site_city_state ?? ""} ${f.event_name ?? ""} ${f.task_name ?? ""} ${f.filename ?? ""} ${f.flight_date}`.toLowerCase();
        return hay.includes(q);
      });
    }
    return list;
  }, [flights, filterYear, filterSite, filterSearch]);

  const groupedFlights = useMemo(() => {
    const groups: Array<{ year: string; flights: LogbookFlightSummaryRecord[] }> = [];
    const groupMap = new Map<string, LogbookFlightSummaryRecord[]>();
    filteredFlights.forEach((flight) => {
      const parsedYear = Number.parseInt(flight.flight_date.slice(0, 4), 10);
      const year = Number.isFinite(parsedYear) ? String(parsedYear) : "Unknown year";
      const existing = groupMap.get(year);
      if (existing) {
        existing.push(flight);
        return;
      }
      const created = [flight];
      groupMap.set(year, created);
      groups.push({ year, flights: created });
    });
    return groups;
  }, [filteredFlights]);
  const allFlightIds = useMemo(() => flights.map((flight) => flight.id), [flights]);
  const selectedCount = useMemo(
    () => allFlightIds.filter((flightId) => selectedFlightIds[flightId]).length,
    [allFlightIds, selectedFlightIds],
  );
  const allSelected = allFlightIds.length > 0 && selectedCount === allFlightIds.length;

  useEffect(() => {
    setSelectedFlightIds((current) => {
      const nextEntries = Object.entries(current).filter(([flightId, selected]) => {
        if (!selected) {
          return false;
        }
        return allFlightIds.includes(Number(flightId));
      });
      if (nextEntries.length === Object.keys(current).length) {
        return current;
      }
      return Object.fromEntries(nextEntries.map(([flightId, selected]) => [Number(flightId), selected]));
    });
  }, [allFlightIds]);

  async function submitManualFlight(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setManualSubmitting(true);
    try {
      await createManualFlight(manualForm);
      setManualForm(blankManualFlightForm());
      setManualOpen(false);
    } finally {
      setManualSubmitting(false);
    }
  }

  async function handleUploadSelection(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) {
      return;
    }
    await uploadFlightFile(file);
  }

  async function handleAttachUploadSelection(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    const flightId = attachFlightId;
    setAttachFlightId(null);
    if (!file || flightId == null) {
      return;
    }
    const flight = flights.find((entry) => entry.id === flightId);
    if (!flight) {
      return;
    }
    await attachFlightFile(flight, file);
  }

  const replayTitle = useMemo(() => {
    if (!replayFlight) {
      return "Flight replay";
    }
    const primaryLabel = replayFlight.site_name || replayFlight.task_name || "Flight";
    return `${formatFlightDate(replayFlight.flight_date)} - ${primaryLabel}`;
  }, [replayFlight]);

  useEffect(() => {
    setNotesDraft(detailFlight?.notes ?? "");
  }, [detailFlight]);

  useEffect(() => {
    const input = folderUploadRef.current as (HTMLInputElement & { webkitdirectory?: boolean; directory?: boolean }) | null;
    if (!input) {
      return;
    }
    input.multiple = true;
    input.setAttribute("webkitdirectory", "");
    input.setAttribute("directory", "");
  }, []);

  async function handleDeleteFlight(flight: LogbookFlightSummaryRecord) {
    const confirmed = window.confirm("Are you sure you want to delete this flight? It can't be restored.");
    if (!confirmed) {
      return;
    }
    await deleteFlight(flight);
  }

  function toggleFlightSelection(flightId: number, checked: boolean) {
    setSelectedFlightIds((current) => ({
      ...current,
      [flightId]: checked,
    }));
  }

  function handleSelectAllFlights() {
    setSelectedFlightIds(Object.fromEntries(allFlightIds.map((flightId) => [flightId, true])));
  }

  function handleClearSelectedFlights() {
    setSelectedFlightIds({});
  }

  async function handleDeleteSelectedFlights() {
    const selectedFlights = flights.filter((flight) => selectedFlightIds[flight.id]);
    if (!selectedFlights.length) {
      return;
    }
    const confirmed = window.confirm(
      `Are you sure you want to delete the selected ${selectedFlights.length} flight${selectedFlights.length === 1 ? "" : "s"}? This cannot be undone.`,
    );
    if (!confirmed) {
      return;
    }
    await bulkDeleteFlights(selectedFlights);
    setSelectedFlightIds({});
  }

  async function handleSaveNotes() {
    if (!detailFlight) {
      return;
    }
    setNotesSaving(true);
    try {
      await saveFlightNotes(detailFlight.id, notesDraft);
    } finally {
      setNotesSaving(false);
    }
  }

  async function handleToggleStar(flight: LogbookFlightSummaryRecord) {
    await setFlightStar(flight, !flight.starred);
  }

  async function handleFolderSelection(event: ChangeEvent<HTMLInputElement>) {
    const selectedFiles = Array.from(event.target.files ?? []);
    event.target.value = "";
    if (!selectedFiles.length) {
      return;
    }
    const igcFiles = selectedFiles.filter((file) => file.name.toLowerCase().endsWith(".igc"));
    if (!igcFiles.length) {
      setFolderImportResult({ imported: [], skipped: [], review_needed: [] });
      setPendingFolderFiles([]);
      setSelectedReviewKeys({});
      setFolderImportNotice(null);
      return;
    }
    const keyedFiles = igcFiles.map((file) => ({ key: logbookImportFileKey(file), file }));
    setFolderImportNotice(null);
    setPendingFolderFiles(keyedFiles);
    setFolderImportSubmitting(true);
    try {
      const result = await scanFolderForFlights(igcFiles);
      setFolderImportResult(result);
      setSelectedReviewKeys(
        Object.fromEntries(result.review_needed.map((item) => [item.file_key, true])),
      );
    } finally {
      setFolderImportSubmitting(false);
    }
  }

  async function handleConfirmFolderImport() {
    const confirmedKeys = Object.entries(selectedReviewKeys)
      .filter(([, selected]) => selected)
      .map(([key]) => key);
    const confirmedFiles = pendingFolderFiles
      .filter((entry) => confirmedKeys.includes(entry.key))
      .map((entry) => entry.file);
    if (!confirmedFiles.length) {
      return;
    }
    setFolderImportSubmitting(true);
    try {
      const confirmationResult = await scanFolderForFlights(confirmedFiles, confirmedKeys);
      setFolderImportResult((current) => ({
        imported: [...(current?.imported ?? []), ...confirmationResult.imported],
        skipped: [...(current?.skipped ?? []), ...confirmationResult.skipped],
        review_needed: [
          ...((current?.review_needed ?? []).filter((item) => !confirmedKeys.includes(item.file_key))),
          ...confirmationResult.review_needed,
        ],
      }));
      setPendingFolderFiles((current) => current.filter((entry) => !confirmedKeys.includes(entry.key)));
      setSelectedReviewKeys((current) => {
        const retainedEntries = Object.entries(current).filter(([key, selected]) => !confirmedKeys.includes(key) && selected);
        const reviewEntries = confirmationResult.review_needed.map((item) => [item.file_key, true] as const);
        return Object.fromEntries([...retainedEntries, ...reviewEntries]);
      });
    } finally {
      setFolderImportSubmitting(false);
    }
  }

  function closeFolderImportModal() {
    const remainingReviewCount = folderImportResult?.review_needed.length ?? 0;
    const skippedCount = folderImportResult?.skipped.length ?? 0;
    setFolderImportResult(null);
    setPendingFolderFiles([]);
    setSelectedReviewKeys({});
    setFolderImportSubmitting(false);
    if (remainingReviewCount || skippedCount) {
      setFolderImportNotice("Unimported IGC files were discarded from this scan session.");
    }
  }

  return (
    <div className="section-stack">
      <SectionCard
        title="Pilot logbook"
        description="Review every uploaded or manually recorded flight for the signed-in pilot."
        actions={
          hasPilotProfile ? (
            <div className="button-row compact">
              <input ref={uploadRef} type="file" accept=".igc" hidden onChange={handleUploadSelection} />
              <input ref={folderUploadRef} type="file" accept=".igc" hidden onChange={handleFolderSelection} />
              <input ref={attachUploadRef} type="file" accept=".igc" hidden onChange={handleAttachUploadSelection} />
              <button type="button" className="ghost-button" onClick={() => uploadRef.current?.click()}>
                Upload IGC
              </button>
              <button type="button" className="ghost-button" onClick={() => folderUploadRef.current?.click()} disabled={folderImportSubmitting}>
                {folderImportSubmitting ? "Scanning..." : "Scan Folder for IGCs"}
              </button>
              <button type="button" className="ghost-button" onClick={() => setManualOpen(true)}>
                Manually Add Flight
              </button>
            </div>
          ) : null
        }
      >
        {!hasPilotProfile ? (
          <div className="stack form-block">
            <p className="hint">This account does not have a pilot profile yet, so there is no personal logbook to display.</p>
          </div>
        ) : (
          <div className="logbook-section-body">
            {feedback ? <div className={`status-chip ${feedback.type}`}>{feedback.text}</div> : null}
            {folderImportNotice ? <div className="status-chip pending">{folderImportNotice}</div> : null}
            <div className="logbook-filter-bar">
              <select value={filterYear} onChange={(e) => setFilterYear(e.target.value)}>
                <option value="all">All years</option>
                {availableYears.map((y) => <option key={y} value={y}>{y}</option>)}
              </select>
              <select value={filterSite} onChange={(e) => setFilterSite(e.target.value)}>
                <option value="all">All sites</option>
                {availableSites.map(([name]) => <option key={name} value={name}>{name}</option>)}
              </select>
              <input
                type="text"
                placeholder="Search flights..."
                value={filterSearch}
                onChange={(e) => setFilterSearch(e.target.value)}
                className="logbook-filter-search"
              />
              <span className="hint">{filteredFlights.length} of {flights.length} flights</span>
            </div>
            <div className="logbook-bulk-actions">
              <div className="button-row compact">
                <button type="button" className="ghost-button" onClick={handleSelectAllFlights} disabled={!allFlightIds.length || allSelected}>
                  Select all
                </button>
                <button type="button" className="ghost-button" onClick={handleClearSelectedFlights} disabled={!selectedCount}>
                  Clear selection
                </button>
                <button type="button" className="ghost-button danger-button" onClick={() => void handleDeleteSelectedFlights()} disabled={!selectedCount}>
                  Delete selected
                </button>
              </div>
              <span className="hint">{selectedCount} selected</span>
            </div>
            <div className="results-table-wrap logbook-table-wrap">
              <table className="results-table logbook-table">
                <thead>
                  <tr>
                    <th className="logbook-select-column">
                      <input
                        type="checkbox"
                        aria-label={allSelected ? "Clear all selected flights" : "Select all flights"}
                        checked={allSelected}
                        onChange={(event) => {
                          if (event.target.checked) {
                            handleSelectAllFlights();
                            return;
                          }
                          handleClearSelectedFlights();
                        }}
                      />
                    </th>
                    <th className="logbook-star-column" aria-label="Starred">★</th>
                    <th>Date</th>
                    <th>Site</th>
                    <th>Duration</th>
                    <th>Highest altitude</th>
                    <th>Best climb</th>
                    <th>Source</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {loading ? (
                    <tr>
                      <td colSpan={9} className="results-table-empty">Loading logbook flights...</td>
                    </tr>
                  ) : null}
                  {!loading && !groupedFlights.length ? (
                    <tr>
                      <td colSpan={9} className="results-table-empty">No flights have been recorded yet.</td>
                    </tr>
                  ) : null}
                </tbody>
                {!loading
                  ? groupedFlights.map((group) => {
                      const isCollapsed = collapsedYears[group.year] ?? false;
                      const yearFlightIds = group.flights.map((f) => f.id);
                      const yearSelectedCount = yearFlightIds.filter((id) => selectedFlightIds[id]).length;
                      const yearAllSelected = yearFlightIds.length > 0 && yearSelectedCount === yearFlightIds.length;
                      const yearSomeSelected = yearSelectedCount > 0 && !yearAllSelected;
                      return (
                        <tbody key={group.year}>
                          <tr className="logbook-year-row">
                            <td className="logbook-select-column">
                              <input
                                type="checkbox"
                                aria-label={yearAllSelected ? `Deselect all ${group.year} flights` : `Select all ${group.year} flights`}
                                checked={yearAllSelected}
                                ref={(el) => { if (el) el.indeterminate = yearSomeSelected; }}
                                onChange={() => {
                                  if (yearAllSelected) {
                                    setSelectedFlightIds((current) => {
                                      const next = { ...current };
                                      for (const id of yearFlightIds) delete next[id];
                                      return next;
                                    });
                                  } else {
                                    setSelectedFlightIds((current) => ({
                                      ...current,
                                      ...Object.fromEntries(yearFlightIds.map((id) => [id, true])),
                                    }));
                                  }
                                }}
                              />
                            </td>
                            <td colSpan={8}>
                              <button
                                type="button"
                                className="logbook-year-toggle"
                                onClick={() =>
                                  setCollapsedYears((current) => ({
                                    ...current,
                                    [group.year]: !isCollapsed,
                                  }))
                                }
                                aria-expanded={!isCollapsed}
                              >
                                <span className="logbook-year-label">{group.year}</span>
                                <span className="logbook-year-meta">{group.flights.length} {group.flights.length === 1 ? "flight" : "flights"}</span>
                                <span className="logbook-year-chevron">{isCollapsed ? "+" : "-"}</span>
                              </button>
                            </td>
                          </tr>
                          {!isCollapsed
                            ? group.flights.map((flight) => (
                                <tr key={flight.id}>
                                  <td className="logbook-select-column">
                                    <input
                                      type="checkbox"
                                      aria-label={`Select ${flight.filename ?? flight.site_name ?? "flight"}`}
                                      checked={selectedFlightIds[flight.id] ?? false}
                                      onChange={(event) => toggleFlightSelection(flight.id, event.target.checked)}
                                    />
                                  </td>
                                  <td className="logbook-star-column">
                                    <button
                                      type="button"
                                      className={`logbook-star-button${flight.starred ? " active" : ""}`}
                                      aria-label={flight.starred ? "Unstar flight" : "Star flight"}
                                      aria-pressed={flight.starred}
                                      onClick={() => void handleToggleStar(flight)}
                                    >
                                      {flight.starred ? "★" : "☆"}
                                    </button>
                                  </td>
                                  <td>{formatFlightDate(flight.flight_date)}</td>
                                  <td className="logbook-site-cell">
                                    <strong>{flight.site_name || "--"}</strong>
                                    {flight.task_name || flight.event_name ? (
                                      <div className="hint">{[flight.task_name, flight.event_name].filter(Boolean).join(" - ")}</div>
                                    ) : null}
                                  </td>
                                  <td>{formatDuration(flight.duration_seconds)}</td>
                                  <td>{formatAltitude(flight.highest_altitude_m, units.altitude)}</td>
                                  <td>{formatVario(flight.best_climb_mps, units.vario)}</td>
                                  <td>
                                    <span className="status-chip pending">{sourceLabel(flight.source_kind)}</span>
                                  </td>
                                  <td>
                                    <div className="logbook-row-actions">
                                      <button type="button" className="ghost-button" onClick={() => void openFlightDetail(flight.id)}>
                                        Statistics
                                      </button>
                                      {flight.can_replay ? (
                                        <button type="button" className="ghost-button" onClick={() => void openFlightReplay(flight)}>
                                          Replay
                                        </button>
                                      ) : null}
                                      {flight.can_download ? (
                                        <button type="button" className="ghost-button" onClick={() => void downloadFlight(flight.id)}>
                                          Download IGC
                                        </button>
                                      ) : null}
                                      {!flight.can_download ? (
                                        <button
                                          type="button"
                                          className="ghost-button"
                                          onClick={() => {
                                            setAttachFlightId(flight.id);
                                            attachUploadRef.current?.click();
                                          }}
                                        >
                                          Upload IGC file
                                        </button>
                                      ) : null}
                                      <button type="button" className="ghost-button danger-button" onClick={() => void handleDeleteFlight(flight)}>
                                        Delete flight
                                      </button>
                                    </div>
                                  </td>
                                </tr>
                              ))
                            : null}
                        </tbody>
                      );
                    })
                  : null}
              </table>
            </div>
          </div>
        )}
      </SectionCard>

      {manualOpen ? (
        <div className="logbook-modal-overlay active" role="presentation">
          <div className="logbook-modal">
            <div className="section-card-header">
              <div>
                <h3>Add manual flight</h3>
                <p className="hint">Create a logbook row without an IGC file. You can add replayable IGC flights with the upload button.</p>
              </div>
            </div>
            <form className="stack form-block" onSubmit={submitManualFlight}>
              <div className="inline-grid">
                <label className="stack compact">
                  <span>Date</span>
                  <input type="date" value={manualForm.flight_date} onChange={(event) => setManualForm((current) => ({ ...current, flight_date: event.target.value }))} required />
                </label>
                <label className="stack compact">
                  <span>Site</span>
                  <input value={manualForm.site_name} onChange={(event) => setManualForm((current) => ({ ...current, site_name: event.target.value }))} required />
                </label>
              </div>
              <div className="inline-grid">
                <label className="stack compact">
                  <span>Flight duration (seconds)</span>
                  <input type="number" min={0} value={manualForm.duration_seconds} onChange={(event) => setManualForm((current) => ({ ...current, duration_seconds: event.target.value }))} />
                </label>
                <label className="stack compact">
                  <span>Highest altitude (m)</span>
                  <input type="number" value={manualForm.highest_altitude_m} onChange={(event) => setManualForm((current) => ({ ...current, highest_altitude_m: event.target.value }))} />
                </label>
              </div>
              <div className="inline-grid">
                <label className="stack compact">
                  <span>Best climb (m/s)</span>
                  <input type="number" step="0.1" value={manualForm.best_climb_mps} onChange={(event) => setManualForm((current) => ({ ...current, best_climb_mps: event.target.value }))} />
                </label>
                <div />
              </div>
              <label className="stack compact">
                <span>Notes</span>
                <textarea rows={4} value={manualForm.notes} onChange={(event) => setManualForm((current) => ({ ...current, notes: event.target.value }))} />
              </label>
              <div className="button-row">
                <button type="button" className="ghost-button" onClick={() => setManualOpen(false)} disabled={manualSubmitting}>
                  Cancel
                </button>
                <button type="submit" disabled={manualSubmitting}>
                  {manualSubmitting ? "Saving..." : "Save flight"}
                </button>
              </div>
            </form>
          </div>
        </div>
      ) : null}

      {folderImportResult ? (
        <div className="logbook-modal-overlay active" role="presentation">
          <div className="logbook-modal">
            <div className="section-card-header">
              <div>
                <h3>Folder import results</h3>
                <p className="hint">Scanned the selected folder and its subfolders for IGC files.</p>
              </div>
              <div className="button-row compact">
                <button type="button" className="ghost-button" onClick={closeFolderImportModal}>Close</button>
              </div>
            </div>
            <div className="logbook-import-sections">
              <details className="logbook-import-section" open>
                <summary className="logbook-import-section-summary">
                  <span className="logbook-import-section-title">Imported</span>
                  <span className="logbook-import-section-badge success">{folderImportResult.imported.length}</span>
                  <span className="logbook-import-section-chevron" aria-hidden="true" />
                </summary>
                <div className="logbook-import-section-body">
                  {folderImportResult.imported.length ? (
                    <div className="logbook-import-list compact">
                      {folderImportResult.imported.map((item) => (
                        <div key={`imported-${item.file_key}`} className="logbook-import-row">
                          <strong title={item.relative_path || item.filename}>{item.relative_path || item.filename}</strong>
                          <span className="hint">{item.detected_pilot_name || item.reason}</span>
                        </div>
                      ))}
                    </div>
                  ) : <p className="hint">No files were imported automatically.</p>}
                </div>
              </details>

              <details className="logbook-import-section" open>
                <summary className="logbook-import-section-summary">
                  <span className="logbook-import-section-title">Need review</span>
                  <span className="logbook-import-section-badge pending">{folderImportResult.review_needed.length}</span>
                  <span className="logbook-import-section-chevron" aria-hidden="true" />
                </summary>
                <div className="logbook-import-section-body">
                  {folderImportResult.review_needed.length ? (
                    <div className="logbook-import-list compact">
                      {folderImportResult.review_needed.map((item) => {
                        const selected = selectedReviewKeys[item.file_key] ?? false;
                        return (
                          <label
                            key={`review-${item.file_key}`}
                            className={`logbook-import-review-row${selected ? " selected" : ""}`}
                          >
                            <input
                              type="checkbox"
                              checked={selected}
                              onChange={(event) =>
                                setSelectedReviewKeys((current) => ({
                                  ...current,
                                  [item.file_key]: event.target.checked,
                                }))
                              }
                            />
                            <div className="logbook-import-review-copy">
                              <div className="logbook-import-row">
                                <strong title={item.relative_path || item.filename}>{item.relative_path || item.filename}</strong>
                                <span className="hint">{item.detected_pilot_name ? `Detected: ${item.detected_pilot_name}` : "No pilot detected"}</span>
                              </div>
                              <span className="hint">{item.reason}</span>
                            </div>
                          </label>
                        );
                      })}
                    </div>
                  ) : <p className="hint">No uncertain files are waiting for review.</p>}
                </div>
              </details>

              <details className="logbook-import-section">
                <summary className="logbook-import-section-summary">
                  <span className="logbook-import-section-title">Skipped</span>
                  <span className="logbook-import-section-badge muted">{folderImportResult.skipped.length}</span>
                  <span className="logbook-import-section-chevron" aria-hidden="true" />
                </summary>
                <div className="logbook-import-section-body">
                  {folderImportResult.skipped.length ? (
                    <div className="logbook-import-list compact">
                      {folderImportResult.skipped.map((item) => (
                        <div key={`skipped-${item.file_key}-${item.reason}`} className="logbook-import-row">
                          <strong title={item.relative_path || item.filename}>{item.relative_path || item.filename}</strong>
                          <span className="hint">{item.reason}</span>
                        </div>
                      ))}
                    </div>
                  ) : <p className="hint">No files were skipped.</p>}
                </div>
              </details>
            </div>
            {folderImportResult.review_needed.length ? (
              <div className="button-row logbook-import-actions">
                <button type="button" className="ghost-button" onClick={closeFolderImportModal} disabled={folderImportSubmitting}>
                  Cancel
                </button>
                <button type="button" onClick={() => void handleConfirmFolderImport()} disabled={folderImportSubmitting}>
                  {folderImportSubmitting ? "Importing..." : "Import Selected Matches"}
                </button>
              </div>
            ) : null}
          </div>
        </div>
      ) : null}

      {detailFlight || detailLoading ? (
        <div className="logbook-modal-overlay active" role="presentation">
          <div className="logbook-modal logbook-modal-wide">
            <div className="section-card-header">
              <div>
                <h3>{detailFlight ? `${formatFlightDate(detailFlight.flight_date)} - ${detailFlight.site_name || "Flight statistics"}` : "Loading statistics..."}</h3>
                <p className="hint">Derived flight metrics and summary details for this personal logbook entry.</p>
              </div>
              <div className="button-row compact">
                <button type="button" className="ghost-button" onClick={closeFlightDetail}>Close</button>
              </div>
            </div>
            {detailLoading || !detailFlight ? (
              <div className="stack form-block">
                <p className="hint">Loading flight statistics...</p>
              </div>
            ) : (
              <div className="logbook-stats-grid">
                <div className="logbook-stats-card">
                  <h4>Summary</h4>
                  <dl className="logbook-stats-list">
                    <div><dt>Source</dt><dd>{sourceLabel(detailFlight.source_kind)}</dd></div>
                    <div><dt>Duration</dt><dd>{formatDuration(detailFlight.stats.duration_seconds)}</dd></div>
                    <div><dt>Highest altitude</dt><dd>{formatAltitude(detailFlight.stats.highest_altitude_m, units.altitude)}</dd></div>
                    <div><dt>Best climb</dt><dd>{formatVario(detailFlight.stats.best_climb_mps, units.vario)}</dd></div>
                    <div><dt>Launch time</dt><dd>{detailFlight.stats.launch_time ? new Date(detailFlight.stats.launch_time).toLocaleString() : "--"}</dd></div>
                    <div><dt>Landing time</dt><dd>{detailFlight.stats.landing_time ? new Date(detailFlight.stats.landing_time).toLocaleString() : "--"}</dd></div>
                  </dl>
                </div>
                <div className="logbook-stats-card">
                  <h4>Statistics</h4>
                  <dl className="logbook-stats-list">
                    <div><dt>Launch altitude</dt><dd>{formatAltitude(detailFlight.stats.launch_altitude_m, units.altitude)}</dd></div>
                    <div><dt>Landing altitude</dt><dd>{formatAltitude(detailFlight.stats.landing_altitude_m, units.altitude)}</dd></div>
                    <div><dt>Time in thermals</dt><dd>{formatDuration(detailFlight.stats.time_in_thermals_seconds)}</dd></div>
                    <div><dt>Time on glide</dt><dd>{formatDuration(detailFlight.stats.time_on_glide_seconds)}</dd></div>
                    <div><dt>Total track distance</dt><dd>{detailFlight.stats.total_track_distance_km ? `${detailFlight.stats.total_track_distance_km.toFixed(1)} km` : "--"}</dd></div>
                    <div><dt>Max ground speed</dt><dd>{detailFlight.stats.max_ground_speed_kmh ? `${detailFlight.stats.max_ground_speed_kmh.toFixed(1)} km/h` : "--"}</dd></div>
                    <div><dt>IGC file</dt><dd>{detailFlight.filename || "--"}</dd></div>
                  </dl>
                </div>
                <div className="logbook-stats-card logbook-stats-notes">
                  <h4>Notes</h4>
                  <div className="stack compact">
                    <textarea rows={5} value={notesDraft} onChange={(event) => setNotesDraft(event.target.value)} placeholder="Add personal notes about this flight..." />
                    <div className="button-row">
                      <button type="button" onClick={() => void handleSaveNotes()} disabled={notesSaving}>
                        {notesSaving ? "Saving..." : "Save notes"}
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      ) : null}

      {replayFlight ? (
        <div className="logbook-modal-overlay active" role="presentation">
          <div className="logbook-modal logbook-modal-map">
            <div className="section-card-header">
              <div>
                <h3>{replayTitle}</h3>
                <p className="hint">Replay this personal flight using the same controls as the task replay map.</p>
              </div>
              <div className="button-row compact">
                <button type="button" className="ghost-button" onClick={closeFlightReplay}>Close</button>
              </div>
            </div>
            {replayLoading || !replayTrack ? (
              <div className="stack form-block">
                <p className="hint">Loading replay track...</p>
              </div>
            ) : (
              <div className="logbook-replay-shell">
                <TaskMap
                  turnpoints={[]}
                  taskPoints={[]}
                  track={replayTrack}
                  editable={false}
                  hideDistanceSummary
                  highlightedTrackUploadId={replayFlight.id}
                  units={units}
                  telemetrySmoothing={telemetrySmoothing}
                  mode="replay"
                />
              </div>
            )}
          </div>
        </div>
      ) : null}
    </div>
  );
}
